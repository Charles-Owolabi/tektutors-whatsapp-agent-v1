import pytest
from fastapi.testclient import TestClient
from app.main import app, init_db_and_seed

@pytest.mark.asyncio
async def test_courses_management_api():
    # Make sure DB is initialized and seeded
    await init_db_and_seed()
    
    with TestClient(app) as client:
        # 1. Get initial courses
        get_res = client.get("/api/courses")
        assert get_res.status_code == 200
        courses = get_res.json()["courses"]
        initial_count = len(courses)

        # 2. Add a new course
        new_course = {
            "title": "Test Web Development",
            "slug": "test-web-dev",
            "price": 199.99,
            "duration_weeks": 6,
            "description": "Learn HTML, CSS, JS",
            "syllabus": "Week 1: HTML, Week 2: CSS, Week 3-6: JS",
            "prerequisites": "None",
            "career_outcomes": "Junior Dev",
            "is_active": True
        }
        post_res = client.post("/api/courses", json=new_course)
        assert post_res.status_code == 200
        course = post_res.json()["course"]
        course_id = course["id"]
        assert course["title"] == "Test Web Development"

        # Check total count increased
        get_res = client.get("/api/courses")
        assert len(get_res.json()["courses"]) == initial_count + 1

        # 3. Update the course
        updated_data = {
            "price": 249.99,
            "title": "Test Advanced Web Development"
        }
        put_res = client.put(f"/api/courses/{course_id}", json=updated_data)
        assert put_res.status_code == 200
        updated_course = put_res.json()["course"]
        assert updated_course["price"] == 249.99
        assert updated_course["title"] == "Test Advanced Web Development"

        # 4. Delete the course
        del_res = client.delete(f"/api/courses/{course_id}")
        assert del_res.status_code == 200
        assert del_res.json()["status"] == "deleted"

        # Check count is back to initial
        get_res = client.get("/api/courses")
        assert len(get_res.json()["courses"]) == initial_count


@pytest.mark.asyncio
async def test_faqs_management_api():
    await init_db_and_seed()
    
    with TestClient(app) as client:
        # 1. Get initial FAQs
        get_res = client.get("/api/faqs")
        assert get_res.status_code == 200
        faqs = get_res.json()["faqs"]
        initial_count = len(faqs)

        # 2. Add a new FAQ
        new_faq = {
            "category": "Testing",
            "question": "Is this a test question?",
            "answer": "Yes, this is a test answer."
        }
        post_res = client.post("/api/faqs", json=new_faq)
        assert post_res.status_code == 200
        faq = post_res.json()["faq"]
        faq_id = faq["id"]
        assert faq["question"] == "Is this a test question?"

        # Check count increased
        get_res = client.get("/api/faqs")
        assert len(get_res.json()["faqs"]) == initial_count + 1

        # 3. Update the FAQ
        updated_data = {
            "answer": "No, it is an updated test answer."
        }
        put_res = client.put(f"/api/faqs/{faq_id}", json=updated_data)
        assert put_res.status_code == 200
        updated_faq = put_res.json()["faq"]
        assert updated_faq["answer"] == "No, it is an updated test answer."

        # 4. Delete the FAQ
        del_res = client.delete(f"/api/faqs/{faq_id}")
        assert del_res.status_code == 200
        assert del_res.json()["status"] == "deleted"

        # Check count is back to initial
        get_res = client.get("/api/faqs")
        assert len(get_res.json()["faqs"]) == initial_count


@pytest.mark.asyncio
async def test_settings_api():
    await init_db_and_seed()
    with TestClient(app) as client:
        # GET settings
        get_res = client.get("/api/settings")
        assert get_res.status_code == 200
        settings_data = get_res.json()
        assert "agent_name" in settings_data
        assert settings_data["global_ai_enabled"] is True

        # PUT settings (update)
        updated_settings = {
            "agent_name": "Assistant Bot",
            "global_ai_enabled": False,
            "system_prompt": "You are Assistant Bot, a helpful support advisor."
        }
        put_res = client.put("/api/settings", json=updated_settings)
        assert put_res.status_code == 200
        new_settings = put_res.json()
        assert new_settings["agent_name"] == "Assistant Bot"
        assert new_settings["global_ai_enabled"] is False

        # Reset settings to default active
        client.put("/api/settings", json={
            "agent_name": "Tara",
            "global_ai_enabled": True
        })


@pytest.mark.asyncio
async def test_crm_stats_and_export():
    await init_db_and_seed()
    with TestClient(app) as client:
        # Fetch CRM statistics
        stats_res = client.get("/api/crm/stats")
        assert stats_res.status_code == 200
        stats = stats_res.json()
        assert "total_leads" in stats
        assert "pipeline_value" in stats
        assert "conversion_rate" in stats

        # Export leads as CSV
        export_res = client.get("/api/crm/export")
        assert export_res.status_code == 200
        assert export_res.headers["content-type"] == "text/csv; charset=utf-8"
        assert "attachment" in export_res.headers["content-disposition"]
        assert "tektutors_leads.csv" in export_res.headers["content-disposition"]


@pytest.mark.asyncio
async def test_auto_escalation_triggers():
    await init_db_and_seed()
    
    # Clean database for this specific test number to prevent local DB pollution from failing tests
    from app.database import AsyncSessionLocal
    from app.models import Conversation, Message, Lead
    from sqlalchemy import delete, select
    async with AsyncSessionLocal() as db:
        conv_id_stmt = select(Conversation.id).where(Conversation.phone == "2348122334455")
        conv_id_res = await db.execute(conv_id_stmt)
        conv_ids = conv_id_res.scalars().all()
        if conv_ids:
            await db.execute(delete(Message).where(Message.conversation_id.in_(conv_ids)))
        await db.execute(delete(Conversation).where(Conversation.phone == "2348122334455"))
        await db.execute(delete(Lead).where(Lead.phone == "2348122334455"))
        await db.commit()

    with TestClient(app) as client:
        # Simulate chat containing keyword trigger
        payload = {
            "phone": "2348122334455",
            "message": "Get me a manager right now"
        }
        res = client.post("/api/simulator/chat", json=payload)
        assert res.status_code == 200
        data = res.json()
        
        # Verify conversation state was set to inactive (takeover)
        assert data["ai_active"] is False
        assert "advisor" in data["ai_response"]["body"].lower()
