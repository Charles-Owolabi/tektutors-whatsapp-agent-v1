import pytest
import json
from app.main import init_db_and_seed
from app.tools import (
    search_tektutors_courses,
    get_course_faq_answer,
    qualify_and_capture_lead,
    schedule_advisor_call,
    escalate_to_human_advisor,
    generate_enrollment_checkout
)

@pytest.mark.asyncio
async def test_search_tektutors_courses():
    await init_db_and_seed()
    result_json = await search_tektutors_courses.ainvoke({"query": "Python"})
    courses = json.loads(result_json)
    assert len(courses) > 0
    assert "Python" in courses[0]["title"]

@pytest.mark.asyncio
async def test_get_course_faq_answer():
    await init_db_and_seed()
    result_json = await get_course_faq_answer.ainvoke({"question_or_topic": "monthly"})
    faqs = json.loads(result_json)
    assert len(faqs) > 0
    assert "monthly" in faqs[0]["answer"].lower()

@pytest.mark.asyncio
async def test_qualify_and_capture_lead():
    await init_db_and_seed()
    res = await qualify_and_capture_lead.ainvoke({
        "phone": "2348123456789",
        "name": "Sarah Connor",
        "email": "sarah@example.com",
        "course_interest": "Data Analytics",
        "skill_level": "Beginner"
    })
    assert "Lead captured successfully" in res

@pytest.mark.asyncio
async def test_schedule_advisor_call():
    await init_db_and_seed()
    res = await schedule_advisor_call.ainvoke({
        "phone": "2348123456789",
        "name": "Sarah Connor",
        "preferred_time": "Saturday 2PM",
        "course": "Data Analytics"
    })
    assert "Advisor Call Scheduled" in res

@pytest.mark.asyncio
async def test_escalate_to_human_advisor():
    await init_db_and_seed()
    res = await escalate_to_human_advisor.ainvoke({
        "phone": "2348123456789",
        "reason": "Test escalation"
    })
    assert "escalated to human advisor" in res

@pytest.mark.asyncio
async def test_generate_enrollment_checkout_link():
    await init_db_and_seed()
    res_str = await generate_enrollment_checkout.ainvoke({
        "course_title": "Data Analytics",
        "payment_plan": "monthly_installment",
        "phone": "2348123456789",
        "student_name": "Test Student"
    })
    invoice = json.loads(res_str)
    assert invoice["checkout_url"] == "https://tektutors.com.ng/registration"
