import os
import logging
import asyncio
import datetime
import urllib.parse
from typing import Optional, Dict, Any, List
import httpx

from app.config import settings

logger = logging.getLogger(__name__)

ADMIN_NOTIFICATION_PHONE = os.getenv("ADMIN_NOTIFICATION_PHONE", "+2348063584517").strip()
TERMII_API_KEY = os.getenv("TERMII_API_KEY", "").strip().strip('"').strip("'")
TERMII_SENDER_ID = os.getenv("TERMII_SENDER_ID", "TekTutors").strip().strip('"').strip("'")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "").strip()

# In-memory dispatch audit log (stores recent 200 dispatches)
SMS_DISPATCH_LOG = []

# GSM 7-bit character sets (basic + extension table: ^{}\[~]|€)
GSM_7_BASIC = set(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ\x1bÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
GSM_7_EXTENDED = set("^{}\\[~]|€")
GSM_7_CHARS = GSM_7_BASIC | GSM_7_EXTENDED



def normalize_phone_number(phone: str, default_country: str = "+234") -> str:
    """
    Standardize a phone number into international E.164 format.
    Handles Nigerian prefixes (080..., 070..., 090..., 091...), local 11-digit numbers,
    and existing international country codes.
    """
    if not phone:
        return ""
    clean = str(phone).strip()
    digits = "".join(filter(str.isdigit, clean))
    
    if not digits:
        return clean

    # Nigerian 11-digit local format: 080..., 070..., etc.
    if len(digits) == 11 and digits.startswith("0"):
        return f"+234{digits[1:]}"
    # Nigerian 10-digit format without leading 0: 80..., 70...
    elif len(digits) == 10 and digits.startswith(("7", "8", "9")):
        return f"+234{digits}"
    # Already with country code (e.g. 23480...)
    elif len(digits) >= 12 and digits.startswith("234"):
        return f"+{digits}"
    # If original had a '+' and other country code
    elif clean.startswith("+"):
        return f"+{digits}"
    else:
        # Default fallback
        if clean.startswith("0") and len(digits) == 11:
            return f"+234{digits[1:]}"
        return f"+{digits}"


def calculate_sms_segments(text: str) -> Dict[str, Any]:
    """
    Calculate SMS length, segment/part count, encoding (GSM-7 vs Unicode),
    and remaining characters in current segment.
    - GSM-7: 160 characters for 1 part; 153 characters per part for multi-part.
    - Unicode: 70 characters for 1 part; 67 characters per part for multi-part.
    """
    if not text:
        return {
            "char_count": 0,
            "segment_count": 1,
            "encoding": "GSM-7",
            "chars_remaining_in_segment": 160
        }

    is_unicode = any(char not in GSM_7_CHARS for char in text)
    encoding = "Unicode" if is_unicode else "GSM-7"
    char_len = len(text)

    if encoding == "GSM-7":
        if char_len <= 160:
            segments = 1
            remaining = 160 - char_len
        else:
            segments = (char_len + 152) // 153
            remaining = (segments * 153) - char_len
    else:
        if char_len <= 70:
            segments = 1
            remaining = 70 - char_len
        else:
            segments = (char_len + 66) // 67
            remaining = (segments * 67) - char_len

    return {
        "char_count": char_len,
        "segment_count": segments,
        "encoding": encoding,
        "chars_remaining_in_segment": remaining
    }


async def get_termii_balance() -> Dict[str, Any]:
    """
    Query current wallet credit balance from Termii.
    Returns balance number, currency, and provider info.
    """
    if not TERMII_API_KEY:
        return {
            "balance": 2500.0,
            "currency": "NGN",
            "provider": "termii",
            "status": "simulated",
            "sender_id": TERMII_SENDER_ID,
            "note": "TERMII_API_KEY is unset; simulated testing balance displayed."
        }

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                f"https://api.ng.termii.com/api/get-balance?api_key={TERMII_API_KEY}"
            )
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "balance": float(data.get("balance", 0.0)),
                    "currency": data.get("currency", "NGN"),
                    "provider": "termii",
                    "status": "live",
                    "sender_id": TERMII_SENDER_ID
                }
            else:
                logger.warning(f"Termii get-balance responded with HTTP {resp.status_code}: {resp.text}")
                return {
                    "balance": 0.0,
                    "currency": "NGN",
                    "provider": "termii",
                    "status": "error",
                    "error": f"HTTP {resp.status_code}"
                }
    except Exception as e:
        logger.error(f"Error querying Termii balance: {e}")
        return {
            "balance": 0.0,
            "currency": "NGN",
            "provider": "termii",
            "status": "error",
            "error": str(e)
        }


async def send_single_sms(
    to_phone: str,
    message: str,
    sender_id: Optional[str] = None,
    channel: str = "generic",
    recipient_name: Optional[str] = "Student",
    lead_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Dispatch a single SMS via Termii, Twilio, or simulator fallback.
    """
    clean_target = normalize_phone_number(to_phone)
    raw_sender = (sender_id or TERMII_SENDER_ID or "tektutors").strip()
    active_sender = "tektutors" if raw_sender.lower() == "tektutors" else raw_sender
    seg_info = calculate_sms_segments(message)

    result = {
        "recipient_phone": clean_target,
        "recipient_name": recipient_name or "Student",
        "sender_id": active_sender,
        "message": message,
        "segments": seg_info["segment_count"],
        "encoding": seg_info["encoding"],
        "sent_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "channel": channel,
        "provider": "none",
        "status": "pending",
        "error": None
    }

    # Format destination for Termii (Termii expects numbers without '+' e.g. 2348063584517)
    termii_to = clean_target.replace("+", "")

    # 1. Termii SMS Integration (Preferred Tier-1 Route for Nigeria)
    if TERMII_API_KEY and termii_to:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                termii_payload = {
                    "to": termii_to,
                    "from": active_sender,
                    "sms": message,
                    "type": "plain",
                    "channel": channel,  # 'generic' or 'dnd'
                    "api_key": TERMII_API_KEY
                }
                resp = await client.post("https://api.ng.termii.com/api/sms/send", json=termii_payload)
                if resp.status_code in (200, 201):
                    result["status"] = "delivered"
                    result["provider"] = "termii"
                    logger.info(f"📲 SMS dispatched to {clean_target} via Termii.")
                else:
                    logger.warning(f"Termii SMS failed ({resp.status_code}): {resp.text}")
                    result["error"] = f"Termii HTTP {resp.status_code}"
        except Exception as e:
            logger.error(f"Error calling Termii SMS API: {e}")
            result["error"] = str(e)

    # 2. Twilio SMS Integration (Fallback or International)
    if result["status"] != "delivered" and TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                twilio_url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
                resp = await client.post(
                    twilio_url,
                    data={
                        "To": clean_target,
                        "From": TWILIO_FROM_NUMBER,
                        "Body": message
                    },
                    auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
                )
                if resp.status_code in (200, 201):
                    result["status"] = "delivered"
                    result["provider"] = "twilio"
                    logger.info(f"📲 SMS dispatched to {clean_target} via Twilio.")
                else:
                    logger.warning(f"Twilio SMS failed ({resp.status_code}): {resp.text}")
                    result["error"] = f"Twilio HTTP {resp.status_code}"
        except Exception as e:
            logger.error(f"Error calling Twilio SMS API: {e}")
            result["error"] = str(e)

    # 3. Simulated Fallback
    if result["status"] == "pending":
        result["status"] = "simulated"
        result["provider"] = "simulator"
        logger.info(f"📲 [SMS SIMULATED to {clean_target} | Sender: {active_sender}]: {message}")

    SMS_DISPATCH_LOG.append(result)
    if len(SMS_DISPATCH_LOG) > 200:
        SMS_DISPATCH_LOG.pop(0)

    return result


async def send_bulk_sms(
    recipients: List[Dict[str, Any]],
    message_template: str,
    sender_id: Optional[str] = None,
    channel: str = "generic",
    db_session: Any = None
) -> Dict[str, Any]:
    """
    Broadcast a bulk SMS campaign to a list of recipients with tag personalization ({name}, {course}).
    Sends concurrently with rate limiting and persists audit records to database.
    """
    if not recipients:
        return {
            "total": 0,
            "delivered": 0,
            "simulated": 0,
            "failed": 0,
            "results": [],
            "message": "No recipients provided"
        }

    raw_sender = (sender_id or TERMII_SENDER_ID or "tektutors").strip()
    active_sender = "tektutors" if raw_sender.lower() == "tektutors" else raw_sender
    semaphore = asyncio.Semaphore(5)  # Safe concurrency limit for SMS gateways

    async def _send_worker(item: Dict[str, Any]) -> Dict[str, Any]:
        async with semaphore:
            phone = item.get("phone") or ""
            name = item.get("name") or "Student"
            course = item.get("course") or "Data Analytics & AI"
            lead_id = item.get("lead_id")

            # Personalize message template
            personalized_msg = (
                message_template
                .replace("{name}", name)
                .replace("{Name}", name)
                .replace("{course}", course)
                .replace("{Course}", course)
                .replace("{phone}", phone)
            )

            res = await send_single_sms(
                to_phone=phone,
                message=personalized_msg,
                sender_id=active_sender,
                channel=channel,
                recipient_name=name,
                lead_id=lead_id
            )

            # Optional DB logging
            if db_session:
                try:
                    from app.models import SmsLog
                    sms_log = SmsLog(
                        lead_id=lead_id,
                        recipient_phone=res["recipient_phone"],
                        recipient_name=name,
                        sender_id=active_sender,
                        body=personalized_msg,
                        segments=res["segments"],
                        provider=res["provider"],
                        status=res["status"],
                        error_message=res.get("error")
                    )
                    db_session.add(sms_log)
                except Exception as log_err:
                    logger.warning(f"Could not persist SmsLog record: {log_err}")

            return res

    results = await asyncio.gather(*[_send_worker(r) for r in recipients])

    if db_session:
        try:
            await db_session.commit()
        except Exception as commit_err:
            logger.warning(f"Error committing bulk SmsLogs: {commit_err}")

    delivered_count = sum(1 for r in results if r["status"] == "delivered")
    simulated_count = sum(1 for r in results if r["status"] == "simulated")
    failed_count = sum(1 for r in results if r["status"] not in ("delivered", "simulated"))

    return {
        "total": len(results),
        "delivered": delivered_count,
        "simulated": simulated_count,
        "failed": failed_count,
        "sender_id": active_sender,
        "channel": channel,
        "results": results
    }


async def send_chat_initiated_sms(
    student_phone: str,
    student_name: Optional[str] = None,
    initial_message: Optional[str] = None,
    notification_phone: str = ADMIN_NOTIFICATION_PHONE
) -> Dict[str, Any]:
    """
    Sends an immediate SMS alert to the admin (+2348063584517) whenever a new prospective
    student initiates a conversation with the TekTutors WhatsApp Sales Agent.
    
    Supports Termii (Nigeria Tier-1 SMS route), Twilio, and direct WhatsApp notification fallback.
    """
    clean_target = normalize_phone_number(notification_phone or ADMIN_NOTIFICATION_PHONE)
    clean_name = (student_name or "New Prospect").strip()
    msg_snippet = (initial_message or "New chat initiated").strip().replace("\n", " ")
    if len(msg_snippet) > 80:
        msg_snippet = msg_snippet[:77] + "..."

    timestamp_str = datetime.datetime.now().strftime("%I:%M %p")
    sms_text = (
        f"🔔 TekTutors Alert: New Chat Initiated!\n"
        f"Student: {clean_name} ({student_phone})\n"
        f"Msg: \"{msg_snippet}\"\n"
        f"Time: {timestamp_str}"
    )

    result = {
        "notification_phone": clean_target,
        "student_phone": student_phone,
        "student_name": clean_name,
        "sent_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "channel": "sms",
        "provider": "none",
        "status": "pending",
        "error": None
    }

    # 1. Termii SMS Integration
    if TERMII_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                termii_payload = {
                    "to": clean_target.replace("+", ""),
                    "from": TERMII_SENDER_ID,
                    "sms": sms_text,
                    "type": "plain",
                    "channel": "generic",
                    "api_key": TERMII_API_KEY
                }
                resp = await client.post("https://api.ng.termii.com/api/sms/send", json=termii_payload)
                if resp.status_code in (200, 201):
                    result["status"] = "delivered"
                    result["provider"] = "termii"
                    logger.info(f"📲 Chat-initiated SMS dispatched to {clean_target} via Termii.")
                else:
                    logger.warning(f"Termii SMS failed ({resp.status_code}): {resp.text}")
                    result["error"] = f"Termii {resp.status_code}"
        except Exception as e:
            logger.error(f"Error calling Termii SMS API: {e}")
            result["error"] = str(e)

    # 2. Twilio SMS Integration
    if result["status"] != "delivered" and TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                twilio_url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
                resp = await client.post(
                    twilio_url,
                    data={
                        "To": clean_target,
                        "From": TWILIO_FROM_NUMBER,
                        "Body": sms_text
                    },
                    auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
                )
                if resp.status_code in (200, 201):
                    result["status"] = "delivered"
                    result["provider"] = "twilio"
                    logger.info(f"📲 Chat-initiated SMS dispatched to {clean_target} via Twilio.")
                else:
                    logger.warning(f"Twilio SMS failed ({resp.status_code}): {resp.text}")
                    result["error"] = f"Twilio {resp.status_code}"
        except Exception as e:
            logger.error(f"Error calling Twilio SMS API: {e}")
            result["error"] = str(e)

    # 3. Dual Alert Fallback: Direct WhatsApp Admin Alert (skip if student is chatting from the admin notification phone)
    try:
        from app.whatsapp import whatsapp_client
        wa_digits = "".join(filter(str.isdigit, clean_target))
        student_digits = "".join(filter(str.isdigit, normalize_phone_number(student_phone) or student_phone))
        if wa_digits and wa_digits != student_digits:
            wa_alert = (
                f"🔔 *TekTutors Alert: New Chat Initiated!*\n\n"
                f"• *Student:* {clean_name}\n"
                f"• *Phone:* {student_phone}\n"
                f"• *Inbound Message:* \"{msg_snippet}\"\n"
                f"• *Time:* {timestamp_str}\n\n"
                f"View live chat in dashboard: https://tektutors.com.ng/dashboard"
            )
            asyncio.create_task(whatsapp_client.send_text_message(wa_digits, wa_alert))
            if result["status"] != "delivered":
                result["status"] = "delivered"
                result["provider"] = "whatsapp_direct_fallback"
                logger.info(f"📲 Chat-initiated alert sent to admin {clean_target} via WhatsApp direct.")
    except Exception as e:
        logger.warning(f"Could not dispatch fallback WhatsApp alert to admin: {e}")

    # Fallback simulated record if no live provider was reached
    if result["status"] == "pending":
        result["status"] = "simulated"
        result["provider"] = "local_logger"
        logger.info(f"📲 [SMS ALERT SIMULATED to {clean_target}]: {sms_text}")

    SMS_DISPATCH_LOG.append(result)
    if len(SMS_DISPATCH_LOG) > 200:
        SMS_DISPATCH_LOG.pop(0)

    return result
