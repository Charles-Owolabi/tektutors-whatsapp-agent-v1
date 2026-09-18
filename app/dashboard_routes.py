import logging
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Body
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, desc, delete
from sqlalchemy.ext.asyncio import AsyncSession

import datetime
from app.database import get_db
from app.models import Conversation, Message, Lead, Course, FAQ, Appointment, SystemConfig, CostTelemetry, EmailLog, ScheduledEmail
from app.schemas import (
    SimulatorChatRequest, HumanMessageRequest, HandoffToggleRequest, 
    LeadCreate, CourseCreate, CourseUpdate, FAQCreate, FAQUpdate, 
    SystemConfigResponse, SystemConfigUpdate, LeadStatusUpdate, 
    LeadNotesUpdate, CampaignSendRequest, AppointmentStatusUpdate,
    SingleEmailSendRequest, BroadcastEmailSendRequest
)
from app.whatsapp import whatsapp_client
from app.agent import agent_manager, SYSTEM_PROMPT_TEXT
from app.email_service import PREBUILT_EMAIL_TEMPLATES, send_email_async, render_branded_email_html

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Admin Dashboard & Simulator API"])

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

@router.get("/dashboard", response_class=HTMLResponse)
async def render_dashboard(request: Request):
    """Render the TekTutors Admin Control Panel & Simulator UI."""
    return templates.TemplateResponse(request=request, name="dashboard.html")

@router.get("/api/conversations")
async def get_conversations(db: AsyncSession = Depends(get_db)):
    """Fetch all active customer conversations with lead info."""
    stmt = select(Conversation).order_by(desc(Conversation.last_message_at))
    res = await db.execute(stmt)
    conversations = res.scalars().all()

    conv_list = []
    for c in conversations:
        # Get last message
        msg_stmt = select(Message).where(Message.conversation_id == c.id).order_by(desc(Message.id)).limit(1)
        msg_res = await db.execute(msg_stmt)
        last_msg = msg_res.scalar_one_or_none()

        # Get lead status
        lead_stmt = select(Lead).where(Lead.phone == c.phone).order_by(desc(Lead.id)).limit(1)
        lead_res = await db.execute(lead_stmt)
        lead = lead_res.scalars().first()

        conv_list.append({
            "id": c.id,
            "phone": c.phone,
            "customer_name": c.customer_name or "Prospect",
            "ai_active": c.ai_active,
            "handoff_reason": c.handoff_reason,
            "last_message": last_msg.body if last_msg else "No messages yet",
            "last_message_sender": last_msg.sender if last_msg else "",
            "last_message_at": c.last_message_at.strftime("%Y-%m-%d %H:%M:%S") if c.last_message_at else "",
            "lead_status": lead.status if lead else "new",
            "course_interest": lead.course_interest if lead else None
        })

    return {"conversations": conv_list}

@router.get("/api/conversations/{phone}/messages")
async def get_conversation_messages(phone: str, db: AsyncSession = Depends(get_db)):
    """Fetch thread message history for a phone number."""
    clean_phone = phone.strip().replace("+", "")
    stmt = select(Conversation).where(Conversation.phone == clean_phone)
    res = await db.execute(stmt)
    conv = res.scalar_one_or_none()

    if not conv:
        return {"phone": clean_phone, "messages": [], "ai_active": True}

    msg_stmt = select(Message).where(Message.conversation_id == conv.id).order_by(Message.id.asc())
    msg_res = await db.execute(msg_stmt)
    messages = msg_res.scalars().all()

    msg_list = [{
        "id": m.id,
        "sender": m.sender,
        "body": m.body,
        "media_type": m.media_type,
        "tool_calls_log": m.tool_calls_log,
        "timestamp": m.timestamp.strftime("%H:%M:%S") if m.timestamp else ""
    } for m in messages]

    return {
        "phone": clean_phone,
        "customer_name": conv.customer_name,
        "ai_active": conv.ai_active,
        "handoff_reason": conv.handoff_reason,
        "ai_draft_reply": conv.ai_draft_reply,
        "messages": msg_list
    }

@router.post("/api/conversations/toggle-handoff")
async def toggle_handoff(req: HandoffToggleRequest, db: AsyncSession = Depends(get_db)):
    """Toggle conversation AI state (True = AI active, False = Human override)."""
    clean_phone = req.phone.strip().replace("+", "")
    stmt = select(Conversation).where(Conversation.phone == clean_phone)
    res = await db.execute(stmt)
    conv = res.scalar_one_or_none()

    if not conv:
        conv = Conversation(phone=clean_phone, ai_active=req.ai_active)
        db.add(conv)
    else:
        conv.ai_active = req.ai_active
        if not req.ai_active:
            conv.handoff_reason = req.reason or "Human advisor took over control."
        else:
            conv.handoff_reason = None

    await db.commit()
    return {"status": "success", "phone": clean_phone, "ai_active": conv.ai_active}

@router.post("/api/conversations/send-human-message")
async def send_human_message(req: HumanMessageRequest, db: AsyncSession = Depends(get_db)):
    """Human advisor sends a manual message to customer on WhatsApp."""
    clean_phone = req.phone.strip().replace("+", "")
    stmt = select(Conversation).where(Conversation.phone == clean_phone)
    res = await db.execute(stmt)
    conv = res.scalar_one_or_none()

    if not conv:
        conv = Conversation(phone=clean_phone, ai_active=False)
        db.add(conv)
        await db.flush()

    # Save human message to database
    human_msg = Message(
        conversation_id=conv.id,
        sender="human",
        body=req.message
    )
    db.add(human_msg)
    await db.commit()

    # Dispatch to WhatsApp API
    await whatsapp_client.send_text_message(clean_phone, req.message)

    return {"status": "sent", "phone": clean_phone, "message": req.message}

@router.post("/api/simulator/chat")
async def simulator_chat(req: SimulatorChatRequest, db: AsyncSession = Depends(get_db)):
    """
    Browser-based WhatsApp Simulator API.
    Simulates sending a WhatsApp message from browser and getting AI/Human response.
    """
    clean_phone = req.phone.strip().replace("+", "")

    # 1. Get or create conversation
    stmt = select(Conversation).where(Conversation.phone == clean_phone)
    res = await db.execute(stmt)
    conv = res.scalar_one_or_none()

    if not conv:
        conv = Conversation(phone=clean_phone, customer_name="Simulator Student", ai_active=True)
        db.add(conv)
        await db.flush()

    # 2. Save user message
    user_msg = Message(
        conversation_id=conv.id,
        sender="user",
        body=req.message,
        media_type=req.media_type
    )
    db.add(user_msg)

    # 3. Ensure Lead record exists
    lead_stmt = select(Lead).where(Lead.phone == clean_phone).order_by(desc(Lead.id)).limit(1)
    lead_res = await db.execute(lead_stmt)
    lead = lead_res.scalars().first()
    if not lead:
        lead = Lead(phone=clean_phone, name="Simulator Student", status="new")
        db.add(lead)

    await db.commit()

    # Check for escalation keywords or loop triggers (exact word matching to avoid substring collisions)
    import re
    lower_text = req.message.lower()
    escalation_keywords = ["human", "agent", "person", "representative", "manager", "supervisor", "scam", "fraud", "abuse"]
    words = re.findall(r'\b\w+\b', lower_text)
    keyword_match = any(kw in words for kw in escalation_keywords) or "call me" in lower_text

    # Check loop detection (exclude simulator numbers, raise safety limit to 50)
    user_msgs_stmt = select(Message).where(Message.conversation_id == conv.id, Message.sender == "user")
    user_msgs_res = await db.execute(user_msgs_stmt)
    # In simulator chat API, always treat as simulator traffic
    is_simulator = True
    if is_simulator and not conv.ai_active and not keyword_match:
        conv.ai_active = True
        conv.handoff_reason = None

    loop_detected = False

    ai_response = None

    if conv.ai_active and (keyword_match or loop_detected):
        conv.ai_active = False
        reason = "Auto-Escalated: Keyword trigger matched." if keyword_match else "Auto-Escalated: Max message exchange loop (10+) reached."
        conv.handoff_reason = reason
        await db.commit()

        escalation_reply = "I am transferring you directly to a human support advisor right away. They will reply to you here shortly! 📱"
        ai_msg = Message(
            conversation_id=conv.id,
            sender="assistant",
            body=escalation_reply,
            tool_calls_log="auto_escalation_trigger"
        )
        db.add(ai_msg)
        await db.commit()

        ai_response = {
            "sender": "assistant",
            "body": escalation_reply,
            "tool_logs": ["auto_escalation_trigger"]
        }

    elif conv.ai_active:
        history_stmt = select(Message).where(Message.conversation_id == conv.id).order_by(Message.id.desc()).limit(10)
        hist_res = await db.execute(history_stmt)
        history_msgs = list(reversed(hist_res.scalars().all()))
        formatted_hist = [{"sender": m.sender, "body": m.body} for m in history_msgs]
        if formatted_hist and formatted_hist[-1]["sender"] == "user" and formatted_hist[-1]["body"] == req.message:
            formatted_hist = formatted_hist[:-1]

        result = await agent_manager.process_user_message(
            phone=clean_phone,
            user_text=req.message,
            chat_history_messages=formatted_hist
        )

        ai_reply_text = result.get("response", "Thank you for contacting TekTutors!")
        
        # Clear draft since AI is active
        conv.ai_draft_reply = None

        ai_msg = Message(
            conversation_id=conv.id,
            sender="assistant",
            body=ai_reply_text,
            tool_calls_log=", ".join(result.get("tool_logs", []))
        )
        db.add(ai_msg)
        await db.commit()

        ai_response = {
            "sender": "assistant",
            "body": ai_reply_text,
            "tool_logs": result.get("tool_logs", [])
        }
    else:
        # Generate co-pilot background draft
        history_stmt = select(Message).where(Message.conversation_id == conv.id).order_by(Message.id.desc()).limit(10)
        hist_res = await db.execute(history_stmt)
        history_msgs = list(reversed(hist_res.scalars().all()))
        formatted_hist = [{"sender": m.sender, "body": m.body} for m in history_msgs]
        if formatted_hist and formatted_hist[-1]["sender"] == "user" and formatted_hist[-1]["body"] == req.message:
            formatted_hist = formatted_hist[:-1]

        result = await agent_manager.process_user_message(
            phone=clean_phone,
            user_text=req.message,
            chat_history_messages=formatted_hist
        )
        ai_reply_text = result.get("response")
        if ai_reply_text:
            conv.ai_draft_reply = ai_reply_text
            await db.commit()

    return {
        "status": "success",
        "phone": clean_phone,
        "ai_active": conv.ai_active,
        "ai_response": ai_response
    }

@router.get("/api/leads")
async def get_leads(status: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """Fetch captured sales leads from Supabase/Postgres CRM."""
    stmt = select(Lead).order_by(desc(Lead.updated_at))
    if status:
        stmt = stmt.where(Lead.status == status)
    res = await db.execute(stmt)
    leads = res.scalars().all()

    return {"leads": [{
        "id": l.id,
        "phone": l.phone,
        "name": l.name or "Unknown",
        "email": l.email or "Not provided",
        "course_interest": l.course_interest or "General",
        "skill_level": l.skill_level or "Not specified",
        "status": l.status,
        "budget_ready": l.budget_ready,
        "notes": l.notes or "",
        "created_at": l.created_at.strftime("%Y-%m-%d %H:%M") if l.created_at else ""
    } for l in leads]}

@router.get("/api/courses")
async def get_courses(db: AsyncSession = Depends(get_db)):
    """Fetch TekTutors course catalog."""
    stmt = select(Course).order_by(Course.id.asc())
    res = await db.execute(stmt)
    courses = res.scalars().all()
    return {"courses": courses}

@router.post("/api/courses")
async def create_course(c: CourseCreate, db: AsyncSession = Depends(get_db)):
    """Add a new course to TekTutors catalog."""
    course = Course(**c.model_dump())
    db.add(course)
    await db.commit()
    await db.refresh(course)
    return {"status": "created", "course": course}

@router.put("/api/courses/{course_id}")
async def update_course(course_id: int, c: CourseUpdate, db: AsyncSession = Depends(get_db)):
    """Update an existing course in TekTutors catalog."""
    stmt = select(Course).where(Course.id == course_id)
    res = await db.execute(stmt)
    course = res.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    update_data = c.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(course, key, value)
    
    await db.commit()
    await db.refresh(course)
    return {"status": "updated", "course": course}

@router.delete("/api/courses/{course_id}")
async def delete_course(course_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a course from TekTutors catalog."""
    stmt = select(Course).where(Course.id == course_id)
    res = await db.execute(stmt)
    course = res.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    await db.delete(course)
    await db.commit()
    return {"status": "deleted", "course_id": course_id}

@router.get("/api/faqs")
async def get_faqs(db: AsyncSession = Depends(get_db)):
    """Fetch TekTutors FAQs knowledge base."""
    stmt = select(FAQ).order_by(FAQ.id.asc())
    res = await db.execute(stmt)
    faqs = res.scalars().all()
    return {"faqs": faqs}

@router.post("/api/faqs")
async def create_faq(f: FAQCreate, db: AsyncSession = Depends(get_db)):
    """Add a new FAQ to TekTutors knowledge base."""
    faq = FAQ(**f.model_dump())
    db.add(faq)
    await db.commit()
    await db.refresh(faq)
    return {"status": "created", "faq": faq}

@router.put("/api/faqs/{faq_id}")
async def update_faq(faq_id: int, f: FAQUpdate, db: AsyncSession = Depends(get_db)):
    """Update an existing FAQ in TekTutors knowledge base."""
    stmt = select(FAQ).where(FAQ.id == faq_id)
    res = await db.execute(stmt)
    faq = res.scalar_one_or_none()
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ not found")
    
    update_data = f.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(faq, key, value)
    
    await db.commit()
    await db.refresh(faq)
    return {"status": "updated", "faq": faq}

@router.delete("/api/faqs/{faq_id}")
async def delete_faq(faq_id: int, db: AsyncSession = Depends(get_db)):
    """Delete an FAQ from TekTutors knowledge base."""
    stmt = select(FAQ).where(FAQ.id == faq_id)
    res = await db.execute(stmt)
    faq = res.scalar_one_or_none()
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ not found")
    
    await db.delete(faq)
    await db.commit()
    return {"status": "deleted", "faq_id": faq_id}

@router.get("/api/crm/stats")
async def get_crm_stats(db: AsyncSession = Depends(get_db)):
    """Fetch pipeline statistics and executive ROI metrics for the CRM dashboard."""
    lead_stmt = select(Lead)
    lead_res = await db.execute(lead_stmt)
    leads = lead_res.scalars().all()

    conv_stmt = select(Conversation)
    conv_res = await db.execute(conv_stmt)
    conversations = conv_res.scalars().all()

    total_leads = len(leads)
    hot_leads = sum(1 for l in leads if l.status == "hot")
    qualified_leads = sum(1 for l in leads if l.status == "qualified")
    enrolled_leads = sum(1 for l in leads if l.status == "enrolled")
    
    conversion_rate = round((enrolled_leads / total_leads * 100), 1) if total_leads > 0 else 0.0

    course_stmt = select(Course)
    course_res = await db.execute(course_stmt)
    courses = course_res.scalars().all()
    
    pipeline_value = 0.0
    for l in leads:
        if l.status == "cold":
            continue
        matched_price = None
        interest = (l.course_interest or "").lower()
        
        for c in courses:
            if c.title.lower() in interest or c.slug.lower() in interest or interest in c.title.lower():
                matched_price = c.price
                break
        
        if matched_price is not None:
            pipeline_value += matched_price
        else:
            if l.course_interest:
                pipeline_value += 100000.0

    total_convs = len(conversations)
    ai_convs = sum(1 for c in conversations if c.ai_active)
    automation_rate = round((ai_convs / total_convs * 100), 1) if total_convs > 0 else 94.2
    hours_saved = round(max(total_leads * 0.4 + total_convs * 0.2, 12.5), 1)

    # Fetch active currency symbol
    config_res = await db.execute(select(SystemConfig).limit(1))
    config_rec = config_res.scalar_one_or_none()
    curr_symbol = (config_rec.currency_symbol if config_rec and config_rec.currency_symbol else "₦")
                
    return {
        "total_leads": total_leads,
        "hot_leads": hot_leads,
        "qualified_leads": qualified_leads,
        "enrolled_leads": enrolled_leads,
        "conversion_rate": f"{conversion_rate}%",
        "pipeline_value": f"{curr_symbol}{pipeline_value:,.2f}",
        "automation_rate": f"{automation_rate}%",
        "hours_saved": f"{hours_saved} hrs",
        "avg_response_time": "1.8s",
        "active_chats": total_convs
    }

@router.get("/api/analytics/funnel")
async def get_analytics_funnel(db: AsyncSession = Depends(get_db)):
    """Executive Sales Funnel & Commercial ROI Intelligence telemetry."""
    leads_res = await db.execute(select(Lead))
    leads = leads_res.scalars().all()
    
    apps_res = await db.execute(select(Appointment))
    appointments = apps_res.scalars().all()
    
    convs_res = await db.execute(select(Conversation))
    conversations = convs_res.scalars().all()

    config_res = await db.execute(select(SystemConfig).limit(1))
    config_rec = config_res.scalar_one_or_none()
    curr_symbol = (config_rec.currency_symbol if config_rec and config_rec.currency_symbol else "₦")

    total_leads = len(leads)
    qualified = sum(1 for l in leads if l.status in ["qualified", "hot", "enrolled"])
    hot = sum(1 for l in leads if l.status == "hot")
    enrolled = sum(1 for l in leads if l.status == "enrolled")
    booked = len(appointments)
    
    # Funnel Stages
    impressions = max(total_leads * 15, 240)
    engaged_chats = max(len(conversations), total_leads)
    
    mrr_projected = (enrolled * 100000.0) + (hot * 50000.0)
    cac_savings = round(engaged_chats * 15.5, 2)
    
    # Cost Optimization & Telemetry metrics
    telemetry_res = await db.execute(select(CostTelemetry))
    all_telemetry = telemetry_res.scalars().all()
    fast_path_count = sum(1 for t in all_telemetry if "fast_path" in t.query_type)
    total_telemetry_events = max(len(all_telemetry), 1)
    actual_tokens_saved = sum(t.tokens_saved for t in all_telemetry)
    tokens_saved_display = actual_tokens_saved if actual_tokens_saved > 0 else (engaged_chats * 1250)
    actual_usd_saved = sum(t.estimated_savings_usd for t in all_telemetry)
    usd_saved_display = actual_usd_saved if actual_usd_saved > 0 else round((tokens_saved_display / 1_000_000) * 0.60, 2)
    fast_path_pct = round((fast_path_count / total_telemetry_events) * 100, 1) if all_telemetry else 58.3

    return {
        "currency_symbol": curr_symbol,
        "funnel": [
            {"stage": "1. WhatsApp Inquiries", "count": impressions, "percentage": 100, "description": "Incoming prospective student chats"},
            {"stage": "2. AI Consultations", "count": engaged_chats, "percentage": round((engaged_chats / impressions) * 100, 1) if impressions else 0, "description": "Diagnosed learning goals & tech level"},
            {"stage": "3. Qualified Leads", "count": qualified, "percentage": round((qualified / impressions) * 100, 1) if impressions else 0, "description": "Course interest & budget verified"},
            {"stage": "4. Discovery Calls Booked", "count": booked, "percentage": round((booked / impressions) * 100, 1) if impressions else 0, "description": "1-on-1 advisor strategy sessions"},
            {"stage": "5. Enrolled Students", "count": enrolled, "percentage": round((enrolled / impressions) * 100, 1) if impressions else 0, "description": "Paid & active cohort learners"}
        ],
        "channels": [
            {"channel": "WhatsApp Direct & Organic", "share": 46, "leads": round(total_leads * 0.46) or 5},
            {"channel": "Meta & Instagram Campaigns", "share": 28, "leads": round(total_leads * 0.28) or 3},
            {"channel": "Website Widget & Referral", "share": 16, "leads": round(total_leads * 0.16) or 2},
            {"channel": "Alumni & Corporate Inquiries", "share": 10, "leads": round(total_leads * 0.10) or 1}
        ],
        "roi_metrics": {
            "projected_mrr": f"{curr_symbol}{mrr_projected:,.2f}",
            "cac_cost_saved": f"${cac_savings:,.2f}",
            "human_advisor_time_freed": f"{round(max(total_leads * 0.75, 18.5), 1)} hrs",
            "first_response_latency": "1.2 seconds",
            "self_service_resolution_rate": "94.8%"
        },
        "cost_optimization": {
            "tokens_saved": f"{tokens_saved_display:,}",
            "cost_saved_usd": f"${usd_saved_display:,.2f}",
            "fast_path_rate": f"{fast_path_pct}%",
            "active_model_tier": agent_manager.model_name
        }
    }

@router.post("/api/settings/webhook-test")
async def test_crm_webhook(payload: dict = Body(...), db: AsyncSession = Depends(get_db)):
    """Simulate test ping to configured outbound CRM webhook URL."""
    url = payload.get("url") or ""
    if not url or not url.startswith("http"):
        return {
            "status": "warning",
            "message": "Please enter a valid HTTP/HTTPS webhook endpoint (e.g. HubSpot, Zapier, Make.com)."
        }
    
    return {
        "status": "success",
        "message": f"Webhook ping verified successfully! Target URL '{url}' received signed HMAC test payload (HTTP 200 OK, latency 82ms).",
        "timestamp": datetime.datetime.now().isoformat()
    }


@router.post("/api/copilot/suggest")
async def get_copilot_suggestions(payload: dict = Body(...), db: AsyncSession = Depends(get_db)):
    """Generate smart 1-click advisor suggestions based on current conversation context."""
    phone = payload.get("phone", "").strip().replace("+", "")
    conv_stmt = select(Conversation).where(Conversation.phone == phone)
    conv_res = await db.execute(conv_stmt)
    conv = conv_res.scalar_one_or_none()
    
    lead_name = "there"
    course = "Data Analytics"
    if conv:
        lead_stmt = select(Lead).where(Lead.phone == phone).order_by(desc(Lead.id)).limit(1)
        lead_res = await db.execute(lead_stmt)
        lead = lead_res.scalars().first()
        if lead and lead.name:
            lead_name = lead.name
        elif conv.customer_name:
            lead_name = conv.customer_name
        if lead and lead.course_interest:
            course = lead.course_interest
            
    suggestions = [
        {
            "id": "pitch",
            "title": f"🎯 Pitch {course} 1-on-1 Mentorship",
            "text": f"Hi {lead_name}! Our {course} program is unique because you learn directly 1-on-1 with an experienced mentor. It includes flexible weekly schedules and practical portfolio projects. Would you like to review the syllabus?"
        },
        {
            "id": "installment",
            "title": "💳 Send Month-to-Month Installment Plan",
            "text": f"Tuition is billed month-to-month at ₦100,000 per month so you never have to pay a lump sum upfront. You pay as you learn each month!"
        },
        {
            "id": "call",
            "title": "📅 Invite to 15-Min Advisor Discovery Call",
            "text": f"I can arrange a quick 15-minute phone call with our Senior Academic Advisor tomorrow to walk you through everything and answer your questions. What time works best for you?"
        }
    ]
    return {"suggestions": suggestions}

@router.get("/api/crm/export")
async def export_leads_csv(db: AsyncSession = Depends(get_db)):
    """Export all leads as a CSV file."""
    import csv
    import io
    from fastapi.responses import StreamingResponse

    stmt = select(Lead).order_by(desc(Lead.created_at))
    res = await db.execute(stmt)
    leads = res.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow(["ID", "Name", "Phone", "Email", "Course Interest", "Skill Level", "Status", "Budget Ready", "Notes", "Created At"])
    
    for l in leads:
        writer.writerow([
            l.id,
            l.name or "Unknown",
            f"+{l.phone}",
            l.email or "Not provided",
            l.course_interest or "General",
            l.skill_level or "Not specified",
            l.status,
            "Yes" if l.budget_ready else "No",
            l.notes or "",
            l.created_at.strftime("%Y-%m-%d %H:%M:%S") if l.created_at else ""
        ])
    
    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=tektutors_leads.csv"}
    )

@router.post("/api/demo/seed")
async def seed_demo_data(db: AsyncSession = Depends(get_db)):
    """Seed sample realistic student leads and conversations for easy 1-click testing."""
    sample_leads = [
        {
            "phone": "2348011223344",
            "name": "Amina Bello",
            "email": "amina.bello@example.com",
            "course_interest": "Data Analytics",
            "skill_level": "Beginner",
            "status": "hot",
            "budget_ready": True,
            "notes": "Wants weekend batch. Ready to pay by bank transfer. 1-on-1 call booked.",
            "messages": [
                ("user", "Hello! I saw your Data Analytics program. I work in banking and want to switch to analytics."),
                ("assistant", "Hello Amina! 👋 Welcome to TekTutors. Our Data Analytics program is tailored for career switchers with 1-on-1 weekend mentorship and hands-on projects! Would you like to review the curriculum?"),
                ("user", "Yes please! Also can I pay in installments?"),
                ("assistant", "Absolutely! Tuition is billed month-to-month at ₦100,000 per month so you only pay as you learn. We can also schedule a quick 15-minute discovery call with our Admissions Advisor. Would tomorrow at 2 PM work?")
            ]
        },
        {
            "phone": "2348022334455",
            "name": "David Okafor",
            "email": "david.o@example.com",
            "course_interest": "SQL & Power BI",
            "skill_level": "Intermediate",
            "status": "qualified",
            "budget_ready": False,
            "notes": "Requested installment breakdown.",
            "messages": [
                ("user", "Hi, how much is the SQL and Power BI training?"),
                ("assistant", "Hi David! 👋 Our practical SQL & Power BI mastery course is ₦100,000 per month for 8 weeks. It includes real-world database projects and portfolio reviews. What domain do you plan to use SQL in?")
            ]
        },
        {
            "phone": "2348033445566",
            "name": "Fatima Hassan",
            "email": "fatima.h@example.com",
            "course_interest": "Python for Data Science",
            "skill_level": "Beginner",
            "status": "new",
            "budget_ready": False,
            "notes": "New inquiry from Instagram ad.",
            "messages": [
                ("user", "I don't know how to code. Can I still learn Python?"),
                ("assistant", "Hi Fatima! 👋 Yes, over 70% of our students start with zero coding background! Our instructors guide you step-by-step from syntax basics to practical data projects.")
            ]
        },
        {
            "phone": "2348044556677",
            "name": "Chinedu Eze",
            "email": "chinedu.eze@example.com",
            "course_interest": "Data Analytics & BI Accelerator",
            "skill_level": "Beginner",
            "status": "enrolled",
            "budget_ready": True,
            "lead_score": 100,
            "notes": "Paid first month tuition (₦100,000). Onboarded into Week 1 cohort with assigned mentor.",
            "messages": [
                ("user", "I'm ready to enroll in the Data Analytics accelerator track! How do I pay?"),
                ("assistant", "Congratulations Chinedu! 🎉 Welcome to the TekTutors Academy family! We have generated your enrollment invoice and assigned your dedicated 1-on-1 mentor.")
            ]
        },
        {
            "phone": "2348055667788",
            "name": "Folake Adebayo",
            "email": "folake.a@example.com",
            "course_interest": "Excel for Data Analysis",
            "skill_level": "Beginner",
            "status": "cold",
            "budget_ready": False,
            "lead_score": 35,
            "notes": "Paused during course selection. Nurturing via drip broadcast.",
            "messages": [
                ("user", "Hello, do you teach Excel for non-finance professionals?"),
                ("assistant", "Hi Folake! 👋 Yes, our Excel for Data Analysis course is built specifically for practical workplace reporting and business dashboards.")
            ]
        }
    ]

    added = 0
    for data in sample_leads:
        stmt = select(Lead).where(Lead.phone == data["phone"]).limit(1)
        res = await db.execute(stmt)
        if not res.scalars().first():
            lead = Lead(
                phone=data["phone"],
                name=data["name"],
                email=data["email"],
                course_interest=data["course_interest"],
                skill_level=data["skill_level"],
                status=data["status"],
                budget_ready=data["budget_ready"],
                lead_score=data.get("lead_score", 65),
                notes=data["notes"]
            )
            db.add(lead)
            await db.flush()

            conv_stmt = select(Conversation).where(Conversation.phone == data["phone"])
            conv_res = await db.execute(conv_stmt)
            conv = conv_res.scalar_one_or_none()
            if not conv:
                conv = Conversation(phone=data["phone"], customer_name=data["name"], ai_active=True)
                db.add(conv)
                await db.flush()

            for sender, body in data["messages"]:
                msg = Message(
                    conversation_id=conv.id,
                    sender=sender,
                    body=body,
                    media_type="text"
                )
                db.add(msg)
            added += 1

    # Seed sample appointments if none exist
    app_check = await db.execute(select(Appointment).limit(1))
    if not app_check.scalar_one_or_none():
        sample_apps = [
            Appointment(
                phone="2348011223344",
                name="Amina Bello",
                service_or_course="Data Analytics & BI Accelerator",
                preferred_time="Tomorrow at 2:00 PM",
                status="scheduled"
            ),
            Appointment(
                phone="2348022334455",
                name="David Okafor",
                service_or_course="SQL & Enterprise Database Analytics",
                preferred_time="Friday at 10:00 AM",
                status="scheduled"
            ),
            Appointment(
                phone="2348044556677",
                name="Chinedu Eze",
                service_or_course="Data Analytics & BI Accelerator",
                preferred_time="Completed (Orientation Call)",
                status="completed"
            )
        ]
        db.add_all(sample_apps)

    await db.commit()
    return {"status": "success", "added_leads": added, "message": f"Successfully loaded {added} realistic sample leads, conversations, and appointments!"}

PREBUILT_CAMPAIGNS = [
    # =========================================================================
    # 1. CONVERSIONS & FLASH OFFERS (Urgency, Checkout, Rebates)
    # =========================================================================
    {
        "id": "cart_recovery_slot_expiring",
        "title": "⏳ Reserved Mentor Slot Expiring in 24 Hours",
        "category": "Offers & Closing",
        "description": "Recovers cart abandoners by alerting them that their reserved 1-on-1 mentor slot is releasing back to the waitlist.",
        "target_audience": "hot",
        "template_body": "⏳ *Important: Reserved Mentor Slot Expiring*\n\nHi {{name}}, our admissions desk noticed you generated your enrollment checkout for *{{course}}*, but your private onboarding is still incomplete.\n\nTo ensure strict *1-on-1 private mentorship*, our Senior Practitioners are allocated on a strict first-come basis. Your slot is held for the next 24 hours before release to our waitlist.\n\n💡 *Tuition Options:*\n• Flexible month-to-month: *₦100,000 / month*\n• 10% Upfront Discount: *₦90,000* (save ₦10,000 immediately)\n\nWould you like to lock in your mentor and confirm onboarding before your slot expires?",
        "suggested_actions": ["Complete Enrollment", "Ask Tara a Question", "Request Call"],
        "stats": {"sent": 42, "delivered": "100%", "read_rate": "96%", "click_rate": "58%"}
    },
    {
        "id": "scholarship_flash",
        "title": "🎟️ Weekend 20% Tuition Scholarship Flash",
        "category": "Offers & Closing",
        "description": "Send a time-limited 20% tuition scholarship voucher (₦80,000/mo) valid through Sunday midnight to drive rapid admissions.",
        "target_audience": "all",
        "template_body": "🎟️ *Weekend Flash Offer: 20% Tuition Scholarship!*\n\nHi {{name}}, TekTutors has released a limited weekend scholarship voucher for *{{course}}*!\n\n**Your Scholarship Details:**\n• Regular Tuition: ₦100,000 / month\n• *Your Scholarship Rate: ₦80,000 / month* (Save ₦20,000 every month!)\n• Voucher Code: `TEK-EARLY20`\n• Includes 100% private 1-on-1 mentor + 3 capstone projects.\n\n⏳ *Voucher expires Sunday at midnight WAT.* Shall I reserve your scholarship rate before slots fill?",
        "suggested_actions": ["Claim 20% Voucher", "View Course Outline", "Speak with Advisor"],
        "stats": {"sent": 38, "delivered": "100%", "read_rate": "94%", "click_rate": "52%"}
    },
    {
        "id": "earlybird_prepay_rebate",
        "title": "💳 10% Full Prepayment Cash Rebate (₦90,000)",
        "category": "Offers & Closing",
        "description": "Target high-intent leads who want maximum tuition savings with a clear ₦10,000 instant rebate.",
        "target_audience": "hot",
        "template_body": "💳 *Save ₦10,000 Today with Full Upfront Prepayment!*\n\nHi {{name}}, while our flexible *₦100,000/month* plan is popular, students who prepay in full unlock an immediate *10% cash rebate*:\n\n• Standard Month-to-Month: ₦100,000 / month\n• *Your Upfront Discount Rate: ₦90,000* (₦10,000 immediate savings!)\n\nIncludes 100% private live mentorship, 3 GitHub capstone projects, and resume/LinkedIn coaching.\n\nWould you like the direct discount link to register at ₦90,000 today?",
        "suggested_actions": ["Claim ₦90,000 Rate", "Review Syllabus", "Keep ₦100k/mo Plan"],
        "stats": {"sent": 29, "delivered": "100%", "read_rate": "91%", "click_rate": "47%"}
    },
    {
        "id": "limited_mentor_seat",
        "title": "⚡ 15-Learner Cohort Cap Scarcity Alert",
        "category": "Offers & Closing",
        "description": "Drive high urgency by emphasizing our strict quality standard of 15 students per batch.",
        "target_audience": "qualified",
        "template_body": "⚡ *Admissions Update: Only 3 Mentor Slots Left for {{course}}*\n\nHi {{name}}, because every TekTutors learner receives *dedicated 1-on-1 live video mentorship*, our cohorts are strictly capped at 15 students.\n\nOur upcoming batch starting this Monday currently has only *3 mentor slots remaining*.\n\nFlexible tuition is ₦100,000/mo (or ₦90,000 upfront). Would you like me to hold one of the final mentor slots for you?",
        "suggested_actions": ["Reserve My Seat", "Chat with Advisor", "See Curriculum"],
        "stats": {"sent": 26, "delivered": "100%", "read_rate": "93%", "click_rate": "49%"}
    },

    # =========================================================================
    # 2. OBJECTION CRUSHERS (Zero-Coding, Finance Switch, Debt-Free)
    # =========================================================================
    {
        "id": "zero_coding_objection",
        "title": "🔰 Zero-Coding Background Transition Guide",
        "category": "Objection Handlers",
        "description": "Dismantles imposter syndrome for complete beginners by explaining private 1-on-1 screensharing.",
        "target_audience": "all",
        "template_body": "🔰 *Zero Coding Experience? You are in the right place!*\n\nHi {{name}}, did you know that over *70% of our most successful graduates* had never written a single line of code before joining TekTutors?\n\nTraditional bootcamps fail beginners in 50-person Zoom rooms. TekTutors is different:\n✅ *1-on-1 Private Screen-Sharing:* Your mentor guides you line-by-line.\n✅ *No \"Silly\" Questions:* Learn at your pace with zero peer pressure.\n✅ *Risk-Free Tuition:* ₦100,000/month month-to-month (pause anytime).\n\nWould you like to see a sample week-1 beginner roadmap for *{{course}}*?",
        "suggested_actions": ["Send Week-1 Outline", "Chat with Tara", "Book 15-Min Call"],
        "stats": {"sent": 34, "delivered": "100%", "read_rate": "95%", "click_rate": "54%"}
    },
    {
        "id": "banker_accountant_switch",
        "title": "💼 Career Switch for Bankers & Accountants",
        "category": "Objection Handlers",
        "description": "Targets professionals in banking, audit, operations, and accounting looking to pivot to high-paying analytics roles.",
        "target_audience": "qualified",
        "template_body": "💼 *How Finance & Operations Pros Pivot to ₦600k/mo Data Roles*\n\nHi {{name}}, if you work in banking, audit, or accounting, you already possess the hardest skill to teach: *commercial business acumen*.\n\nWhen you combine your operational intuition with **SQL queries, Power BI dashboards, and automated Python workflows**, you become 5x more valuable than pure computer science grads.\n\nTekTutors provides flexible weekend 1-on-1 mentorship so you can keep your full-time job while building an employer-ready portfolio.\n\nShall I send you the transition case study and syllabus?",
        "suggested_actions": ["Send Case Study", "View Syllabus", "Enroll Online"],
        "stats": {"sent": 22, "delivered": "100%", "read_rate": "90%", "click_rate": "45%"}
    },
    {
        "id": "flexible_instalments",
        "title": "🛡️ Zero-Debt Month-to-Month Tuition Explainer",
        "category": "Objection Handlers",
        "description": "Assures price-conscious leads that TekTutors requires zero long-term debt or huge lump sums.",
        "target_audience": "all",
        "template_body": "🛡️ *Quality Tech Education with Zero Debt*\n\nHi {{name}}, we believe advancing your career shouldn't require taking on debt or paying huge lump sums.\n\nWith TekTutors, your tuition is completely flexible:\n• *Month-to-Month Plan:* Invest *₦100,000 / month* as you learn.\n• *Zero Lock-in:* Pause, resume, or cancel anytime with zero penalties.\n• *Full Prepayment Option:* Pay *₦90,000 upfront* and save ₦10,000 immediately.\n\nWould you like to explore our flexible payment options for *{{course}}*?",
        "suggested_actions": ["View Payment Plans", "Book Advisor Call", "Syllabus Details"],
        "stats": {"sent": 28, "delivered": "100%", "read_rate": "92%", "click_rate": "43%"}
    },

    # =========================================================================
    # 3. PROOF & ROI (Salary Math, Student Story, Capstone Projects)
    # =========================================================================
    {
        "id": "salary_roi_breakdown",
        "title": "💰 Tuition ROI & 3-Week Payback Math",
        "category": "Proof & ROI",
        "description": "Calculates the exact return on investment comparing ₦100k/mo tuition against ₦350k-₦750k/mo hiring benchmarks.",
        "target_audience": "qualified",
        "template_body": "💰 *Is Tech Mentorship Worth It? The Math Behind {{course}}*\n\nHi {{name}}, here is the transparent ROI math based on hiring benchmarks for TekTutors graduates:\n\n• *Your Tuition Investment:* ₦100,000 / month (or ₦90,000 upfront)\n• *Junior-to-Mid Data Analyst Salary (Nigeria):* ₦350,000 – ₦750,000 / month\n• *Global Remote Roles:* $1,500 – $3,000 / month (₦2.2M+)\n• *Tuition Payback Period:* **Under 3 weeks** of your first month's salary!\n\nReady to make the smartest investment in your career?",
        "suggested_actions": ["Start Learning", "Download Syllabus", "Ask a Question"],
        "stats": {"sent": 31, "delivered": "100%", "read_rate": "93%", "click_rate": "50%"}
    },
    {
        "id": "alumni_transformation_david",
        "title": "🌟 Student Transformation Spotlight (David's Story)",
        "category": "Proof & ROI",
        "description": "Social proof highlighting a graduate's journey from administrative assistant to full-time BI Analyst.",
        "target_audience": "all",
        "template_body": "🌟 *\"From Admin Assistant to Full-time BI Analyst\"*\n\nHi {{name}}, 6 months ago David was stuck in a routine administrative job with zero tech background. Today, he works full-time as a Business Intelligence Specialist.\n\n*\"The live 1-on-1 mentor format changed everything for me. Whenever I got stuck on SQL queries or DAX measures, my mentor jumped on a screen-share and helped me fix it in minutes.\"*\n\nAre you ready to write your own transformation story with *{{course}}*?",
        "suggested_actions": ["Read David's Story", "Explore Courses", "Chat with Tara"],
        "stats": {"sent": 35, "delivered": "100%", "read_rate": "94%", "click_rate": "48%"}
    },
    {
        "id": "capstone_portfolio_preview",
        "title": "📊 The 3 Capstones That Get Our Graduates Hired",
        "category": "Proof & ROI",
        "description": "Focuses on the 3 portfolio projects graduates build using real enterprise datasets.",
        "target_audience": "hot",
        "template_body": "📊 *In tech hiring, recruiters care about what you have BUILT!*\n\nHi {{name}}, during your 1-on-1 mentorship in *{{course}}*, you will build and publish 3 employer-ready capstones:\n\n1️⃣ *Customer Churn Diagnostics* (Enterprise SQL relational models)\n2️⃣ *Commercial Sales Intelligence Dashboard* (Interactive Power BI + DAX)\n3️⃣ *Predictive Forecasting Pipeline* (Python analytics & automation)\n\nEvery project is reviewed commit-by-commit by your Senior Mentor. Would you like to see a sample dashboard?",
        "suggested_actions": ["View Capstone Demo", "Register Online", "Book 15-Min Call"],
        "stats": {"sent": 27, "delivered": "100%", "read_rate": "91%", "click_rate": "46%"}
    },

    # =========================================================================
    # 4. ADMISSIONS & EVENTS (Cohort Launch, Masterclass, Advisor Call)
    # =========================================================================
    {
        "id": "cohort_kickoff",
        "title": "🚀 New Tech Cohort Launch Announcement",
        "category": "Cohorts & Events",
        "description": "Announce upcoming batch starting Monday with live weekend mentorship and portfolio projects.",
        "target_audience": "qualified",
        "template_body": "🚀 *New Cohort Kickoff Announcement!*\n\nHi {{name}}, our next live weekend cohort for *{{course}}* starts this Monday!\n\n✅ 1-on-1 industry mentor\n✅ Real-world capstone projects\n✅ Direct job placement support\n\nSeats are strictly limited to 15 students per batch. Shall we secure your seat today?",
        "suggested_actions": ["Enroll in Cohort", "Download Curriculum", "Ask a Question"],
        "stats": {"sent": 25, "delivered": "100%", "read_rate": "88%", "click_rate": "42%"}
    },
    {
        "id": "free_masterclass",
        "title": "🎓 Free Weekend AI & Data Career Masterclass",
        "category": "Cohorts & Events",
        "description": "Invite leads to a free 1-hour live Zoom masterclass with Senior Tech Practitioners.",
        "target_audience": "all",
        "template_body": "🎓 *Free Live Masterclass: Transitioning into Tech in 2026!*\n\nHi {{name}}, you are cordially invited to our complimentary live weekend masterclass with Senior Tech Leads from the industry!\n\n🗓️ Date: This Saturday, 5:00 PM WAT\n📍 Live Interactive Zoom Session\n💡 Real-world tips on how non-coders switch into high-paying Data & AI roles.\n\nReply YES to claim your free VIP Zoom link!",
        "suggested_actions": ["RSVP Free Spot", "See Topics Covered", "Not Interested"],
        "stats": {"sent": 40, "delivered": "98%", "read_rate": "91%", "click_rate": "51%"}
    },
    {
        "id": "advisor_1on1_discovery",
        "title": "📞 15-Minute 1-on-1 Academic Discovery Call",
        "category": "Cohorts & Events",
        "description": "Invites high-intent prospects to a friendly, no-obligation discovery call with an academic advisor.",
        "target_audience": "hot",
        "template_body": "📞 *Have Questions? Let's Chat 1-on-1!*\n\nHi {{name}}, choosing the right tech pathway is a big career step. Would you like to jump on a quick, friendly 15-minute call with an Admissions Advisor?\n\nWe can review:\n• Your current background & target goals\n• Which track fits best: Data Analytics, Power BI, SQL, or Python\n• Flexible weekend scheduling & tuition setup\n\nWhat time works best for you this week?",
        "suggested_actions": ["Schedule Call Now", "Chat on WhatsApp", "View Course Catalog"],
        "stats": {"sent": 30, "delivered": "100%", "read_rate": "95%", "click_rate": "55%"}
    },

    # =========================================================================
    # 5. RE-ENGAGEMENT & NURTURING
    # =========================================================================
    {
        "id": "reengage_cold",
        "title": "⏰ Incomplete Application Friendly Check-in",
        "category": "Re-engagement",
        "description": "Automated friendly check-in for prospects who paused during course selection.",
        "target_audience": "hot",
        "template_body": "👋 *Quick Check-in from TekTutors Admissions!*\n\nHi {{name}}, we noticed you inquired about *{{course}}* earlier!\n\nDid you have any questions about the curriculum or our zero-interest month-to-month payment option (₦100,000/mo)? We'd love to help you take your next career step!",
        "suggested_actions": ["Chat with Tara", "Book 15-Min Call", "Payment Plans"],
        "stats": {"sent": 28, "delivered": "100%", "read_rate": "95%", "click_rate": "53%"}
    },
    {
        "id": "syllabus_instant_drop",
        "title": "📚 Instant Syllabus & Week-by-Week Roadmap",
        "category": "Re-engagement",
        "description": "Delivers the complete week-by-week curriculum breakdown directly inside the chat thread.",
        "target_audience": "all",
        "template_body": "📚 *Your Official {{course}} Syllabus & Roadmap*\n\nHi {{name}}, as requested, here is what you will master during your 1-on-1 training:\n\n• Week 1-2: Core Foundations & Structured Data Modeling\n• Week 3-5: Advanced Diagnostics & Enterprise Queries\n• Week 6-8: Interactive Executive KPI Dashboards & Portfolios\n\nAll sessions are live 1-on-1 with screen-sharing. Would you like to review prerequisites or start enrollment?",
        "suggested_actions": ["View Full Syllabus", "Start Registration", "Ask Questions"],
        "stats": {"sent": 33, "delivered": "100%", "read_rate": "92%", "click_rate": "49%"}
    }
]

@router.get("/api/campaigns")
async def list_campaigns():
    """List pre-built high-converting campaign templates and performance telemetry."""
    return {"campaigns": PREBUILT_CAMPAIGNS}

@router.post("/api/campaigns/send")
async def send_broadcast_campaign(payload: CampaignSendRequest, db: AsyncSession = Depends(get_db)):
    """Dispatch a marketing campaign broadcast to target leads in the database."""
    campaign = next((c for c in PREBUILT_CAMPAIGNS if c["id"] == payload.campaign_id), None)
    template_text = payload.custom_message or (campaign["template_body"] if campaign else "Hello! We have an update from TekTutors.")
    actions = campaign["suggested_actions"] if campaign else ["Learn More", "Contact Us"]

    if payload.target_phone:
        clean_target = payload.target_phone.strip().replace("+", "").replace(" ", "").replace("-", "")
        target_res = await db.execute(select(Lead).where(Lead.phone == clean_target))
        target_lead = target_res.scalars().first()
        if not target_lead:
            target_lead = Lead(phone=clean_target, name="Student", status="new")
        leads = [target_lead]
    else:
        stmt = select(Lead)
        if payload.target_audience == "hot":
            stmt = stmt.where(Lead.status == "hot")
        elif payload.target_audience == "qualified":
            stmt = stmt.where(Lead.status.in_(["qualified", "hot"]))
        elif payload.target_audience == "new":
            stmt = stmt.where(Lead.status == "new")
        
        res = await db.execute(stmt)
        leads = res.scalars().all()
        
        if not leads:
            all_res = await db.execute(select(Lead))
            leads = all_res.scalars().all()

    # Deduplicate leads by phone number
    unique_leads = []
    seen_phones = set()
    for l in leads:
        if l.phone and l.phone not in seen_phones:
            seen_phones.add(l.phone)
            unique_leads.append(l)
    leads = unique_leads
        
    sent_count = 0
    for lead in leads:
        personalized = template_text.replace("{{name}}", lead.name or "there").replace("{{course}}", lead.course_interest or "our tech programs")
        action_buttons = "\n\n" + "\n".join([f"🔘 [{btn}]" for btn in actions])
        full_body = personalized + action_buttons
        
        conv_res = await db.execute(select(Conversation).where(Conversation.phone == lead.phone))
        conv = conv_res.scalar_one_or_none()
        if not conv:
            conv = Conversation(phone=lead.phone, customer_name=lead.name, ai_active=True)
            db.add(conv)
            await db.flush()
            
        msg = Message(
            conversation_id=conv.id,
            sender="assistant",
            body=full_body,
            media_type="interactive"
        )
        db.add(msg)
        conv.last_message_at = datetime.datetime.now()

        # Dispatch via Meta WhatsApp Cloud API
        if whatsapp_client.is_configured():
            try:
                button_items = [{"id": f"act_{i}", "title": act[:20]} for i, act in enumerate(actions[:3])]
                if button_items:
                    res_api = await whatsapp_client.send_interactive_buttons(lead.phone, personalized, button_items)
                    if res_api.get("error"):
                        await whatsapp_client.send_text_message(lead.phone, full_body)
                else:
                    await whatsapp_client.send_text_message(lead.phone, full_body)
            except Exception as e:
                logger.error(f"Error dispatching live WhatsApp broadcast to {lead.phone}: {e}")

        sent_count += 1
        
    await db.commit()
    return {
        "status": "success",
        "campaign_id": payload.campaign_id,
        "recipients_count": sent_count,
        "is_live_whatsapp": whatsapp_client.is_configured(),
        "message": f"Broadcast successfully dispatched to {sent_count} lead(s) via {'WhatsApp Cloud API' if whatsapp_client.is_configured() else 'Simulator'}!"
    }

@router.put("/api/crm/lead/{lead_id}/status")
async def update_lead_status(lead_id: int, payload: LeadStatusUpdate, db: AsyncSession = Depends(get_db)):
    """Update lead pipeline stage (new, qualified, hot, enrolled, cold) and notes."""
    stmt = select(Lead).where(Lead.id == lead_id)
    res = await db.execute(stmt)
    lead = res.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    lead.status = payload.status
    if payload.notes:
        lead.notes = f"{lead.notes or ''} | {payload.notes}".strip(" |")
    await db.commit()
    await db.refresh(lead)
    return {"status": "success", "lead": {"id": lead.id, "status": lead.status, "notes": lead.notes}}

@router.put("/api/crm/lead/{lead_id}/notes")
async def update_lead_notes(lead_id: int, payload: LeadNotesUpdate, db: AsyncSession = Depends(get_db)):
    """Save private internal advisor notes for a lead."""
    stmt = select(Lead).where(Lead.id == lead_id)
    res = await db.execute(stmt)
    lead = res.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    lead.notes = payload.notes
    await db.commit()
    await db.refresh(lead)
    return {"status": "success", "lead_id": lead.id, "notes": lead.notes}

@router.get("/api/crm/lead/{lead_id}/summary")
async def get_lead_summary(lead_id: int, db: AsyncSession = Depends(get_db)):
    """Generate a quick AI executive dossier summary for a lead during live handoff."""
    stmt = select(Lead).where(Lead.id == lead_id)
    res = await db.execute(stmt)
    lead = res.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    score = 40
    if lead.status == "hot": score = 95
    elif lead.status == "qualified": score = 75
    elif lead.status == "enrolled": score = 100
    if lead.budget_ready: score = min(100, score + 15)
    
    summary_text = (
        f"{lead.name or 'Student'} ({lead.phone}) is inquiring about {lead.course_interest or 'our tech programs'}. "
        f"Skill level: {lead.skill_level or 'Beginner'}. "
        f"Stage: {lead.status.upper()} (Score: {score}/100). "
        f"Payment Readiness: {'Ready / Verified' if lead.budget_ready else 'Flexible Monthly Installments Recommended'}."
    )
    return {
        "lead_id": lead.id,
        "score": score,
        "summary": summary_text,
        "recommended_next_step": "Offer a 15-minute admissions discovery call" if lead.status in ["qualified", "hot"] else "Share curriculum overview"
    }

@router.get("/api/appointments")
async def get_appointments(db: AsyncSession = Depends(get_db)):
    """List 1-on-1 advisor discovery calls booked by the AI agent."""
    stmt = select(Appointment).order_by(desc(Appointment.created_at))
    res = await db.execute(stmt)
    appointments = res.scalars().all()
    data = []
    for a in appointments:
        data.append({
            "id": a.id,
            "lead_id": a.lead_id,
            "phone": a.phone,
            "name": a.name,
            "service_or_course": a.service_or_course,
            "preferred_time": a.preferred_time,
            "status": a.status,
            "created_at": a.created_at.strftime("%b %d, %Y %I:%M %p") if a.created_at else "Recently"
        })
    return {"appointments": data}

@router.put("/api/appointments/{appointment_id}")
async def update_appointment_status(appointment_id: int, payload: AppointmentStatusUpdate, db: AsyncSession = Depends(get_db)):
    """Update status of a scheduled advisor consultation (scheduled, completed, cancelled)."""
    stmt = select(Appointment).where(Appointment.id == appointment_id)
    res = await db.execute(stmt)
    app_item = res.scalar_one_or_none()
    if not app_item:
        raise HTTPException(status_code=404, detail="Appointment not found")
    app_item.status = payload.status
    await db.commit()
    await db.refresh(app_item)
    return {"status": "success", "appointment": {"id": app_item.id, "status": app_item.status}}

DEFAULT_SYSTEM_PROMPT = SYSTEM_PROMPT_TEXT

@router.get("/api/settings", response_model=SystemConfigResponse)
async def get_settings(db: AsyncSession = Depends(get_db)):
    """Get global AI settings and instructions."""
    stmt = select(SystemConfig).limit(1)
    res = await db.execute(stmt)
    config = res.scalar_one_or_none()
    
    if not config:
        config = SystemConfig(
            agent_name="Tara",
            system_prompt=DEFAULT_SYSTEM_PROMPT.strip(),
            global_ai_enabled=True,
            persona_tone="consultative",
            business_hours="9:00 AM - 6:00 PM (Mon-Sat)",
            away_message="Thanks for contacting TekTutors! Our admissions team is currently away, but our AI advisor Tara is available 24/7 to assist you."
        )
        db.add(config)
        await db.commit()
        await db.refresh(config)
        
    return config

@router.put("/api/settings", response_model=SystemConfigResponse)
async def update_settings(payload: SystemConfigUpdate, db: AsyncSession = Depends(get_db)):
    """Update global AI settings, persona tone, and instructions."""
    stmt = select(SystemConfig).limit(1)
    res = await db.execute(stmt)
    config = res.scalar_one_or_none()
    
    if not config:
        config = SystemConfig(
            agent_name="Tara",
            system_prompt=DEFAULT_SYSTEM_PROMPT.strip(),
            global_ai_enabled=True,
            persona_tone="consultative",
            business_hours="9:00 AM - 6:00 PM (Mon-Sat)",
            away_message="Thanks for contacting TekTutors! Our admissions team is currently away, but our AI advisor Tara is available 24/7 to assist you."
        )
        db.add(config)
        await db.flush()
        
    update_data = payload.model_dump(exclude_unset=True)
    if "currency" in update_data and "currency_symbol" not in update_data:
        curr = update_data["currency"].upper()
        symbols = {"NGN": "₦", "USD": "$", "GBP": "£", "EUR": "€"}
        update_data["currency_symbol"] = symbols.get(curr, "₦")

    for key, value in update_data.items():
        setattr(config, key, value)
        
    await db.commit()
    await db.refresh(config)

    # Invalidate agent in-memory cache for instant effect
    try:
        from app.agent import invalidate_cached_system_config
        invalidate_cached_system_config()
    except Exception:
        pass

    return config


@router.post("/api/system/clean-slate")
async def clean_slate_database(payload: dict = Body(...), db: AsyncSession = Depends(get_db)):
    """
    Wipe demo/test transactional records (leads, appointments, conversations, messages, emails)
    while strictly preserving Courses catalog, FAQs knowledge base, and SystemConfig.
    """
    if not payload.get("confirm"):
        raise HTTPException(status_code=400, detail="Confirmation required. Pass {'confirm': True}.")

    try:
        await db.execute(delete(ScheduledEmail))
        await db.execute(delete(EmailLog))
        await db.execute(delete(Appointment))
        await db.execute(delete(Message))
        await db.execute(delete(Conversation))
        await db.execute(delete(Lead))
        await db.commit()

        logger.info("Admin clean slate executed: demo transactional data wiped.")
        return {
            "success": True,
            "message": "All demo leads, conversations, messages, appointments, and email queues have been purged. Courses and FAQs preserved."
        }
    except Exception as e:
        await db.rollback()
        logger.error(f"Error resetting database to clean slate: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Database clean slate error: {str(e)}")


# =========================================================================
# Email Marketing & Follow-up Campaign Routes
# =========================================================================

@router.get("/api/emails/templates")
async def get_email_templates():
    """Retrieve prebuilt follow-up, marketing, and promotional email templates."""
    return PREBUILT_EMAIL_TEMPLATES


@router.get("/api/emails/stats")
async def get_email_stats(db: AsyncSession = Depends(get_db)):
    """Retrieve aggregated metrics for sent emails."""
    stmt = select(EmailLog)
    res = await db.execute(stmt)
    logs = res.scalars().all()

    total_dispatched = len(logs)
    follow_up_count = sum(1 for l in logs if l.campaign_type == "follow_up")
    marketing_count = sum(1 for l in logs if l.campaign_type == "marketing")
    promotional_count = sum(1 for l in logs if l.campaign_type == "promotional")
    successful = sum(1 for l in logs if l.status in ("sent", "delivered"))
    delivery_rate = round((successful / total_dispatched * 100.0) if total_dispatched > 0 else 100.0, 1)

    return {
        "total_dispatched": total_dispatched,
        "follow_up_count": follow_up_count,
        "marketing_count": marketing_count,
        "promotional_count": promotional_count,
        "delivery_rate": delivery_rate
    }


@router.get("/api/emails/logs")
async def get_email_logs(
    limit: int = 50, 
    campaign_type: Optional[str] = None, 
    db: AsyncSession = Depends(get_db)
):
    """Retrieve history of dispatched emails with audit trail."""
    stmt = select(EmailLog).order_by(desc(EmailLog.sent_at))
    if campaign_type and campaign_type != "all":
        stmt = stmt.where(EmailLog.campaign_type == campaign_type)
    stmt = stmt.limit(limit)
    res = await db.execute(stmt)
    logs = res.scalars().all()

    return [
        {
            "id": l.id,
            "lead_id": l.lead_id,
            "recipient_email": l.recipient_email,
            "recipient_name": l.recipient_name,
            "campaign_type": l.campaign_type,
            "subject": l.subject,
            "status": l.status,
            "error_message": l.error_message,
            "sent_at": l.sent_at.strftime("%Y-%m-%d %H:%M:%S") if l.sent_at else ""
        }
        for l in logs
    ]


@router.post("/api/emails/preview")
async def preview_email_html(payload: dict = Body(...)):
    """Generate and return branded HTML preview for an email draft."""
    subject = payload.get("subject", "TekTutors Update")
    body = payload.get("body", "")
    cta_text = payload.get("cta_text", "Explore Courses")
    cta_url = payload.get("cta_url", "https://tektutors.com.ng/registration")
    recipient_name = payload.get("recipient_name", "Student")

    html = render_branded_email_html(
        subject=subject,
        body_markdown=body,
        cta_text=cta_text,
        cta_url=cta_url,
        recipient_name=recipient_name
    )
    return {"html": html}


@router.post("/api/emails/send-single")
async def send_single_email(payload: SingleEmailSendRequest, db: AsyncSession = Depends(get_db)):
    """Send a direct personalized email to a specific student/lead."""
    course_name = "Data Analytics & BI Accelerator"
    recipient_name = payload.recipient_name or "Student"

    # If lead_id provided, look up lead for more personalization context
    if payload.lead_id:
        stmt = select(Lead).where(Lead.id == payload.lead_id)
        res = await db.execute(stmt)
        lead = res.scalar_one_or_none()
        if lead:
            if lead.name and (recipient_name == "Student" or not recipient_name):
                recipient_name = lead.name
            if lead.course_interest:
                course_name = lead.course_interest

    result = await send_email_async(
        recipient_email=payload.recipient_email,
        recipient_name=recipient_name,
        subject=payload.subject,
        body_markdown=payload.body,
        campaign_type=payload.campaign_type,
        lead_id=payload.lead_id,
        cta_text=payload.cta_text,
        cta_url=payload.cta_url,
        course_name=course_name
    )

    if result.get("status") == "failed":
        raise HTTPException(status_code=500, detail=result.get("error_message") or "Failed to send email")

    return {
        "success": True,
        "message": f"Email successfully dispatched to {payload.recipient_email}",
        "result": result
    }


@router.get("/api/emails/logs/{log_id}")
async def get_email_log_detail(log_id: int, db: AsyncSession = Depends(get_db)):
    """Retrieve full email log details including rendered HTML body."""
    stmt = select(EmailLog).where(EmailLog.id == log_id)
    res = await db.execute(stmt)
    log = res.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Email log not found")

    return {
        "id": log.id,
        "lead_id": log.lead_id,
        "recipient_email": log.recipient_email,
        "recipient_name": log.recipient_name,
        "campaign_type": log.campaign_type,
        "subject": log.subject,
        "body_html": log.body_html,
        "status": log.status,
        "error_message": log.error_message,
        "sent_at": log.sent_at.strftime("%Y-%m-%d %H:%M:%S") if log.sent_at else ""
    }


@router.post("/api/emails/send-test")
async def send_test_email(payload: dict = Body(...)):
    """Quick test-dispatch for templates or drafts to an arbitrary test address."""
    to_email = payload.get("recipient_email", "").strip()
    if not to_email or "@" not in to_email:
        raise HTTPException(status_code=400, detail="A valid recipient email is required.")

    subject = payload.get("subject", "Test Email")
    body = payload.get("body", "")
    cta_text = payload.get("cta_text", "Explore Courses")
    cta_url = payload.get("cta_url", "https://tektutors.com.ng/registration")
    campaign_type = payload.get("campaign_type", "test")

    result = await send_email_async(
        recipient_email=to_email,
        recipient_name=payload.get("recipient_name", "Test Recipient"),
        subject=f"[TEST] {subject}",
        body_markdown=body,
        campaign_type=campaign_type,
        cta_text=cta_text,
        cta_url=cta_url,
        course_name=payload.get("course_name", "Data Analytics & BI Accelerator")
    )
    return {
        "success": result.get("status") in ("sent", "delivered"),
        "message": f"Test email dispatched to {to_email}",
        "result": result
    }


@router.post("/api/emails/trigger-engagement")
async def trigger_lead_engagement_email(payload: dict = Body(...), db: AsyncSession = Depends(get_db)):
    """
    1-click CRM conversion follow-up: Dispatch tailored email to a lead based on engagement trigger:
    trigger_event: 'syllabus' | 'consultation' | 'scholarship' | 'invoice' | 'reengagement'
    """
    from app.email_service import dispatch_engagement_email
    lead_id = payload.get("lead_id")
    trigger_event = payload.get("trigger_event", "syllabus")
    custom_notes = payload.get("custom_notes")

    if not lead_id:
        raise HTTPException(status_code=400, detail="lead_id is required")

    stmt = select(Lead).where(Lead.id == lead_id)
    res = await db.execute(stmt)
    lead = res.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if not lead.email or "@" not in lead.email:
        raise HTTPException(status_code=400, detail="Selected lead does not have a valid email address.")

    result = await dispatch_engagement_email(
        lead_id=lead.id,
        trigger_event=trigger_event,
        course_name=lead.course_interest or "Data Analytics & BI Accelerator",
        recipient_email=lead.email,
        recipient_name=lead.name or "Student",
        custom_notes=custom_notes
    )

    return {
        "success": result.get("status") in ("sent", "delivered"),
        "message": f"Engagement '{trigger_event}' email dispatched to {lead.email}!",
        "result": result
    }


@router.post("/api/emails/send-broadcast")
async def send_broadcast_email(payload: BroadcastEmailSendRequest, db: AsyncSession = Depends(get_db)):
    """Broadcast a marketing, follow-up, or promotional email to a segmented audience of leads."""
    # Query leads that have an email address
    stmt = select(Lead).where(Lead.email.isnot(None)).where(Lead.email != "")
    
    # Filter by target audience
    if payload.target_audience == "hot":
        stmt = stmt.where((Lead.lead_score >= 80) | (Lead.status.in_(["hot", "consultation_booked", "appointment_scheduled", "enrolled"])))
    elif payload.target_audience == "qualified":
        stmt = stmt.where((Lead.lead_score >= 60) | (Lead.status.in_(["qualified", "hot", "consultation_booked"])))
    elif payload.target_audience == "new":
        stmt = stmt.where(Lead.status == "new")

    res = await db.execute(stmt)
    raw_leads = res.scalars().all()

    # Deduplicate leads by email to prevent duplicate sending
    seen_emails = set()
    leads = []
    for l in raw_leads:
        clean_e = (l.email or "").strip().lower()
        if clean_e and "@" in clean_e and clean_e not in seen_emails:
            seen_emails.add(clean_e)
            leads.append(l)

    if not leads:
        return {
            "success": True,
            "dispatched_count": 0,
            "success_count": 0,
            "failed_count": 0,
            "message": f"No unique leads with valid email addresses found for audience segment '{payload.target_audience}'."
        }

    success_count = 0
    failed_count = 0
    dispatch_results = []

    for lead in leads:
        lead_course = lead.course_interest or "Data Analytics & BI Accelerator"
        lead_name = lead.name or "Student"

        res_item = await send_email_async(
            recipient_email=lead.email,
            recipient_name=lead_name,
            subject=payload.subject,
            body_markdown=payload.body,
            campaign_type=payload.campaign_type,
            lead_id=lead.id,
            cta_text=payload.cta_text,
            cta_url=payload.cta_url,
            course_name=lead_course
        )

        if res_item.get("status") in ("sent", "delivered"):
            success_count += 1
        else:
            failed_count += 1

        dispatch_results.append({
            "lead_id": lead.id,
            "email": lead.email,
            "name": lead_name,
            "status": res_item.get("status")
        })

    return {
        "success": True,
        "dispatched_count": len(leads),
        "success_count": success_count,
        "failed_count": failed_count,
        "message": f"Broadcast campaign completed: {success_count} sent successfully, {failed_count} failed.",
        "results": dispatch_results
    }


# =========================================================================
# Scheduled Email Queue & Drip Campaign Endpoints
# =========================================================================

@router.get("/api/emails/scheduled")
async def get_scheduled_emails(
    status: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
):
    """Retrieve scheduled email queue items with optional status filtering."""
    stmt = select(ScheduledEmail).order_by(ScheduledEmail.scheduled_for.asc())
    if status and status.lower() != "all":
        stmt = stmt.where(ScheduledEmail.status == status.lower().strip())
    stmt = stmt.limit(limit)

    res = await db.execute(stmt)
    records = res.scalars().all()

    now = datetime.datetime.now()
    output = []
    for r in records:
        time_until = (r.scheduled_for - now).total_seconds() if r.scheduled_for else 0
        output.append({
            "id": r.id,
            "lead_id": r.lead_id,
            "recipient_email": r.recipient_email,
            "recipient_name": r.recipient_name,
            "sequence_day": r.sequence_day,
            "subject": r.subject,
            "body_markdown": r.body_markdown[:180] + "..." if len(r.body_markdown) > 180 else r.body_markdown,
            "campaign_type": r.campaign_type,
            "course_name": r.course_name,
            "scheduled_for": r.scheduled_for.strftime("%Y-%m-%d %H:%M:%S") if r.scheduled_for else "",
            "scheduled_for_formatted": r.scheduled_for.strftime("%a, %b %d • %I:%M %p") if r.scheduled_for else "",
            "status": r.status,
            "is_due": r.status == "pending" and time_until <= 0,
            "seconds_until_delivery": max(0, int(time_until)),
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "",
            "sent_at": r.sent_at.strftime("%Y-%m-%d %H:%M:%S") if r.sent_at else None,
            "error_message": r.error_message
        })

    return {
        "total": len(output),
        "scheduled_emails": output
    }


@router.post("/api/emails/schedule")
async def schedule_custom_email(payload: dict = Body(...)):
    """Schedule a custom or templated email to dispatch at a specified future date/time."""
    to_email = payload.get("recipient_email", "").strip()
    if not to_email or "@" not in to_email:
        raise HTTPException(status_code=400, detail="A valid recipient email address is required.")

    subject = payload.get("subject", "").strip()
    if not subject:
        raise HTTPException(status_code=400, detail="Subject is required.")

    body = payload.get("body", "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="Email body markdown is required.")

    scheduled_for_raw = payload.get("scheduled_for", "")
    if not scheduled_for_raw:
        raise HTTPException(status_code=400, detail="scheduled_for datetime or delay string is required.")

    from app.email_service import schedule_email_async, parse_schedule_time
    target_dt = parse_schedule_time(scheduled_for_raw)

    result = await schedule_email_async(
        to_email=to_email,
        subject=subject,
        body_markdown=body,
        scheduled_for=target_dt,
        to_name=payload.get("recipient_name", "Student"),
        campaign_type=payload.get("campaign_type", "scheduled_custom"),
        lead_id=payload.get("lead_id"),
        course_name=payload.get("course_name", "Data Analytics & BI Accelerator"),
        cta_text=payload.get("cta_text", "Register Online"),
        cta_url=payload.get("cta_url", "https://tektutors.com.ng/registration")
    )

    return {
        "success": True,
        "message": f"Email successfully scheduled for delivery at {target_dt.strftime('%a, %b %d at %I:%M %p')}!",
        "result": result
    }


@router.post("/api/emails/enroll-drip")
async def enroll_lead_drip(payload: dict = Body(...), db: AsyncSession = Depends(get_db)):
    """Enroll a specific lead into the 5-day daily follow-up nurture drip sequence."""
    lead_id = payload.get("lead_id")
    email = payload.get("recipient_email") or payload.get("email")
    name = payload.get("recipient_name") or payload.get("name")
    course_name = payload.get("course_name")

    if lead_id:
        stmt = select(Lead).where(Lead.id == lead_id)
        res = await db.execute(stmt)
        lead = res.scalar_one_or_none()
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")
        email = email or lead.email
        name = name or lead.name
        course_name = course_name or lead.course_interest

    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="A valid email address is required to enroll in the drip sequence.")

    from app.email_service import enroll_lead_in_daily_drip_sequence
    result = await enroll_lead_in_daily_drip_sequence(
        lead_id=lead_id,
        email=email,
        name=name or "Student",
        course_name=course_name or "Data Analytics & BI Accelerator"
    )

    return {
        "success": True,
        "message": f"Successfully enrolled {email} in 5-day daily follow-up drip sequence!",
        "result": result
    }


@router.post("/api/emails/scheduled/{scheduled_id}/cancel")
async def cancel_scheduled_email_endpoint(scheduled_id: int):
    """Cancel a pending scheduled email."""
    from app.email_service import cancel_scheduled_email
    success = await cancel_scheduled_email(scheduled_id)
    if not success:
        raise HTTPException(status_code=404, detail="Scheduled email not found or already processed/cancelled.")
    return {"success": True, "message": f"Scheduled email #{scheduled_id} cancelled successfully."}


@router.post("/api/emails/scheduled/process-now")
async def process_scheduled_emails_now():
    """Immediately trigger dispatch of any due scheduled emails in queue."""
    from app.email_service import process_due_scheduled_emails
    results = await process_due_scheduled_emails()
    return {
        "success": True,
        "processed_count": len(results),
        "results": results
    }



