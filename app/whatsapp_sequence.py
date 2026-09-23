import logging
import json
import re
import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Lead, Conversation, Message, WhatsAppLog, ScheduledWhatsAppMessage
from app.whatsapp import whatsapp_client

def strip_asterisks(text: str) -> str:
    return re.sub(r"\*", "", text) if text else ""

logger = logging.getLogger(__name__)


def clean_phone_number(raw_phone: str) -> str:
    """Sanitize phone number to international E.164 without plus sign for WhatsApp Cloud API."""
    if not raw_phone:
        return ""
    digits = re.sub(r"[^\d]", "", raw_phone)
    if digits.startswith("0") and len(digits) == 11:
        digits = "234" + digits[1:]
    elif not digits.startswith("234") and len(digits) == 10:
        digits = "234" + digits
    return digits


def format_whatsapp_cloud_text(text: str) -> str:
    """
    Format and sanitize text strictly according to WhatsApp Cloud API standards:
    1. Single asterisk for bold (*text*), never double (**text**).
    2. Clean unicode bullets (• item), avoiding markdown hyphens or stray asterisks.
    3. Remove raw HTML tags (<p>, <br>, etc.).
    4. Keep within safe message length limits.
    """
    if not text:
        return ""
    # Strip raw HTML tags if any
    cleaned = re.sub(r"<[^>]+>", " ", text)
    # Convert markdown headers (### Header) to bold caps (*HEADER*)
    cleaned = re.sub(r"(?m)^#{1,6}\s*(.*?)$", r"*\1*", cleaned)
    # Convert double or triple asterisks to single asterisks for bold
    cleaned = re.sub(r"\*{2,}([^*\n]+?)\*{2,}", r"*\1*", cleaned)
    # Convert markdown bullets (- item or * item) to clean unicode bullets
    cleaned = re.sub(r"(?m)^\s*[\*\-]\s+", "• ", cleaned)
    # Clean redundant whitespaces
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def generate_personalized_3_step_sequence(
    lead_name: str,
    course_name: Optional[str] = None,
    skill_level: Optional[str] = None,
    notes: Optional[str] = None,
    chat_summary: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Intelligently craft 3 sequential WhatsApp messages tailored to an individual user's
    learning goals, background, and chat interactions with Tara.
    Strictly compliant with Meta WhatsApp Cloud API standards (character limits, clean bolding,
    interactive buttons, and user opt-out disclosures).
    """
    first_name = (lead_name or "there").strip().split()[0]
    course = course_name or "Data Analytics & BI Accelerator"
    level = skill_level or "Beginner"

    # Adapt syllabus highlights based on course
    course_lower = course.lower()
    if "python" in course_lower:
        topic_highlight = "Python programming syntax, Pandas, NumPy, and real data workflows"
        capstone_sample = "Automated Data Extraction & Predictive Customer Churn Pipeline"
    elif "sql" in course_lower:
        topic_highlight = "PostgreSQL, complex joins, window functions, and database reporting"
        capstone_sample = "FinTech Database Query Engine & Financial Metrics Reporting"
    elif "excel" in course_lower:
        topic_highlight = "Advanced formulas, PivotTables, Power Query, and executive dashboards"
        capstone_sample = "Executive Sales & Operations Multi-Department Dashboard"
    elif "power bi" in course_lower:
        topic_highlight = "DAX formulas, dimensional modeling, KPI dashboards, and storytelling"
        capstone_sample = "Enterprise Executive KPI Dashboard & Real-Time Performance Matrix"
    else:
        topic_highlight = "Data cleaning, Excel, SQL queries, Power BI dashboards, and storytelling"
        capstone_sample = "End-to-End Business Performance & Customer Analytics Capstone"

    # =========================================================================
    # MESSAGE 1: Curriculum & Learning Roadmap (Immediate Discovery Follow-up)
    # =========================================================================
    msg1_raw = f"""Hello *{first_name}*! 👋 It's *Tara* from *TekTutors Academy*.

Thank you for chatting with me about our *{course}* program! Here is your personalized learning roadmap based on our discussion:

• *Starting Level:* {level}
• *Key Skills:* {topic_highlight}
• *Format:* Live Weekend Mentorship + 1-on-1 Code & Query Reviews
• *Tuition:* Month-to-month installment at *₦100,000/month* (pay as you learn)

Would you like to review the week-by-week curriculum syllabus or ask me any question?

_(Reply 1 to chat with Tara, or STOP to opt out)_"""

    msg1_text = format_whatsapp_cloud_text(msg1_raw)
    msg1_buttons = [
        {"id": "seq_dl_syllabus", "title": "Download Syllabus"},
        {"id": "seq_ask_tara", "title": "Ask Tara Question"}
    ]

    # =========================================================================
    # MESSAGE 2: Social Proof, Career ROI & Practical Projects (Value Nurture)
    # =========================================================================
    msg2_raw = f"""Hi *{first_name}*! 👋 Checking back in regarding your goals in *{course}*.

Over 70% of TekTutors students started with non-tech backgrounds (banking, marketing, healthcare, administration) and built career-ready confidence through hands-on capstone mentorship:

• *Executive Portfolio:* You will build your own *{capstone_sample}*
• *Live Mentor Debugging:* Dedicated 1-on-1 mentor guidance every weekend
• *Zero Lock-in:* Billed month-to-month so you stay in total control of your budget

Are you planning to transition into tech or upskill in your current workplace?

_(Reply 1 to chat with Tara, or STOP to opt out)_"""

    msg2_text = format_whatsapp_cloud_text(msg2_raw)
    msg2_buttons = [
        {"id": "seq_view_capstones", "title": "View Capstones"},
        {"id": "seq_tuition_breakdown", "title": "Tuition Details"}
    ]

    # =========================================================================
    # MESSAGE 3: Admissions Urgency, Seat Reservation & Free 1-on-1 Call
    # =========================================================================
    msg3_raw = f"""Hello *{first_name}*! 🚀 Our upcoming *{course}* cohort is currently finalizing its mentor pairings!

Because we cap each cohort at *15 students* to guarantee personal 1-on-1 mentor attention, seats fill up quickly:

• *Next Batch:* Kicking off next Saturday
• *Special Benefit:* Free 15-Minute Admissions Discovery Call with our Senior Lead Mentor
• *Action:* Confirm your reservation today before the waitlist opens

Would you like to claim your free 15-minute mentor discovery call or reserve your seat?

_(Reply 1 to chat with Tara, or STOP to opt out)_"""

    msg3_text = format_whatsapp_cloud_text(msg3_raw)
    msg3_buttons = [
        {"id": "seq_book_call", "title": "Book 1-on-1 Call"},
        {"id": "seq_reserve_seat", "title": "Reserve Seat"}
    ]

    return [
        {
            "step": 1,
            "title": "Step 1: Curriculum & Learning Roadmap (Immediate)",
            "body": msg1_text,
            "buttons": msg1_buttons,
            "delay_hours": 0  # Immediate (T+0h)
        },
        {
            "step": 2,
            "title": "Step 2: Social Proof & Capstones (+10 Hours)",
            "body": msg2_text,
            "buttons": msg2_buttons,
            "delay_hours": 10  # 10 hours later (T+10h, 10-hour interval)
        },
        {
            "step": 3,
            "title": "Step 3: Admissions Closing & Mentor Call (+20 Hours)",
            "body": msg3_text,
            "buttons": msg3_buttons,
            "delay_hours": 20  # 20 hours later (T+20h, 10 hours after Step 2, safely within Meta 24h window)
        }
    ]


async def dispatch_whatsapp_message_direct(
    recipient_phone: str,
    recipient_name: str,
    body_text: str,
    buttons: Optional[List[Dict[str, str]]] = None,
    campaign_name: str = "WhatsApp 3-Touch AI Sequence",
    lead_id: Optional[int] = None,
    db: Optional[AsyncSession] = None
) -> Dict[str, Any]:
    """
    Dispatch a single WhatsApp Cloud API message with interactive buttons (or text fallback),
    track response, and record into WhatsAppLog.
    """
    clean_phone = clean_phone_number(recipient_phone)
    if not clean_phone:
        return {"status": "failed", "error": "Invalid recipient phone number format"}

    delivery_status = "delivered"
    delivery_error = None
    api_response = None

    # Enforce WhatsApp Cloud API button constraints: max 3 buttons, title <= 20 chars
    valid_buttons = []
    if buttons:
        for b in buttons[:3]:
            title = b.get("title", "")[:20].strip()
            if title:
                valid_buttons.append({"id": b.get("id", f"btn_{title}"), "title": title})

    try:
        if whatsapp_client.is_configured():
            if valid_buttons:
                api_response = await whatsapp_client.send_interactive_buttons(clean_phone, body_text, valid_buttons)
                # If interactive buttons failed, fallback to plain text with numbered options
                if api_response and api_response.get("error"):
                    button_fallback_text = body_text + "\n\n" + "\n".join([f"🔘 [{b['title']}]" for b in valid_buttons])
                    api_response = await whatsapp_client.send_text_message(clean_phone, button_fallback_text)
            else:
                api_response = await whatsapp_client.send_text_message(clean_phone, body_text)

            if api_response and api_response.get("error"):
                delivery_status = "failed"
                err_obj = api_response.get("error", {})
                err_code = err_obj.get("code") if isinstance(err_obj, dict) else None
                err_msg = err_obj.get("message", "") if isinstance(err_obj, dict) else str(err_obj)

                if err_code == 131047:
                    delivery_error = "Meta 24-hour service window expired (contact has not messaged your WhatsApp bot in the last 24h). Requires pre-approved Meta Template."
                elif err_code == 131030:
                    delivery_error = "Meta Sandbox restriction: phone number not in verified test numbers list (Manage phone number list in Meta Developer Portal)."
                elif err_code == 131026:
                    delivery_error = "Undeliverable by WhatsApp (number may not have an active WhatsApp account or invalid format)."
                else:
                    delivery_error = f"Meta API Error ({err_code or 'N/A'}): {err_msg}"
        else:
            # Simulated environment: successfully delivered to mock client
            delivery_status = "delivered"
            delivery_error = None

    except Exception as e:
        delivery_status = "failed"
        delivery_error = str(e)
        logger.error(f"Error dispatching WhatsApp message to {clean_phone}: {e}")

    # Log into WhatsAppLog
    if db:
        try:
            # Also record in conversation if conversation exists
            conv_stmt = select(Conversation).where(Conversation.phone == clean_phone)
            conv_res = await db.execute(conv_stmt)
            conv = conv_res.scalar_one_or_none()
            if not conv:
                conv = Conversation(phone=clean_phone, customer_name=recipient_name, ai_active=True)
                db.add(conv)
                await db.flush()

            chat_msg = Message(
                conversation_id=conv.id,
                sender="assistant",
                body=body_text + ("\n\n" + "\n".join([f"🔘 [{b['title']}]" for b in valid_buttons]) if valid_buttons else ""),
                media_type="interactive" if valid_buttons else "text"
            )
            if delivery_status == "failed":
                chat_msg.media_type = "failed"
                chat_msg.body = f"[⚠️ WhatsApp Delivery Failed: {delivery_error}]\n\n" + chat_msg.body
            db.add(chat_msg)
            conv.last_message_at = datetime.datetime.now()

            log_entry = WhatsAppLog(
                lead_id=lead_id,
                recipient_phone=clean_phone,
                recipient_name=recipient_name or "Student",
                message_type="sequence",
                campaign_name=campaign_name,
                body=body_text,
                status=delivery_status,
                error_message=delivery_error
            )
            db.add(log_entry)
            await db.commit()
        except Exception as e:
            logger.error(f"Error persisting WhatsAppLog: {e}")

    return {
        "status": delivery_status,
        "phone": clean_phone,
        "name": recipient_name,
        "error": delivery_error,
        "api_response": api_response
    }


async def enroll_lead_in_3_step_sequence(
    db: AsyncSession,
    lead: Lead,
    dispatch_all_now: bool = False
) -> Dict[str, Any]:
    """
    Enroll a user who chatted with Tara into the 3-step intelligently crafted sequence.
    If dispatch_all_now is True, sends all 3 messages immediately for test/instant review.
    Otherwise, sends Step 1 now, and schedules Step 2 and Step 3 into the queue.
    """
    clean_phone = clean_phone_number(lead.phone)
    if not clean_phone:
        return {"status": "error", "message": f"Lead {lead.name} has no valid phone number."}

    steps = generate_personalized_3_step_sequence(
        lead_name=lead.name or "Student",
        course_name=lead.course_interest,
        skill_level=lead.skill_level,
        notes=lead.notes
    )

    now = datetime.datetime.now()
    dispatched_results = []

    for step_data in steps:
        step_num = step_data["step"]
        step_title = step_data["title"]
        body = step_data["body"]
        buttons = step_data["buttons"]
        delay_hrs = step_data["delay_hours"]

        scheduled_time = now + datetime.timedelta(hours=delay_hrs)

        # Check if already scheduled
        existing_stmt = select(ScheduledWhatsAppMessage).where(
            ScheduledWhatsAppMessage.recipient_phone == clean_phone,
            ScheduledWhatsAppMessage.sequence_step == step_num,
            ScheduledWhatsAppMessage.status == "pending"
        )
        existing_res = await db.execute(existing_stmt)
        scheduled_rec = existing_res.scalar_one_or_none()

        if not scheduled_rec:
            scheduled_rec = ScheduledWhatsAppMessage(
                lead_id=lead.id,
                recipient_phone=clean_phone,
                recipient_name=lead.name or "Student",
                sequence_step=step_num,
                step_title=step_title,
                body=body,
                buttons_json=json.dumps(buttons),
                scheduled_for=scheduled_time,
                status="pending"
            )
            db.add(scheduled_rec)
            await db.flush()

        # Decide whether to dispatch immediately
        should_send = dispatch_all_now or (step_num == 1)

        if should_send:
            res = await dispatch_whatsapp_message_direct(
                recipient_phone=clean_phone,
                recipient_name=lead.name or "Student",
                body_text=body,
                buttons=buttons,
                campaign_name=f"WhatsApp 3-Touch AI: {step_title}",
                lead_id=lead.id,
                db=db
            )
            scheduled_rec.status = res["status"]
            scheduled_rec.error_message = res.get("error")
            scheduled_rec.sent_at = datetime.datetime.now()
            dispatched_results.append({
                "step": step_num,
                "title": step_title,
                "status": res["status"],
                "error": res.get("error")
            })
        else:
            dispatched_results.append({
                "step": step_num,
                "title": step_title,
                "status": "queued_pending",
                "scheduled_for": scheduled_time.strftime("%Y-%m-%d %H:%M:%S")
            })

    await db.commit()

    return {
        "status": "success",
        "lead_id": lead.id,
        "lead_name": lead.name,
        "phone": clean_phone,
        "course": lead.course_interest or "Data Analytics",
        "steps": dispatched_results
    }


async def auto_trigger_sequence_for_all_chat_users(
    db: AsyncSession,
    target_audience: str = "all_chat_users",
    dispatch_all_now: bool = True
) -> Dict[str, Any]:
    """
    Automatically identify all users who chatted with Tara and dispatch the 3-step WhatsApp sequence.
    """
    # Find all leads who have active conversations or are in CRM
    stmt = select(Lead)
    if target_audience == "hot":
        stmt = stmt.where(Lead.status == "hot")
    elif target_audience == "qualified":
        stmt = stmt.where(Lead.status.in_(["hot", "qualified"]))
    elif target_audience == "new":
        stmt = stmt.where(Lead.status == "new")

    res = await db.execute(stmt)
    leads = res.scalars().all()

    if not leads:
        # Fallback to any lead in system
        all_res = await db.execute(select(Lead))
        leads = all_res.scalars().all()

    # Deduplicate by phone
    seen_phones = set()
    unique_leads = []
    for l in leads:
        clean = clean_phone_number(l.phone)
        if clean and clean not in seen_phones:
            seen_phones.add(clean)
            unique_leads.append(l)

    results = []
    total_messages_dispatched = 0
    total_delivered = 0
    total_failed = 0

    for lead in unique_leads:
        enroll_res = await enroll_lead_in_3_step_sequence(db, lead, dispatch_all_now=dispatch_all_now)
        for s in enroll_res.get("steps", []):
            if s["status"] in ("delivered", "sent"):
                total_messages_dispatched += 1
                if s["status"] == "delivered":
                    total_delivered += 1
            elif s["status"] == "failed":
                total_messages_dispatched += 1
                total_failed += 1
        results.append(enroll_res)

    return {
        "status": "success",
        "total_leads_targeted": len(unique_leads),
        "total_messages_processed": total_messages_dispatched,
        "delivered_count": total_delivered,
        "failed_count": total_failed,
        "dispatch_all_now": dispatch_all_now,
        "lead_details": results
    }


async def process_due_scheduled_whatsapp_messages(db: AsyncSession) -> Dict[str, Any]:
    """
    Find all scheduled WhatsApp messages whose scheduled_for time has arrived (<= now)
    and status is 'pending', then dispatch them via Meta WhatsApp Cloud API.
    Enforces the 10-hour sequence interval progression automatically.
    """
    now = datetime.datetime.now()
    stmt = select(ScheduledWhatsAppMessage).where(
        ScheduledWhatsAppMessage.status == "pending",
        ScheduledWhatsAppMessage.scheduled_for <= now
    ).order_by(ScheduledWhatsAppMessage.scheduled_for.asc()).limit(50)

    res = await db.execute(stmt)
    due_items = res.scalars().all()

    processed_count = 0
    delivered_count = 0
    failed_count = 0
    dispatched_items = []

    for item in due_items:
        buttons = []
        if item.buttons_json:
            try:
                buttons = json.loads(item.buttons_json)
            except Exception:
                buttons = []

        dispatch_res = await dispatch_whatsapp_message_direct(
            recipient_phone=item.recipient_phone,
            recipient_name=item.recipient_name,
            body_text=item.body,
            buttons=buttons,
            campaign_name=f"WhatsApp 10h Sequence: Step {item.sequence_step}",
            lead_id=item.lead_id,
            db=db
        )

        item.status = dispatch_res["status"]
        item.error_message = dispatch_res.get("error")
        item.sent_at = datetime.datetime.now()

        processed_count += 1
        if dispatch_res["status"] in ("delivered", "sent"):
            delivered_count += 1
        elif dispatch_res["status"] == "failed":
            failed_count += 1

        dispatched_items.append({
            "id": item.id,
            "lead_id": item.lead_id,
            "phone": item.recipient_phone,
            "step": item.sequence_step,
            "status": item.status,
            "error": item.error_message
        })

    if processed_count > 0:
        await db.commit()

    return {
        "status": "success",
        "processed_count": processed_count,
        "delivered_count": delivered_count,
        "failed_count": failed_count,
        "items": dispatched_items
    }

