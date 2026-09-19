import uuid
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from app.main import app, init_db_and_seed
from app.agent import agent_manager

@pytest.fixture(autouse=True)
def mock_whatsapp_client():
    with patch("app.dashboard_routes.whatsapp_client.send_interactive_buttons", new_callable=AsyncMock) as mock_btns, \
         patch("app.dashboard_routes.whatsapp_client.send_text_message", new_callable=AsyncMock) as mock_txt:
        mock_btns.return_value = {"status": "mocked"}
        mock_txt.return_value = {"status": "mocked"}
        yield

@pytest.mark.asyncio
async def test_campaigns_broadcast_api():
    await init_db_and_seed()
    with TestClient(app) as client:
        # 1. List campaigns
        res = client.get("/api/campaigns")
        assert res.status_code == 200
        campaigns = res.json()["campaigns"]
        assert len(campaigns) >= 4
        assert any(c["id"] == "scholarship_flash" for c in campaigns)
        first_c = next(c for c in campaigns if c["id"] == "scholarship_flash")
        assert "template_body_original" in first_c

        # 2. Edit a campaign template via PUT /api/campaigns/{id}
        edit_res = client.put("/api/campaigns/scholarship_flash", json={
            "template_body": "Hello {{name}}, this is a custom edited campaign for {{course}}! Enroll today and save ₦10,000."
        })
        assert edit_res.status_code == 200
        edit_data = edit_res.json()
        assert edit_data["status"] == "success"
        assert "custom edited campaign" in edit_data["template_body"]

        # Verify edited campaign is reflected in list
        res_updated = client.get("/api/campaigns")
        updated_c = next(c for c in res_updated.json()["campaigns"] if c["id"] == "scholarship_flash")
        assert "custom edited campaign" in updated_c["template_body"]

        # 3. Dispatch broadcast with custom edited message
        send_res = client.post("/api/campaigns/send", json={
            "campaign_id": "scholarship_flash",
            "target_audience": "all",
            "custom_message": "Special flash announcement: Hi {{name}}, your custom slot for {{course}} is ready!"
        })
        assert send_res.status_code == 200
        data = send_res.json()
        assert data["status"] == "success"
        assert data["recipients_count"] >= 1

@pytest.mark.asyncio
async def test_lead_stage_notes_and_summary_api():
    await init_db_and_seed()
    with TestClient(app) as client:
        # First ensure we have at least one lead
        leads_res = client.get("/api/leads")
        assert leads_res.status_code == 200
        leads = leads_res.json()["leads"]
        
        if not leads:
            # Create a test lead
            lead_create = client.post("/api/leads", json={
                "phone": "2348099887766",
                "name": "Alex Test",
                "email": "alex@example.com",
                "course_interest": "Data Analytics",
                "status": "new"
            })
            lead_id = lead_create.json()["lead"]["id"]
        else:
            lead_id = leads[0]["id"]

        # 1. Update lead stage to hot
        status_res = client.put(f"/api/crm/lead/{lead_id}/status", json={
            "status": "hot",
            "notes": "Interested in weekend cohort"
        })
        assert status_res.status_code == 200
        assert status_res.json()["lead"]["status"] == "hot"

        # 2. Update private notes
        notes_res = client.put(f"/api/crm/lead/{lead_id}/notes", json={
            "notes": "Prefers morning calls on Friday"
        })
        assert notes_res.status_code == 200
        assert notes_res.json()["notes"] == "Prefers morning calls on Friday"

        # 3. Get AI executive summary
        sum_res = client.get(f"/api/crm/lead/{lead_id}/summary")
        assert sum_res.status_code == 200
        summary_data = sum_res.json()
        assert summary_data["lead_id"] == lead_id
        assert summary_data["score"] >= 95  # Because status is hot

@pytest.mark.asyncio
async def test_appointments_api():
    await init_db_and_seed()
    with TestClient(app) as client:
        # 1. List appointments
        get_res = client.get("/api/appointments")
        assert get_res.status_code == 200
        appointments = get_res.json()["appointments"]

        if appointments:
            app_id = appointments[0]["id"]
            # 2. Update appointment status
            put_res = client.put(f"/api/appointments/{app_id}", json={
                "status": "completed"
            })
            assert put_res.status_code == 200
            assert put_res.json()["appointment"]["status"] == "completed"

@pytest.mark.asyncio
async def test_settings_persona_tone_api():
    await init_db_and_seed()
    with TestClient(app) as client:
        # 1. Update settings with persona tone and business hours
        update_payload = {
            "agent_name": "Tara AI",
            "persona_tone": "closer",
            "business_hours": "8:30 AM - 6:30 PM (Mon-Sat)",
            "away_message": "Our admissions counselors will be with you tomorrow morning."
        }
        put_res = client.put("/api/settings", json=update_payload)
        assert put_res.status_code == 200
        updated = put_res.json()
        assert updated["agent_name"] == "Tara AI"
        assert updated["persona_tone"] == "closer"

        # 2. Fetch settings and verify
        get_res = client.get("/api/settings")
        assert get_res.status_code == 200
        assert get_res.json()["persona_tone"] == "closer"

@pytest.mark.asyncio
async def test_course_presentation_and_numbered_selection():
    """Verify courses are formatted as numbered tracks with explicit prompt to pick by number or course name."""
    await init_db_and_seed()
    orig_llm = agent_manager.llm_with_tools
    agent_manager.llm_with_tools = None
    try:
        with TestClient(app) as client:
            # 1. Ask about courses
            res = client.post("/api/simulator/chat", json={
                "phone": "2348011223344",
                "message": "What courses do you offer?"
            })
            assert res.status_code == 200
            body = res.json()["ai_response"]["body"]
            
            # Verify numbered tracks
            assert "1️⃣" in body
            assert "Data Analytics" in body
            # Verify outline instruction inviting choice by number or typing course
            assert "reply with the number" in body.lower()
            assert "type the name" in body.lower()

            # 2. User selects by number: "1"
            sel_num_res = client.post("/api/simulator/chat", json={
                "phone": "2348011223344",
                "message": "1"
            })
            assert sel_num_res.status_code == 200
            sel_num_body = sel_num_res.json()["ai_response"]["body"]
            assert "Track 1" in sel_num_body
            assert "Data Analytics" in sel_num_body
            assert "Tuition" in sel_num_body

            # 3. User selects by typing course name: "Power BI"
            sel_name_res = client.post("/api/simulator/chat", json={
                "phone": "2348011223344",
                "message": "I want Power BI"
            })
            assert sel_name_res.status_code == 200
            sel_name_body = sel_name_res.json()["ai_response"]["body"]
            assert "Track 4" in sel_name_body
            assert "Power BI" in sel_name_body
    finally:
        agent_manager.llm_with_tools = orig_llm

@pytest.mark.asyncio
async def test_analytics_funnel_and_webhook_test_api():
    """Verify Executive Sales Funnel and Outbound Webhook Test endpoints."""
    await init_db_and_seed()
    with TestClient(app) as client:
        # 1. Funnel telemetry
        funnel_res = client.get("/api/analytics/funnel")
        assert funnel_res.status_code == 200
        data = funnel_res.json()
        assert "funnel" in data
        assert len(data["funnel"]) == 5
        assert "channels" in data
        assert "roi_metrics" in data
        assert "projected_mrr" in data["roi_metrics"]

        # 2. Outbound Webhook test ping
        wh_res = client.post("/api/settings/webhook-test", json={
            "url": "https://hooks.zapier.com/hooks/catch/123/abc"
        })
        assert wh_res.status_code == 200
        assert wh_res.json()["status"] == "success"

@pytest.mark.asyncio
async def test_multi_currency_settings_and_crm_stats():
    """Verify Multi-Currency support in SystemConfig and CRM Stats."""
    await init_db_and_seed()
    with TestClient(app) as client:
        # 1. Update currency to USD
        put_res = client.put("/api/settings", json={
            "currency": "USD"
        })
        assert put_res.status_code == 200
        assert put_res.json()["currency"] == "USD"
        assert put_res.json()["currency_symbol"] == "$"

        # 2. Check CRM stats reflects $ currency symbol
        stats_res = client.get("/api/crm/stats")
        assert stats_res.status_code == 200
        assert "$" in stats_res.json()["pipeline_value"]

        # 3. Restore to NGN
        client.put("/api/settings", json={"currency": "NGN"})

@pytest.mark.asyncio
async def test_broadcast_campaign_with_custom_external_numbers():
    """Verify dispatching a WhatsApp broadcast to external customer numbers not in DB."""
    await init_db_and_seed()
    tag = str(uuid.uuid4().int)[:6]
    p1 = f"23481{tag}1"
    p2 = f"23481{tag}2"
    p3 = f"23481{tag}3"
    with TestClient(app) as client:
        raw_contacts = (
            f"{p1}, External Student One, Data Science\n"
            f"+234 81 {tag} 2, External Student Two\n"
            f"081{tag}3\n"
        )
        send_res = client.post("/api/campaigns/send", json={
            "campaign_id": "cart_recovery_slot_expiring",
            "target_audience": "custom",
            "custom_numbers_raw": raw_contacts
        })
        assert send_res.status_code == 200
        data = send_res.json()
        assert data["status"] == "success"
        assert data["recipients_count"] == 3

        # Verify leads were auto-created in the database
        leads_res = client.get("/api/leads")
        assert leads_res.status_code == 200
        leads = leads_res.json()["leads"]
        phones = [l["phone"] for l in leads]
        assert p1 in phones
        assert p2 in phones
        assert p3 in phones

@pytest.mark.asyncio
async def test_bulk_import_leads_api():
    """Verify bulk importing external customer leads into CRM via API."""
    await init_db_and_seed()
    tag = str(uuid.uuid4().int)[:6]
    p1 = f"23480{tag}1"
    p2 = f"080{tag}2"
    with TestClient(app) as client:
        csv_content = (
            f"{p1}, Chidi Okeke, Python Backend, chidi.{tag}@example.com\n"
            f"{p2}, Amina Yusuf, Full Stack\n"
            f"{p1}, Chidi Okeke, Duplicate Should Be Skipped\n"
        )
        import_res = client.post("/api/crm/leads/import", json={
            "raw_text": csv_content
        })
        assert import_res.status_code == 200
        data = import_res.json()
        assert data["status"] == "success"
        assert data["imported"] >= 2
        assert data["skipped"] >= 1

def test_convert_markdown_tables_to_whatsapp():
    """Verify raw markdown tables are transformed into clean, readable WhatsApp cards."""
    from app.agent import convert_markdown_tables_to_whatsapp, sanitize_whatsapp_message
    
    raw_user_table = (
        "| # | Track | Duration (weeks) | What You’ll Master |\n"
        "|---|-------|------------------|--------------------|\n"
        "| *1* | *Data Analytics & BI Accelerator* | *10 wks* | Excel, SQL, Power BI, Python + real‑world capstone projects |\n"
        "| *2* | *Excel for Data Analysis* | *6‑8 wks* | Advanced formulas, Power Query, dashboards, data‑visual storytelling |\n"
        "| *3* | *SQL for Analytics & Data Engineering* | *6‑8 wks* | Data modeling, complex queries, performance tuning, ETL basics |\n"
        "| *4* | *Power BI & Business Intelligence* | *6‑8 wks* | Data modeling, DAX, interactive reports, publishing to the cloud |\n"
        "| *5* | *Applied Python for Analytics & AI* | *6‑8 wks* | Python fundamentals, pandas, data‑visualization, intro to AI/ML |\n"
        "| *6* | *Explore Other Specialized Tracks* | *6‑20 wks* (depending on track) | R for Data Analysis, Advanced Excel & Power Query, Data Science (16‑20 wks), Machine Learning (16 wks), Business Analysis (10 wks), Financial/Marketing/HR Analytics (6‑8 wks) |"
    )

    cleaned = sanitize_whatsapp_message(raw_user_table)
    
    # 1. Verify no markdown table pipe symbols remain
    assert "|" not in cleaned
    # 2. Verify numbered badges and clean bold titles for attention
    assert "1️⃣ *Data Analytics & BI Accelerator*" in cleaned
    assert "2️⃣ *Excel for Data Analysis*" in cleaned
    assert "3️⃣ *SQL for Analytics & Data Engineering*" in cleaned
    assert "4️⃣ *Power BI & Business Intelligence*" in cleaned
    assert "5️⃣ *Applied Python for Analytics & AI*" in cleaned
    assert "6️⃣ *Explore Other Specialized Tracks*" in cleaned
    # 3. Verify clean bold labels
    assert "⏱️ *Duration (weeks):*" in cleaned
    assert "💡 *What You’ll Master:*" in cleaned
    assert "10 wks" in cleaned
    assert "Excel, SQL, Power BI, Python" in cleaned


def test_whatsapp_bold_and_clean_formatting():
    """Verify bold formatting is preserved using WhatsApp single-asterisks and markdown double-asterisks are normalized."""
    from app.agent import sanitize_whatsapp_message

    # Input with markdown double asterisks produced by LLMs
    user_chat = (
        "I've tentatively set up a **15-minute discovery call** for you.\n"
        "To make sure we're fully prepared, could you please share:\n\n"
        "1️⃣ **Your full name**\n"
        "2️⃣ **Which track (1-6) or career goal** you're most interested in\n"
        "3️⃣ **Preferred date & time** for the call (evenings or weekends work best)\n\n"
        "Once I have those details, I'll confirm the slot and send you a calendar invite. Looking forward to chatting! 🌟"
    )

    cleaned = sanitize_whatsapp_message(user_chat)
    # Double asterisks must be normalized to single asterisks for WhatsApp
    assert "**" not in cleaned
    assert "*15-minute discovery call*" in cleaned
    assert "1️⃣ *Your full name*" in cleaned
    assert "2️⃣ *Which track (1-6) or career goal*" in cleaned
    assert "3️⃣ *Preferred date & time*" in cleaned
    assert "Looking forward to chatting! 🌟" in cleaned

