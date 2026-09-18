import json
import time
import logging
from typing import Optional, List, Dict, Any
from langchain.tools import tool
from sqlalchemy import select, or_, desc
from app.database import AsyncSessionLocal
from app.models import Course, FAQ, Lead, Appointment, Conversation

logger = logging.getLogger(__name__)

# In-memory TTL cache to eliminate redundant DB reads during active chats
_COURSES_CACHE: Optional[List[Dict[str, Any]]] = None
_COURSES_CACHE_EXPIRY: float = 0.0
_FAQS_CACHE: Optional[List[Dict[str, Any]]] = None
_FAQS_CACHE_EXPIRY: float = 0.0
_TOOL_CACHE_TTL_SECONDS: float = 300.0  # 5 minutes


def invalidate_tool_caches() -> None:
    """Clear in-memory caches when admin modifies courses or FAQs."""
    global _COURSES_CACHE, _COURSES_CACHE_EXPIRY, _FAQS_CACHE, _FAQS_CACHE_EXPIRY
    _COURSES_CACHE = None
    _COURSES_CACHE_EXPIRY = 0.0
    _FAQS_CACHE = None
    _FAQS_CACHE_EXPIRY = 0.0


async def _get_cached_courses() -> List[Dict[str, Any]]:
    """Retrieve active courses from cache or database."""
    global _COURSES_CACHE, _COURSES_CACHE_EXPIRY
    now = time.time()
    if _COURSES_CACHE is not None and now < _COURSES_CACHE_EXPIRY:
        return _COURSES_CACHE

    async with AsyncSessionLocal() as db:
        res = await db.execute(select(Course).where(Course.is_active == True))
        db_courses = res.scalars().all()
        _COURSES_CACHE = [
            {
                "id": c.id,
                "title": c.title,
                "description": c.description or "",
                "syllabus": c.syllabus or "",
                "duration_weeks": c.duration_weeks,
                "price": int(c.price) if c.price else 100000,
                "career_outcomes": c.career_outcomes or "",
                "prerequisites": c.prerequisites or ""
            }
            for c in db_courses
        ]
        _COURSES_CACHE_EXPIRY = now + _TOOL_CACHE_TTL_SECONDS
    return _COURSES_CACHE


async def _get_cached_faqs() -> List[Dict[str, Any]]:
    """Retrieve FAQs from cache or database."""
    global _FAQS_CACHE, _FAQS_CACHE_EXPIRY
    now = time.time()
    if _FAQS_CACHE is not None and now < _FAQS_CACHE_EXPIRY:
        return _FAQS_CACHE

    async with AsyncSessionLocal() as db:
        res = await db.execute(select(FAQ))
        db_faqs = res.scalars().all()
        _FAQS_CACHE = [
            {
                "id": f.id,
                "category": f.category or "",
                "question": f.question or "",
                "answer": f.answer or ""
            }
            for f in db_faqs
        ]
        _FAQS_CACHE_EXPIRY = now + _TOOL_CACHE_TTL_SECONDS
    return _FAQS_CACHE


@tool
async def search_tektutors_courses(query: str) -> str:
    """
    Search TekTutors course catalog, prices, syllabus, prerequisites, and duration.
    Use this tool whenever a customer asks about courses, prices, bootcamps, or learning topics.
    """
    all_courses = await _get_cached_courses()
    matched_specific = False
    matched_courses = []

    if query:
        keywords = [kw.strip().lower() for kw in query.replace(",", " ").replace("?", " ").replace(".", " ").split() if len(kw.strip()) > 2]
        if keywords:
            for c in all_courses:
                title_lower = c["title"].lower()
                desc_lower = c["description"].lower()
                syl_lower = c["syllabus"].lower()

                score = 0
                for kw in keywords:
                    if kw in title_lower:
                        score += 10
                    elif kw in desc_lower:
                        score += 3
                    elif kw in syl_lower:
                        score += 2

                if score > 0:
                    matched_courses.append((score, c))

            if matched_courses:
                matched_courses.sort(key=lambda x: x[0], reverse=True)
                matched_courses = [c for _, c in matched_courses]
                matched_specific = True

    if not matched_courses:
        # Provide top 3 foundational tracks if no specific match
        matched_courses = all_courses[:3]
        matched_specific = False

    # Cap to top 3 matches to prevent multi-thousand token context bloat
    selected = matched_courses[:3]
    courses_data = []
    for c in selected:
        item = {
            "title": c["title"],
            "price_monthly": f"₦{c['price']:,}",
            "duration": f"{c['duration_weeks']} Weeks",
            "career_outcomes": c["career_outcomes"],
            "prerequisites": c["prerequisites"]
        }
        if matched_specific or len(selected) <= 2:
            item["syllabus"] = c["syllabus"]
            item["description"] = c["description"]
        else:
            item["summary"] = c["description"][:120] + "..." if len(c["description"]) > 120 else c["description"]
        courses_data.append(item)

    # Minified JSON serialization saves 45-60% whitespace/indent tokens
    return json.dumps(courses_data, separators=(',', ':'))


FAQ_STOPWORDS = {
    "the", "and", "for", "with", "can", "what", "how", "why", "when", "where", "who", "which",
    "are", "is", "was", "were", "been", "being", "that", "this", "these", "those", "from",
    "into", "onto", "about", "there", "their", "they", "them", "some", "any", "all", "our",
    "ours", "you", "your", "yours", "have", "has", "had", "does", "did", "tell", "give", "want",
    "know", "like", "would", "could", "should", "please", "need"
}


@tool
async def get_course_faq_answer(question_or_topic: str) -> str:
    """
    Search TekTutors FAQ knowledge base regarding payment installment options, beginner prerequisites, live weekend schedule, certificates, and job placement assistance.
    """
    all_faqs = await _get_cached_faqs()
    keywords = []

    if question_or_topic:
        raw_tokens = [kw.strip().lower() for kw in question_or_topic.replace(",", " ").replace("?", " ").replace(".", " ").split() if kw.strip()]
        keywords = [w for w in raw_tokens if len(w) > 2 and w not in FAQ_STOPWORDS]
        if not keywords and raw_tokens:
            keywords = [w for w in raw_tokens if len(w) > 2]

    scored_faqs = []
    if keywords and all_faqs:
        for f in all_faqs:
            q_text = f["question"].lower()
            a_text = f["answer"].lower()
            c_text = f["category"].lower()
            score = 0
            for kw in keywords:
                if kw in q_text:
                    score += 10
                if kw in a_text:
                    score += 3
                if kw in c_text:
                    score += 1
            if score > 0:
                scored_faqs.append((score, f))

        scored_faqs.sort(key=lambda x: x[0], reverse=True)
        faqs = [f for _, f in scored_faqs]
    else:
        faqs = all_faqs

    if not faqs and not (question_or_topic and question_or_topic.strip()):
        faqs = all_faqs[:3]
    elif not faqs:
        return json.dumps({
            "found": False,
            "message": "No matching FAQ in knowledge base. Escalate this question to a human advisor."
        }, separators=(',', ':'))

    # Limit to top 2-3 matched FAQs and serialize compactly
    faq_list = [{"category": f["category"], "question": f["question"], "answer": f["answer"]} for f in faqs[:3]]
    return json.dumps(faq_list, separators=(',', ':'))

@tool
async def qualify_and_capture_lead(
    phone: str,
    name: Optional[str] = None,
    email: Optional[str] = None,
    course_interest: Optional[str] = None,
    skill_level: Optional[str] = None,
    budget_ready: Optional[bool] = True,
    notes: Optional[str] = None
) -> str:
    """
    Capture student details and save them to TekTutors CRM database.
    Use this tool when a prospect shares their name, email, background, or course interest.
    """
    clean_phone = phone.strip().replace("+", "")
    if email:
        import re
        match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', email)
        if match:
            email = match.group(0)
    if name and ("is" in name.lower() or ":" in name or "name" in name.lower()):
        name = name.split(":")[-1].split("is")[-1].strip().title()

    async with AsyncSessionLocal() as db:
        stmt = select(Lead).where(Lead.phone == clean_phone).order_by(desc(Lead.id)).limit(1)
        res = await db.execute(stmt)
        lead = res.scalars().first()

        # Calculate dynamic buying readiness score
        score = 50
        if email and "@" in email:
            score += 20
        if course_interest:
            score += 15
        if name and name.lower() not in ("prospect", "student", "there", ""):
            score += 10
        if budget_ready:
            score += 15
        calculated_score = min(score, 100)

        if not lead:
            initial_status = "hot" if calculated_score >= 80 else ("qualified" if (email or calculated_score >= 60) else "new")
            lead = Lead(
                phone=clean_phone,
                name=name,
                email=email,
                course_interest=course_interest,
                skill_level=skill_level,
                status=initial_status,
                budget_ready=budget_ready if budget_ready is not None else False,
                lead_score=calculated_score,
                notes=notes
            )
            db.add(lead)
        else:
            if name and name.lower() not in ("prospect", "student", ""):
                lead.name = name
            if email:
                lead.email = email
            if course_interest:
                lead.course_interest = course_interest
            if skill_level:
                lead.skill_level = skill_level
            if budget_ready is not None:
                lead.budget_ready = budget_ready
            if notes:
                lead.notes = f"{lead.notes or ''} | {notes}".strip(" |")
            
            lead.lead_score = max(lead.lead_score or 50, calculated_score)
            if lead.status != "enrolled":
                if lead.lead_score >= 80:
                    lead.status = "hot"
                elif lead.lead_score >= 60 and lead.status == "new":
                    lead.status = "qualified"

        await db.commit()
        await db.refresh(lead)

        # Automatically trigger personalized syllabus & roadmap email when email is captured
        if lead.email and "@" in lead.email:
            try:
                from app.email_service import dispatch_engagement_email
                await dispatch_engagement_email(
                    lead_id=lead.id,
                    trigger_event="syllabus",
                    course_name=lead.course_interest or course_interest or "Data Analytics & BI Accelerator",
                    recipient_email=lead.email,
                    recipient_name=lead.name or "Student"
                )
                logger.info(f"Syllabus email successfully dispatched for lead #{lead.id} to {lead.email}")
            except Exception as e:
                logger.error(f"Error during lead syllabus email dispatch for {lead.email}: {e}")

        return f"Lead captured successfully! ID: {lead.id}, Name: {lead.name}, Score: {lead.lead_score}, Status: {lead.status}"

@tool
async def schedule_advisor_call(
    phone: str,
    name: str,
    preferred_time: str,
    course: str
) -> str:
    """
    Schedule a 1-on-1 discovery call for a prospect with a TekTutors Admissions Advisor.
    Marks the lead as 'hot'.
    """
    clean_phone = phone.strip().replace("+", "")
    async with AsyncSessionLocal() as db:
        # Check or create lead
        stmt = select(Lead).where(Lead.phone == clean_phone).order_by(desc(Lead.id)).limit(1)
        res = await db.execute(stmt)
        lead = res.scalars().first()

        if not lead:
            lead = Lead(phone=clean_phone, name=name, course_interest=course, status="hot", lead_score=85)
            db.add(lead)
            await db.flush()
        else:
            lead.name = name or lead.name
            lead.course_interest = course or lead.course_interest
            lead.status = "hot"
            lead.lead_score = max(lead.lead_score or 50, 85)

        appointment = Appointment(
            lead_id=lead.id,
            phone=clean_phone,
            name=name,
            service_or_course=course,
            preferred_time=preferred_time,
            status="scheduled"
        )
        db.add(appointment)
        await db.commit()

        # Automatically dispatch 1-on-1 consultation booking confirmation email
        if lead.email and "@" in lead.email:
            try:
                import asyncio
                from app.email_service import dispatch_engagement_email
                asyncio.create_task(dispatch_engagement_email(
                    lead_id=lead.id,
                    trigger_event="consultation",
                    course_name=course or lead.course_interest or "Data Analytics & BI Accelerator",
                    recipient_email=lead.email,
                    recipient_name=name or lead.name or "Student",
                    custom_notes=f"Your consultation call is booked for {preferred_time}."
                ))
            except Exception as e:
                logger.warning(f"Note: Background consultation email dispatch skipped: {e}")

        return f"Advisor Call Scheduled for {name} ({clean_phone}) at {preferred_time} regarding {course}."

@tool
async def escalate_to_human_advisor(phone: str, reason: str) -> str:
    """
    Escalate the conversation to a human admissions and sales advisor on the dashboard.
    Call this tool whenever:
    1. A prospect asks ANY question, policy, or detail that you cannot answer or that is NOT verified in the TekTutors knowledge base.
    2. The customer explicitly asks to speak to a human, advisor, agent, or representative.
    3. The customer has a dispute, complex complaint, custom corporate group training request, or custom billing concern.
    """
    clean_phone = phone.strip().replace("+", "")
    async with AsyncSessionLocal() as db:
        stmt = select(Conversation).where(Conversation.phone == clean_phone).order_by(desc(Conversation.id)).limit(1)
        res = await db.execute(stmt)
        conv = res.scalars().first()

        if conv:
            conv.ai_active = False
            conv.handoff_reason = reason
            await db.commit()

        # Update lead status to hot if exists
        lead_stmt = select(Lead).where(Lead.phone == clean_phone).order_by(desc(Lead.id)).limit(1)
        lead_res = await db.execute(lead_stmt)
        lead = lead_res.scalars().first()
        if lead:
            lead.status = "hot"
            lead.notes = f"{lead.notes or ''} | Escalate: {reason}".strip(" |")
            await db.commit()

        return f"Conversation escalated to human advisor. Reason: {reason}"

@tool
async def generate_enrollment_checkout(
    course_title: str,
    payment_plan: str,
    phone: str,
    student_name: Optional[str] = None
) -> str:
    """
    Generate an official TekTutors registration and payment link (https://tektutors.com.ng/registration) and payment invoice.
    Use this tool when a student asks how to pay, wants to register/enroll, or asks for the payment or registration link.
    payment_plan can be 'monthly_installment' (₦100,000/mo) or 'upfront_full' (10% discount, ₦90,000).
    """
    clean_phone = phone.strip().replace("+", "")
    async with AsyncSessionLocal() as db:
        stmt = select(Course).where(Course.is_active == True)
        res = await db.execute(stmt)
        courses = res.scalars().all()
        
        matched_course = None
        for c in courses:
            if course_title.lower() in c.title.lower() or c.title.lower() in course_title.lower():
                matched_course = c
                break
        if not matched_course and courses:
            matched_course = courses[0]

        course_name = matched_course.title if matched_course else "Data Analytics Bootcamp"
        slug = matched_course.slug if matched_course else "data-analytics"
        
        is_upfront = "upfront" in payment_plan.lower() or "full" in payment_plan.lower() or "discount" in payment_plan.lower()
        if is_upfront:
            plan_desc = "Full Upfront Payment (10% Discount Applied - Save ₦10,000)"
            due_today = "₦90,000 (Full Payment with 10% Discount)"
        else:
            plan_desc = "Flexible Month-to-Month Plan (₦100,000 / month)"
            due_today = "₦100,000 (First Month Installment)"

        inv_ref = f"TEK-{clean_phone[-6:]}-{slug[:4].upper()}"
        checkout_url = "https://tektutors.com.ng/registration"

        lead_stmt = select(Lead).where(Lead.phone == clean_phone).order_by(desc(Lead.id)).limit(1)
        lead_res = await db.execute(lead_stmt)
        lead = lead_res.scalars().first()
        if not lead:
            lead = Lead(
                phone=clean_phone,
                name=student_name or "Prospect",
                course_interest=course_name,
                status="hot",
                budget_ready=True,
                notes=f"[Checkout Generated: {inv_ref} | Plan: {plan_desc}]"
            )
            db.add(lead)
        else:
            lead.status = "hot"
            lead.budget_ready = True
            lead.course_interest = course_name
            lead.notes = f"{lead.notes or ''} | [Checkout Generated: {inv_ref} | {plan_desc}]".strip(" |")
        
        await db.commit()

        # Automatically dispatch official enrollment invoice & registration link email
        if lead and lead.email and "@" in lead.email:
            try:
                import asyncio
                from app.email_service import dispatch_engagement_email
                asyncio.create_task(dispatch_engagement_email(
                    lead_id=lead.id,
                    trigger_event="invoice",
                    course_name=course_name,
                    recipient_email=lead.email,
                    recipient_name=student_name or lead.name or "Student",
                    custom_notes=f"Invoice Ref: {inv_ref} | Plan: {plan_desc} | Due Today: {due_today}"
                ))
            except Exception as e:
                logger.warning(f"Note: Background invoice email dispatch skipped: {e}")

        invoice_data = {
            "invoice_ref": inv_ref,
            "course": course_name,
            "plan": plan_desc,
            "due_today": due_today,
            "checkout_url": checkout_url,
            "cohort_start": "Next Saturday (10:00 AM WAT)",
            "seats_remaining": "Strictly 4 seats remaining in this 1-on-1 mentor cohort"
        }
        return json.dumps(invoice_data, indent=2)

@tool
async def calculate_career_roi(course_title: str) -> str:
    """
    Calculate and retrieve realistic market salary benchmarks, job roles, and return on investment (ROI) for TekTutors graduates.
    Use this tool when a student asks about career prospects, job security, whether the fee is worth it, or salary expectations.
    """
    title_lower = course_title.lower()
    
    if "data" in title_lower or "analytics" in title_lower or "bi" in title_lower:
        role = "Junior to Mid Data Analyst / BI Specialist"
        local_salary = "₦350,000 - ₦750,000 / month"
        remote_salary = "$1,500 - $3,000 / month (₦2,250,000+)"
        top_employers = "Fintechs, Commercial Banks, FMCG, Telecommunications, Global remote startups"
        payback_time = "Under 3 weeks of first month salary"
    elif "ai" in title_lower or "machine" in title_lower or "python" in title_lower:
        role = "AI Engineer / Machine Learning Developer"
        local_salary = "₦450,000 - ₦950,000 / month"
        remote_salary = "$2,000 - $4,500 / month"
        top_employers = "AI startups, Global software agencies, Financial institutions"
        payback_time = "Under 2 weeks of first month salary"
    else:
        role = "Technology Specialist"
        local_salary = "₦350,000 - ₦700,000 / month"
        remote_salary = "$1,500 - $2,500 / month"
        top_employers = "Tech companies and corporate enterprise teams"
        payback_time = "Under 1 month"

    roi_data = {
        "target_career": role,
        "nigeria_entry_salary": local_salary,
        "global_remote_salary": remote_salary,
        "training_investment": "₦100,000 / month",
        "roi_payback_duration": payback_time,
        "hiring_industries": top_employers,
        "mentorship_career_support": "Resume optimization, LinkedIn branding, 3 capstone portfolio projects, and direct interview referrals."
    }
    return json.dumps(roi_data, indent=2)

@tool
async def check_scholarship_and_discounts(course_title: str, eligibility_reason: Optional[str] = None) -> str:
    """
    Check active TekTutors tuition scholarships, upfront payment discounts, and early-bird promotional codes.
    Use this tool when a student asks for discounts, scholarships, financial aid, or promo codes.
    """
    discounts = [
        {
            "program": "🎟️ Fast-Action Early Bird Voucher",
            "benefit": "₦20,000 Tuition Waiver on 2-Month Bootcamps",
            "coupon_code": "TEK-EARLY20",
            "validity": "Valid for next 48 hours for upcoming weekend cohort",
            "how_to_claim": "Enter code TEK-EARLY20 on checkout or mention it during your advisor consultation."
        },
        {
            "program": "👩‍💻 Women in Tech Empowerment Grant",
            "benefit": "15% Tuition Waiver (Save ₦30,000 total)",
            "coupon_code": "TEK-WOMEN15",
            "validity": "Active for female professionals and university graduates",
            "how_to_claim": "Select Grant option during registration."
        },
        {
            "program": "💳 Full Upfront Payment Discount",
            "benefit": "10% Instant Discount (Pay ₦90,000 instead of ₦100,000 - Save ₦10,000)",
            "coupon_code": "TEK-UPFRONT10",
            "validity": "Available year-round on full program prepayment",
            "how_to_claim": "Select 'Full Prepayment' option at checkout."
        }
    ]
    return json.dumps({
        "status": "active_programs_available",
        "course": course_title,
        "available_discounts": discounts,
        "action": "Offer the early bird or upfront discount to help the customer enroll today."
    }, indent=2)

@tool
async def trigger_conversion_email_campaign(
    phone: str,
    campaign_stage: str,
    course_name: Optional[str] = None,
    custom_note: Optional[str] = None,
    email: Optional[str] = None
) -> str:
    """
    Dispatch a targeted, branded email campaign directly to a student's inbox to drive conversion.
    Use this tool when a prospect asks for written documents, syllabus roadmaps, scholarship vouchers, or checkout invoices.
    
    Allowed campaign_stage values:
    - 'syllabus': Sends detailed week-by-week curriculum, tools breakdown, and capstone roadmap.
    - 'consultation': Sends 1-on-1 advisor discovery call confirmation, agenda, and meeting prep guide.
    - 'scholarship': Sends the 20% Fast-Action Scholarship voucher code (TEK-EARLY20) and upfront rebate (₦90,000).
    - 'invoice': Sends official registration checkout link (https://tektutors.com.ng/registration) & payment options.
    - 'reengagement': Sends student career transformation case study and urgency reminder.
    """
    clean_phone = phone.strip().replace("+", "")
    from app.email_service import dispatch_engagement_email

    async with AsyncSessionLocal() as db:
        stmt = select(Lead).where(Lead.phone == clean_phone).order_by(desc(Lead.id)).limit(1)
        res = await db.execute(stmt)
        lead = res.scalars().first()

        target_email = email.strip() if (email and "@" in email) else (lead.email if lead and lead.email else None)

        if not target_email or "@" not in target_email:
            return (
                f"Prospect does not have an email address on file yet. "
                f"Please ask them: 'Could you please share your email address so I can dispatch your personalized {campaign_stage} package right away?'"
            )

        if lead:
            if email and "@" in email:
                lead.email = email.strip()
                await db.commit()
                await db.refresh(lead)
        else:
            lead = Lead(
                phone=clean_phone,
                email=target_email,
                course_interest=course_name or "Data Analytics & BI Accelerator",
                status="qualified",
                lead_score=70
            )
            db.add(lead)
            await db.commit()
            await db.refresh(lead)

        target_course = course_name or lead.course_interest or "Data Analytics & BI Accelerator"
        target_name = lead.name or "Student"

        result = await dispatch_engagement_email(
            lead_id=lead.id,
            trigger_event=campaign_stage.lower().strip(),
            course_name=target_course,
            recipient_email=target_email,
            recipient_name=target_name,
            custom_notes=custom_note
        )

        return (
            f"✅ Dispatched '{campaign_stage}' conversion email to {target_email}! "
            f"Subject: '{result.get('subject')}'. Delivery Status: {result.get('status')}."
        )

TEKTUTORS_TOOLS = [
    search_tektutors_courses,
    get_course_faq_answer,
    qualify_and_capture_lead,
    schedule_advisor_call,
    escalate_to_human_advisor,
    generate_enrollment_checkout,
    calculate_career_roi,
    check_scholarship_and_discounts,
    trigger_conversion_email_campaign
]
