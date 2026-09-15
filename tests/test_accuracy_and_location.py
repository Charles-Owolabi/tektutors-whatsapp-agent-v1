import pytest
import json
from fastapi.testclient import TestClient
from app.main import app, init_db_and_seed
from app.agent import agent_manager
from app.tools import get_course_faq_answer

@pytest.mark.asyncio
async def test_faq_scoring_accuracy():
    """Verify that get_course_faq_answer returns relevant FAQ for location and address queries, not unrelated FAQs."""
    await init_db_and_seed()
    
    # 1. Location / physical address query
    res_raw = await get_course_faq_answer.ainvoke({"question_or_topic": "do you have physical address"})
    res = json.loads(res_raw)
    assert isinstance(res, list) and len(res) > 0
    top_faq = res[0]
    # Must be about physical office / address, NOT about completing a course in one month
    assert "online" in top_faq["answer"].lower() or "physical" in top_faq["question"].lower() or "address" in top_faq["question"].lower()
    assert "complete a larger skill" not in top_faq["answer"].lower()

@pytest.mark.asyncio
async def test_simulator_physical_address_inquiry():
    """Verify the chat simulator returns an accurate, smart location response for 'do you have physical address'."""
    await init_db_and_seed()
    with TestClient(app) as client:
        res = client.post("/api/simulator/chat", json={
            "phone": "2348011998877",
            "message": "do you have physical address"
        })
        assert res.status_code == 200
        data = res.json()
        body = data["ai_response"]["body"]

        # Response must clearly explain 100% online format, Lagos hub, contact info, and registration link
        assert "100% live online" in body.lower() or "100% online" in body.lower()
        assert "lagos" in body.lower()
        assert "tektutors.com.ng" in body.lower()
        # Ensure it NEVER dumps the irrelevant skill in a month answer
        assert "depending on the skill" not in body.lower()
        assert "larger skill" not in body.lower()

@pytest.mark.asyncio
async def test_location_variations():
    """Verify multiple natural phrasing variations for physical address and location."""
    await init_db_and_seed()
    with TestClient(app) as client:
        queries = [
            "where are you located",
            "where is your office",
            "what is your physical address",
            "can I visit your office in Lagos"
        ]
        for q in queries:
            res = client.post("/api/simulator/chat", json={
                "phone": f"23480119988{len(q)}",
                "message": q
            })
            assert res.status_code == 200
            body = res.json()["ai_response"]["body"]
            assert "online" in body.lower()
            assert "lagos" in body.lower()
            assert "larger skill" not in body.lower()

@pytest.mark.asyncio
async def test_multi_turn_payment_then_address():
    """Verify multi-turn flow: inquiry about payment plan followed by physical address inquiry."""
    await init_db_and_seed()
    with TestClient(app) as client:
        phone = "2348019990001"
        # Turn 1: Payment plan
        res1 = client.post("/api/simulator/chat", json={
            "phone": phone,
            "message": "Tell me more about the month-to-month payment plan."
        })
        assert res1.status_code == 200
        body1 = res1.json()["ai_response"]["body"]
        assert "100,000" in body1
        assert "month" in body1.lower()

        # Turn 2: Physical address
        res2 = client.post("/api/simulator/chat", json={
            "phone": phone,
            "message": "do you have physical address"
        })
        assert res2.status_code == 200
        body2 = res2.json()["ai_response"]["body"]
        assert "100% live online" in body2.lower() or "online" in body2.lower()
        assert "lagos" in body2.lower()
        assert "larger skill" not in body2.lower()


@pytest.mark.asyncio
async def test_discount_pricing_accuracy():
    """Verify that 10% discount correctly calculates ₦90,000 (saving ₦10,000) and NEVER ₦900,000."""
    await init_db_and_seed()
    with TestClient(app) as client:
        phone = "2348019990002"
        res = client.post("/api/simulator/chat", json={
            "phone": phone,
            "message": "Do you offer any discounts or promo codes if I pay upfront?"
        })
        assert res.status_code == 200
        body = res.json()["ai_response"]["body"]
        
        # Must show ₦90,000 for 10% discount
        assert "90,000" in body
        # Must NEVER hallucinate 900,000 or 1,000,000 from multiplying 10 weeks
        assert "900,000" not in body
        assert "1,000,000" not in body
        assert "100,000" in body


@pytest.mark.asyncio
async def test_sanitize_pricing_hallucinations_guard():
    """Direct unit test of pricing hallucination guard with user's exact hallucinated snippet."""
    from app.agent import sanitize_pricing_hallucinations

    hallucinated = (
        "📌 ₦100,000 / month – flexible month-to-month billing (cancel anytime)\n"
        "📌 10% discount if you pay the full course upfront (e.g., 10-wk Data Analytics = ₦900,000)"
    )
    cleaned = sanitize_pricing_hallucinations(hallucinated)
    assert "900,000" not in cleaned
    assert "90,000" in cleaned
    assert "₦100,000 / month" in cleaned


@pytest.mark.asyncio
async def test_power_bi_and_single_tool_duration():
    """Verify that Power BI and single-tool courses are 6-8 weeks (8 weeks), not 12 weeks."""
    await init_db_and_seed()
    with TestClient(app) as client:
        # 1. Ask about Power BI training
        res = client.post("/api/simulator/chat", json={
            "phone": "2348019990003",
            "message": "Do you offer Power BI training?"
        })
        assert res.status_code == 200
        body = res.json()["ai_response"]["body"]
        assert "Power BI" in body
        assert "6-8" in body or "8" in body
        assert "12 Weeks" not in body
        assert "12 wks" not in body

        # 2. Verify course database records
        from app.database import AsyncSessionLocal
        from app.models import Course
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            pbi_res = await db.execute(select(Course).where(Course.slug == "power-bi-data-analytics"))
            pbi = pbi_res.scalar_one()
            assert pbi.duration_weeks == 8
            assert "6-8 weeks" in pbi.description

            py_res = await db.execute(select(Course).where(Course.slug == "applied-python-for-data-analysis"))
            py = py_res.scalar_one()
            assert py.duration_weeks == 8
            assert "6-8 weeks" in py.description

