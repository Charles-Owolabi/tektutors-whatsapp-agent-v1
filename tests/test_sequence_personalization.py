import pytest
import datetime
from app.whatsapp_sequence import (
    generate_personalized_3_step_sequence,
    detect_course_interest,
    detect_discussion_line,
    COURSE_CATALOG_DATA
)

def test_detect_course_interest():
    assert detect_course_interest("I want to learn python programming") == "Applied Python for Data Analysis & AI"
    assert detect_course_interest("How much is Power BI course?") == "Power BI & Business Intelligence"
    assert detect_course_interest("Can you teach me SQL and postgres queries?") == "SQL & Enterprise Database Analytics"
    assert detect_course_interest("I need advanced excel with pivot tables") == "Excel for Data Analysis & Business Modeling"
    assert detect_course_interest("Machine learning algorithms and models") == "Machine Learning with Python"
    assert detect_course_interest("What is business analysis?") == "Business Analysis"
    assert detect_course_interest("Financial modeling and valuation") == "Financial Analytics"
    assert detect_course_interest("People and hr analytics") == "HR Analytics"
    assert detect_course_interest("I want to learn RStudio and tidyverse") == "R for Data Analysis"
    assert detect_course_interest("Predictive analytics and forecasting") == "Predictive Analytics"
    assert detect_course_interest("4") == "Power BI & Business Intelligence"
    assert detect_course_interest("Hi there") == "Data Analytics & BI Accelerator"


def test_assistant_menu_does_not_pollute_course_detection():
    """Ensure Tara's 6-track catalog greeting menu (which mentions Machine Learning) never hijacks course detection."""
    tara_menu = (
        "🎓 *TekTutors Practical Tech Pathways (1-on-1 Mentorship)*\n"
        "1️⃣ *Data Analytics & BI Accelerator*\n"
        "2️⃣ *Excel for Data Analysis*\n"
        "3️⃣ *SQL for Analytics*\n"
        "4️⃣ *Power BI & Business Intelligence*\n"
        "5️⃣ *Applied Python for Analytics & AI*\n"
        "6️⃣ *Explore Other Specialized Tracks* (Data Science, Machine Learning, Business Analysis)"
    )
    chat_hist = [
        {"sender": "user", "body": "Hi"},
        {"sender": "assistant", "body": tara_menu},
        {"sender": "user", "body": "How much is the tuition fee for Excel?"}
    ]
    steps = generate_personalized_3_step_sequence(lead_name="Chidi", chat_history=chat_hist)
    assert "Excel for Data Analysis & Business Modeling" in steps[0]["body"]
    assert "Machine Learning" not in steps[0]["body"]


def test_detect_discussion_line():
    disc_price = detect_discussion_line("How much is the fee? Can I pay in monthly installments of 100k?")
    assert disc_price["topic_key"] == "pricing_tuition"

    disc_beginner = detect_discussion_line("I have zero coding experience and I come from a banking background. Is it hard?")
    assert disc_beginner["topic_key"] == "beginner_nontech"

    disc_sched = detect_discussion_line("Are the classes on weekends? I work 9-5 during weekdays and need recordings.")
    assert disc_sched["topic_key"] == "schedule_flexibility"

    disc_syl = detect_discussion_line("Can you send me the full curriculum and syllabus modules?")
    assert disc_syl["topic_key"] == "curriculum_syllabus"

    disc_proj = detect_discussion_line("What capstone project will I build for my portfolio?")
    assert disc_proj["topic_key"] == "projects_capstone"

    disc_career = detect_discussion_line("Will this help me switch careers and get a job? Do you review CVs?")
    assert disc_career["topic_key"] == "career_job_switch"

    disc_gen = detect_discussion_line("Hello, good morning.")
    assert disc_gen["topic_key"] == "general_discovery"


def test_2_hour_follow_up_pricing_python():
    """Verify that when a prospect asks about Python tuition, Step 1 (T+2h) is tailored to Python and installments."""
    chat_hist = [
        {"sender": "user", "body": "Hi Tara, I want to learn Python for data analysis."},
        {"sender": "assistant", "body": "Hello! We'd love to help you master Python."},
        {"sender": "user", "body": "How much is the fee? Can I pay in installments?"}
    ]
    steps = generate_personalized_3_step_sequence(
        lead_name="Emeka",
        chat_history=chat_hist
    )
    assert len(steps) == 3
    step1 = steps[0]

    # Verify 2-hour delay
    assert step1["step"] == 1
    assert step1["delay_hours"] == 2

    # Verify content relevance: mentions Python, flexible installments, and ₦100,000
    body = step1["body"]
    assert "Applied Python for Data Analysis & AI" in body
    assert "₦100,000 / month" in body
    assert "Emeka" in body
    assert "Python, Pandas, NumPy & Jupyter" in body
    assert "Automated Customer Churn Pipeline" in body

    # Verify interactive button
    btn_ids = [b["id"] for b in step1["buttons"]]
    assert "seq_tuition_breakdown" in btn_ids


def test_2_hour_follow_up_beginner_power_bi():
    """Verify that when a prospect asks about zero coding for Power BI, Step 1 reassures their beginner background."""
    chat_hist = [
        {"sender": "user", "body": "I want to learn Power BI, but I have no coding background. Can a beginner do this?"}
    ]
    steps = generate_personalized_3_step_sequence(
        lead_name="Amina",
        chat_history=chat_hist
    )
    assert len(steps) == 3
    step1 = steps[0]

    assert step1["delay_hours"] == 2
    body = step1["body"]
    assert "Power BI & Business Intelligence" in body
    assert "non-technical background" in body or "zero coding" in body
    assert "Power BI Desktop, Power Query & DAX" in body
    assert "Enterprise Executive KPI Dashboard" in body
    assert "Amina" in body


def test_2_hour_follow_up_weekend_sql():
    """Verify that when a prospect asks about SQL weekend schedule, Step 1 addresses weekend class timing."""
    chat_hist = [
        {"sender": "user", "body": "When are SQL classes held? I work during weekdays so I only have time on weekends."}
    ]
    steps = generate_personalized_3_step_sequence(
        lead_name="Tunde",
        chat_history=chat_hist
    )
    step1 = steps[0]
    assert step1["delay_hours"] == 2
    body = step1["body"]
    assert "SQL & Enterprise Database Analytics" in body
    assert "Saturdays & Sundays" in body
    assert "lifetime replay" in body or "recordings" in body
    assert "PostgreSQL & Database Queries" in body


@pytest.mark.asyncio
async def test_enroll_lead_db_lifecycle():
    """Verify that enroll_lead_in_3_step_sequence creates pending Step 1 scheduled for T+2h and updates it upon chat."""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import select
    from app.models import Base, Lead, ScheduledWhatsAppMessage
    from app.whatsapp_sequence import enroll_lead_in_3_step_sequence

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as db:
        # Step 1: Initial chat: Lead asks about Python tuition
        lead = Lead(phone="2348011223344", name="Ngozi", status="new")
        db.add(lead)
        await db.commit()

        initial_chat = [
            {"sender": "user", "body": "Hello, I want to learn Python. How much is the monthly fee?"}
        ]
        res = await enroll_lead_in_3_step_sequence(
            db=db,
            lead=lead,
            dispatch_all_now=False,
            chat_history=initial_chat
        )
        assert res["status"] == "success"
        assert res["course"] == "Applied Python for Data Analysis & AI"
        assert res["discussion_topic"] == "Tuition & Flexible Monthly Installments"

        # Check that Step 1 is in DB, pending, and scheduled for ~2 hours from now
        stmt = select(ScheduledWhatsAppMessage).where(
            ScheduledWhatsAppMessage.recipient_phone == "2348011223344",
            ScheduledWhatsAppMessage.sequence_step == 1
        )
        msg_res = await db.execute(stmt)
        scheduled_msg = msg_res.scalar_one()
        assert scheduled_msg.status == "pending"
        assert "Applied Python for Data Analysis & AI" in scheduled_msg.body
        assert "₦100,000 / month" in scheduled_msg.body
        # Check time is roughly 2 hours in the future
        time_diff = (scheduled_msg.scheduled_for - datetime.datetime.now()).total_seconds() / 3600
        assert 1.9 <= time_diff <= 2.1

        # Step 2: Next chat interaction: Ngozi inquires about zero coding background
        # Ensure that calling enroll_lead_in_3_step_sequence dynamically updates Step 1
        second_chat = initial_chat + [
            {"sender": "assistant", "body": "Tuition is ₦100k/mo."},
            {"sender": "user", "body": "I have zero coding background, can a beginner do this?"}
        ]
        res2 = await enroll_lead_in_3_step_sequence(
            db=db,
            lead=lead,
            dispatch_all_now=False,
            chat_history=second_chat
        )
        assert res2["discussion_topic"] == "Starting with Zero Coding / Non-Tech Background"

        # Verify that the pending Step 1 record in the DB was updated
        msg_res2 = await db.execute(stmt)
        updated_msg = msg_res2.scalar_one()
        assert updated_msg.status == "pending"
        assert "zero coding experience" in updated_msg.body or "non-technical background" in updated_msg.body
        assert "Applied Python for Data Analysis & AI" in updated_msg.body

    await engine.dispose()
