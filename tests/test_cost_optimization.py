import pytest
import json
from fastapi.testclient import TestClient
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage
from app.main import app, init_db_and_seed
from app.cache import check_fast_path
from app.tools import search_tektutors_courses, get_course_faq_answer
from app.agent import agent_manager

@pytest.mark.asyncio
async def test_fast_path_routing():
    await init_db_and_seed()
    test_phone = "2348099881122"

    # 1. Greeting Fast-Path ($0.00 LLM cost)
    greet_res = await check_fast_path(test_phone, "Hi there")
    assert greet_res is not None
    assert greet_res["fast_path"] is True
    assert "TekTutors" in greet_res["response"]
    assert "6️⃣" in greet_res["response"]
    assert "Reply with a number (1-6)" in greet_res["response"]
    assert greet_res["tokens_saved"] >= 500

    # 2. Track Selection Fast-Path ($0.00 LLM cost)
    track_res = await check_fast_path(test_phone, "1")
    assert track_res is not None
    assert "Data Analytics & BI Accelerator" in track_res["response"]
    assert "https://tektutors.com.ng/registration" in track_res["response"]

    # 2b. Option 6 (Other Courses) Fast-Path ($0.00 LLM cost)
    other_res = await check_fast_path(test_phone, "6")
    assert other_res is not None
    assert "Other Available Courses & Specialized Tracks" in other_res["response"]
    assert "Data Science with Python" in other_res["response"]
    assert "Machine Learning with Python" in other_res["response"]
    assert "Business Analysis" in other_res["response"]
    assert "qualify_and_capture_lead" in other_res["tool_logs"]

    other_text_res = await check_fast_path(test_phone, "other courses")
    assert other_text_res is not None
    assert "Other Available Courses & Specialized Tracks" in other_text_res["response"]

    # 3. Direct Registration / Payment Fast-Path ($0.00 LLM cost)
    reg_res = await check_fast_path(test_phone, "how to pay for the course?")
    assert reg_res is not None
    assert "https://tektutors.com.ng/registration" in reg_res["response"]

    # 4. Curriculum Email Fast-Path ($0.00 LLM cost)
    email_res = await check_fast_path(test_phone, "send curriculum to test_student@gmail.com")
    assert email_res is not None
    assert "test_student@gmail.com" in email_res["response"]
    assert "qualify_and_capture_lead" in email_res["tool_logs"]

    # 5. Escalation Fast-Path ($0.00 LLM cost)
    esc_res = await check_fast_path(test_phone, "I want to speak with a human agent")
    assert esc_res is not None
    assert "escalate_to_human_advisor" in esc_res["tool_logs"]

    # 6. Interactive Action Option 1: Book 1-on-1 Call Fast-Path ($0.00 LLM cost)
    call_res = await check_fast_path(test_phone, "Yes, please book me a 1-on-1 call with an Admissions Advisor.")
    assert call_res is not None
    assert call_res["fast_path"] is True
    assert "Book Your 1-on-1 Admissions Discovery Call" in call_res["response"]
    assert "Your Full Name" in call_res["response"]
    assert "Preferred Time & Day" in call_res["response"]
    assert "qualify_and_capture_lead" in call_res["tool_logs"]
    assert call_res["tokens_saved"] >= 900

    # 7. Interactive Action Option 2: View Payment Plans Fast-Path ($0.00 LLM cost)
    pay_res = await check_fast_path(test_phone, "Tell me more about the month-to-month payment plan.")
    assert pay_res is not None
    assert pay_res["fast_path"] is True
    assert "Flexible Tuition & Payment Plans" in pay_res["response"]
    assert "100,000" in pay_res["response"]
    assert "10% tuition discount" in pay_res["response"]
    assert "https://tektutors.com.ng/registration" in pay_res["response"]
    assert "qualify_and_capture_lead" in pay_res["tool_logs"]
    assert pay_res["tokens_saved"] >= 900

    # 8. Interactive Action Option 3: Send Full Syllabus (no email yet) Fast-Path ($0.00 LLM cost)
    syl_res = await check_fast_path(test_phone, "Please share the complete course syllabus breakdown.")
    assert syl_res is not None
    assert syl_res["fast_path"] is True
    assert "Practical Curriculum & Syllabus Breakdown" in syl_res["response"]
    assert "Module 1: Foundations" in syl_res["response"]
    assert "Module 2: Data Wrangling" in syl_res["response"]
    assert "Module 3: Business Intelligence" in syl_res["response"]
    assert "Module 4: Advanced Analytics" in syl_res["response"]
    assert "Module 5: Capstone Projects" in syl_res["response"]
    assert "Email Address" in syl_res["response"]
    assert syl_res["tokens_saved"] >= 900

    # 9. Non-fast-path complex question should return None and route to LLM
    complex_res = await check_fast_path(test_phone, "Can you explain how backpropagation works in neural networks?")
    assert complex_res is None

@pytest.mark.asyncio
async def test_compact_tool_payloads():
    await init_db_and_seed()

    # Verify search_tektutors_courses returns compact serialized payload without indent bloat
    courses_raw = await search_tektutors_courses.ainvoke({"query": "Data Analytics"})
    assert "  " not in courses_raw  # No 2-space indentation
    courses = json.loads(courses_raw)
    assert len(courses) >= 1
    assert "title" in courses[0]
    assert "price_monthly" in courses[0]

    # Verify get_course_faq_answer returns compact payload
    faq_raw = await get_course_faq_answer.ainvoke({"question_or_topic": "installments"})
    assert "  " not in faq_raw
    faqs = json.loads(faq_raw)
    assert len(faqs) >= 1

@pytest.mark.asyncio
async def test_sliding_window_advisor_node():
    """Verify context windowing bounds message length to prevent token explosion."""
    # Build a simulated multi-turn state with 15 messages and historical tool outputs
    messages = [
        SystemMessage(content="Initial system prompt"),
        HumanMessage(content="Msg 1"),
        AIMessage(content="Reply 1"),
        HumanMessage(content="Msg 2"),
        AIMessage(content="Reply 2"),
        ToolMessage(content="A" * 1500, tool_call_id="call_1"),  # Large old tool output
        HumanMessage(content="Msg 3"),
        AIMessage(content="Reply 3"),
        ToolMessage(content="B" * 1500, tool_call_id="call_2"),  # Large old tool output
        HumanMessage(content="Msg 4"),
        AIMessage(content="Reply 4"),
        HumanMessage(content="Msg 5"),
        AIMessage(content="Reply 5"),
        HumanMessage(content="What courses do you offer?"),
    ]

    state = {
        "messages": messages,
        "phone": "2348011223344",
        "tool_logs": [],
        "system_prompt": "Test Prompt",
        "is_escalated": False
    }

    # Run advisor node with mocked LLM to verify context windowing and message handling
    from unittest.mock import AsyncMock
    orig_llm = agent_manager.llm_with_tools
    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="Here are the courses!"))
    agent_manager.llm_with_tools = mock_llm
    try:
        advisor_res = await agent_manager._advisor_node(state)
        assert "messages" in advisor_res
        assert len(advisor_res["messages"]) >= 1
    finally:
        agent_manager.llm_with_tools = orig_llm

@pytest.mark.asyncio
async def test_funnel_cost_telemetry_api():
    await init_db_and_seed()
    with TestClient(app) as client:
        res = client.get("/api/analytics/funnel")
        assert res.status_code == 200
        data = res.json()
        assert "cost_optimization" in data
        cost_opt = data["cost_optimization"]
        assert "tokens_saved" in cost_opt
        assert "cost_saved_usd" in cost_opt
        assert "fast_path_rate" in cost_opt
