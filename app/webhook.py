import logging
import hmac
import hashlib
import asyncio
from typing import Dict, Any
from fastapi import APIRouter, Request, Response, HTTPException, Depends, Query, BackgroundTasks
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db, AsyncSessionLocal
from app.models import Conversation, Message, Lead
from app.whatsapp import whatsapp_client
from app.agent import agent_manager, sanitize_whatsapp_message
from datetime import datetime

logger = logging.getLogger(__name__)
router = APIRouter(tags=["WhatsApp Webhook"])

# In-memory deduplication set for message IDs
processed_message_ids = set()

# In-memory concurrency locks per phone number to serialize processing
user_locks: Dict[str, asyncio.Lock] = {}

# Live diagnostics store for real-time inspection
webhook_diagnostics = {
    "total_webhooks_received": 0,
    "last_webhook_at": None,
    "last_incoming_message": None,
    "last_agent_response": None,
    "last_meta_dispatch": None
}

@router.get("/api/webhook/status")
async def webhook_status():
    """Live diagnostic endpoint to inspect webhook health, token configuration, and recent events."""
    return {
        "whatsapp_configured": whatsapp_client.is_configured(),
        "whatsapp_token_configured": bool(settings.WHATSAPP_TOKEN),
        "whatsapp_phone_number_id_configured": bool(settings.WHATSAPP_PHONE_NUMBER_ID),
        "groq_configured": bool(settings.GROQ_API_KEY),
        "diagnostics": webhook_diagnostics
    }

async def verify_meta_signature(request: Request) -> bool:
    """Validate that incoming webhook payload matches the Meta App Secret signature."""
    if not settings.WHATSAPP_APP_SECRET:
        # If no secret is configured in environment, skip signature verification
        return True
    signature_header = request.headers.get("X-Hub-Signature-256")
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    signature = signature_header.replace("sha256=", "")
    body = await request.body()
    expected_signature = hmac.new(
        key=settings.WHATSAPP_APP_SECRET.encode(),
        msg=body,
        digestmod=hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected_signature)

@router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge")
):
    """
    Meta WhatsApp Cloud API Webhook Verification Endpoint.
    """
    if hub_mode and hub_verify_token:
        if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN:
            logger.info("WhatsApp Webhook verified successfully!")
            return Response(content=hub_challenge, media_type="text/plain")
        else:
            logger.warning("WhatsApp Webhook verification token mismatch!")
            raise HTTPException(status_code=403, detail="Verification token mismatch")
    raise HTTPException(status_code=400, detail="Missing verification parameters")

async def process_webhook_message_in_background(conversation_id: int, phone: str, user_text: str):
    """
    Background task worker to run the AI agent and reply or generate draft response.
    """
    try:
        if phone not in user_locks:
            user_locks[phone] = asyncio.Lock()

        async with user_locks[phone]:
            # Step 1: Fast, isolated DB read to fetch conversation state and message history
            async with AsyncSessionLocal() as db:
                stmt = select(Conversation).where(Conversation.id == conversation_id)
                res = await db.execute(stmt)
                conv = res.scalar_one_or_none()
                if not conv:
                    return
                ai_is_active = conv.ai_active

                # Fetch recent messages (excluding the last user message to avoid duplication in LLM prompt context)
                history_stmt = select(Message).where(Message.conversation_id == conv.id).order_by(Message.id.desc()).limit(10)
                hist_res = await db.execute(history_stmt)
                history_msgs = list(reversed(hist_res.scalars().all()))

                formatted_hist = [{"sender": m.sender, "body": m.body} for m in history_msgs]
                if formatted_hist and formatted_hist[-1]["sender"] == "user" and formatted_hist[-1]["body"] == user_text:
                    formatted_hist = formatted_hist[:-1]

            # Step 2: Run AI agent outside any DB session to prevent connection starvation
            ai_result = await agent_manager.process_user_message(
                phone=phone,
                user_text=user_text,
                chat_history_messages=formatted_hist
            )

            ai_reply = ai_result.get("response")
            webhook_diagnostics["last_agent_response"] = {
                "phone": phone,
                "reply": ai_reply[:140] if ai_reply else None,
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

            # Step 3: Short write session to persist the message and update state
            async with AsyncSessionLocal() as db:
                stmt = select(Conversation).where(Conversation.id == conversation_id)
                res = await db.execute(stmt)
                conv = res.scalar_one_or_none()
                if not conv:
                    return

                if ai_reply:
                    ai_reply = sanitize_whatsapp_message(ai_reply)

                if conv.ai_active:
                    if ai_reply:
                        conv.ai_draft_reply = None
                        assistant_msg = Message(
                            conversation_id=conv.id,
                            sender="assistant",
                            body=ai_reply,
                            tool_calls_log=", ".join(ai_result.get("tool_logs", []))
                        )
                        db.add(assistant_msg)
                        await db.commit()

                        # Send reply back to user on WhatsApp
                        send_res = await whatsapp_client.send_text_message(phone, ai_reply)
                        webhook_diagnostics["last_meta_dispatch"] = {
                            "phone": phone,
                            "result": send_res,
                            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        logger.info(f"WhatsApp reply sent to {phone}. Result: {send_res}")
                else:
                    # AI is NOT active (Human mode). Generate background draft.
                    if ai_reply:
                        conv.ai_draft_reply = ai_reply
                        await db.commit()
    except Exception as e:
        logger.error(f"Error processing webhook message in background for {phone}: {e}", exc_info=True)

@router.post("/webhook")
async def receive_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Incoming WhatsApp Cloud API event notification handler.
    """
    if settings.WHATSAPP_APP_SECRET:
        if not await verify_meta_signature(request):
            logger.warning("WhatsApp Webhook Signature Verification failed!")
            raise HTTPException(status_code=403, detail="Signature mismatch")

    try:
        body = await request.json()
    except Exception:
        return {"status": "ignored", "reason": "invalid_json"}

    logger.info(f"📩 Webhook event received from Meta: {body}")
    webhook_diagnostics["total_webhooks_received"] += 1
    webhook_diagnostics["last_webhook_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Extract entry & changes
    entries = body.get("entry", [])
    if not entries:
        return {"status": "ok"}

    for entry in entries:
        changes = entry.get("changes", [])
        for change in changes:
            value = change.get("value", {})
            messages = value.get("messages", [])
            contacts = value.get("contacts", [])

            if not messages:
                continue

            contact_name = "Prospect"
            if contacts:
                profile = contacts[0].get("profile", {})
                contact_name = profile.get("name", "Prospect")

            for msg in messages:
                msg_id = msg.get("id")
                if not msg_id or msg_id in processed_message_ids:
                    continue
                processed_message_ids.add(msg_id)

                # Keep deduplication set reasonable size
                if len(processed_message_ids) > 2000:
                    processed_message_ids.clear()

                from_number = msg.get("from", "")
                msg_type = msg.get("type", "text")
                user_text = ""

                if msg_type == "text":
                    user_text = msg.get("text", {}).get("body", "")
                elif msg_type == "interactive":
                    interactive = msg.get("interactive", {})
                    if interactive.get("type") == "button_reply":
                        user_text = interactive.get("button_reply", {}).get("title", "")
                    elif interactive.get("type") == "list_reply":
                        user_text = interactive.get("list_reply", {}).get("title", "")
                elif msg_type == "audio":
                    user_text = "[Voice Note received]"
                elif msg_type == "image":
                    user_text = msg.get("image", {}).get("caption", "[Customer sent an image]")
                else:
                    user_text = f"[{msg_type} message received]"

                if not user_text or not from_number:
                    continue

                webhook_diagnostics["last_incoming_message"] = {
                    "phone": from_number,
                    "name": contact_name,
                    "text": user_text,
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                logger.info(f"📨 Incoming WhatsApp message from {from_number} ({contact_name}): '{user_text}'")

                # Mark message as read on WhatsApp
                await whatsapp_client.mark_message_as_read(msg_id)

                # 1. Get or create conversation record
                stmt = select(Conversation).where(Conversation.phone == from_number)
                res = await db.execute(stmt)
                conv = res.scalar_one_or_none()

                if not conv:
                    conv = Conversation(phone=from_number, customer_name=contact_name, ai_active=True)
                    db.add(conv)
                    await db.flush()
                else:
                    conv.customer_name = contact_name or conv.customer_name

                # 2. Save incoming user message
                user_msg = Message(
                    conversation_id=conv.id,
                    sender="user",
                    body=user_text,
                    media_type=msg_type
                )
                db.add(user_msg)
                await db.commit()

                # 3. Create or update Lead record automatically
                lead_stmt = select(Lead).where(Lead.phone == from_number).order_by(desc(Lead.id)).limit(1)
                lead_res = await db.execute(lead_stmt)
                lead = lead_res.scalars().first()
                if not lead:
                    new_lead = Lead(phone=from_number, name=contact_name, status="new")
                    db.add(new_lead)
                    await db.commit()

                # Check for escalation keywords or phrases (exact word matching to avoid substring collisions)
                import re
                lower_text = user_text.lower()
                escalation_keywords = ["human", "agent", "person", "representative", "manager", "supervisor", "scam", "fraud", "abuse"]
                words = re.findall(r'\b\w+\b', lower_text)
                keyword_match = any(kw in words for kw in escalation_keywords) or "call me" in lower_text

                # Check for loop detection (exclude simulator numbers, raise safety limit to 50)
                user_msgs_stmt = select(Message).where(Message.conversation_id == conv.id, Message.sender == "user")
                user_msgs_res = await db.execute(user_msgs_stmt)
                user_msgs_count = len(user_msgs_res.scalars().all())
                is_simulator = from_number in ["2348012345678", "2348099887766", "2348011223344", "2348099881122"] or from_number.startswith("2348011")
                loop_detected = user_msgs_count >= 50 if not is_simulator else False

                if conv.ai_active and (keyword_match or loop_detected):
                    conv.ai_active = False
                    reason = "Auto-Escalated: Keyword trigger matched." if keyword_match else "Auto-Escalated: Max message exchange loop (10+) reached."
                    conv.handoff_reason = reason
                    await db.commit()

                    # Send notification back on WhatsApp
                    escalation_reply = "I am transferring you directly to a human support advisor right away. They will reply to you here shortly! 📱"
                    assistant_msg = Message(
                        conversation_id=conv.id,
                        sender="assistant",
                        body=escalation_reply,
                        tool_calls_log="auto_escalation_trigger"
                    )
                    db.add(assistant_msg)
                    await db.commit()
                    await whatsapp_client.send_text_message(from_number, escalation_reply)
                    
                else:
                    # Offload agent processing (AI response or human draft generation) to a background task
                    background_tasks.add_task(
                        process_webhook_message_in_background,
                        conv.id,
                        from_number,
                        user_text
                    )

    return {"status": "success"}
