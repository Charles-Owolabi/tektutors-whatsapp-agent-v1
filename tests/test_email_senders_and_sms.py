import pytest
import datetime
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from sqlalchemy import select

from app.main import app, init_db_and_seed
from app.database import AsyncSessionLocal
from app.models import EmailSender, Conversation, Message
from app.email_service import analyze_email_deliverability, resolve_sender_identity
from app.sms_service import send_chat_initiated_sms, SMS_DISPATCH_LOG


@pytest.fixture(autouse=True)
def mock_external_transports():
    with patch("app.email_service._send_smtp_email_sync", return_value=True), \
         patch("app.whatsapp.whatsapp_client.send_text_message", new_callable=AsyncMock) as mock_wa:
        mock_wa.return_value = {"messages": [{"id": "wamid.test"}]}
        yield


@pytest.mark.asyncio
async def test_multi_sender_personas_seeded():
    await init_db_and_seed()
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(EmailSender))
        senders = res.scalars().all()
        names = [s.name.lower() for s in senders]

        # Verify Charles, Ben, Agnes, Tara exist
        assert any("charles" in n for n in names)
        assert any("ben" in n for n in names)
        assert any("agnes" in n for n in names)
        assert any("tara" in n for n in names)


def test_sender_management_api():
    with TestClient(app) as client:
        # 1. List senders
        res = client.get("/api/emails/senders")
        assert res.status_code == 200
        senders = res.json()
        assert len(senders) >= 4

        # 2. Create custom sender persona
        create_res = client.post("/api/emails/senders", json={
            "name": "David from TekTutors",
            "email": "david@tektutors.com.ng",
            "reply_to": "tektutorsng@gmail.com",
            "role_title": "Senior Career Counselor",
            "phone_or_whatsapp": "+234 911 212 0531",
            "signature_markdown": "Best, David",
            "provider_type": "system_default",
            "is_default": False
        })
        assert create_res.status_code == 200
        new_sender = create_res.json()["sender"]
        new_id = new_sender["id"]
        assert new_sender["name"] == "David from TekTutors"

        # 3. Set as default sender
        def_res = client.post(f"/api/emails/senders/{new_id}/set-default")
        assert def_res.status_code == 200
        assert def_res.json()["success"] is True

        # 4. Test dispatch endpoint for sender
        test_send_res = client.post(f"/api/emails/senders/{new_id}/test", json={
            "test_to": "admissions.test@example.com"
        })
        assert test_send_res.status_code == 200
        assert test_send_res.json()["success"] is True

        # 5. Delete test sender
        del_res = client.delete(f"/api/emails/senders/{new_id}")
        assert del_res.status_code == 200
        assert del_res.json()["success"] is True


def test_deliverability_checker_api():
    with TestClient(app) as client:
        # Good deliverability draft (Natural casing, conversational, aligned envelope)
        good_payload = {
            "subject": "Your private 1-on-1 mentor slot in Data Analytics",
            "body": "Hi Alex,\n\nWe reserved your mentor onboarding slot for this weekend. Let us know if you have questions.",
            "layout_style": "conversational",
            "is_bulk": False,
            "sender_email": "tektutorsng@gmail.com"
        }
        res = client.post("/api/emails/deliverability-check", json=good_payload)
        assert res.status_code == 200
        data = res.json()
        assert data["score"] >= 85
        assert data["is_primary_inbox_optimized"] is True

        # Spammy draft (ALL CAPS, spam trigger words, symbols)
        bad_payload = {
            "subject": "CLAIM NOW CASH 100% FREE $$$!!!",
            "body": "Make money fast and get rich with crypto giveaway and risk-free guaranteed cash!",
            "layout_style": "card",
            "is_bulk": True,
            "sender_email": "spammer@gmail.com"
        }
        res_bad = client.post("/api/emails/deliverability-check", json=bad_payload)
        assert res_bad.status_code == 200
        data_bad = res_bad.json()
        assert data_bad["score"] < 60
        assert data_bad["is_primary_inbox_optimized"] is False


@pytest.mark.asyncio
async def test_chat_initiated_sms_alert():
    # Trigger SMS alert to default +2348063584517
    result = await send_chat_initiated_sms(
        student_phone="+2348123456789",
        student_name="Tunde Bakare",
        initial_message="Hello, I am interested in Data Analytics tuition options",
        notification_phone="+2348063584517"
    )

    assert result["notification_phone"] == "+2348063584517"
    assert result["student_phone"] == "+2348123456789"
    assert result["status"] in ("delivered", "simulated")
    assert len(SMS_DISPATCH_LOG) >= 1
    last_log = SMS_DISPATCH_LOG[-1]
    assert last_log["notification_phone"] == "+2348063584517"


def test_sms_segment_and_phone_normalization():
    from app.sms_service import calculate_sms_segments, normalize_phone_number

    # GSM-7 short message
    gsm_res = calculate_sms_segments("Hi Alex, your slot is confirmed!")
    assert gsm_res["encoding"] == "GSM-7"
    assert gsm_res["segment_count"] == 1
    assert gsm_res["chars_remaining_in_segment"] == 160 - len("Hi Alex, your slot is confirmed!")

    # Unicode message (contains emoji)
    uni_res = calculate_sms_segments("🎉 Welcome to TekTutors!")
    assert uni_res["encoding"] == "Unicode"
    assert uni_res["segment_count"] == 1

    # Phone number normalization
    assert normalize_phone_number("08063584517") == "+2348063584517"
    assert normalize_phone_number("2348063584517") == "+2348063584517"
    assert normalize_phone_number("+2348063584517") == "+2348063584517"
    assert normalize_phone_number("+14155552671") == "+14155552671"


def test_bulk_sms_api_suite():
    with TestClient(app) as client:
        # 1. Check SMS balance
        bal_res = client.get("/api/sms/balance")
        assert bal_res.status_code == 200
        bal_data = bal_res.json()
        assert "balance" in bal_data
        assert bal_data["sender_id"] == "TekTutors"

        # 2. Preview SMS text
        prev_res = client.post("/api/sms/preview", json={
            "message": "Hi {name}! Welcome to {course}.",
            "sample_name": "Tunde",
            "sample_course": "Machine Learning"
        })
        assert prev_res.status_code == 200
        prev_data = prev_res.json()
        assert "Tunde" in prev_data["rendered_preview"]
        assert "Machine Learning" in prev_data["rendered_preview"]
        assert prev_data["segment_count"] == 1

        # 3. Send single test SMS
        single_res = client.post("/api/sms/send-single", json={
            "phone": "08063584517",
            "name": "Chinedu",
            "sender_id": "TekTutors",
            "message": "Hi {name}, your TekTutors consultation is confirmed."
        })
        assert single_res.status_code == 200
        assert single_res.json()["success"] is True

        # 4. Broadcast bulk SMS to recipient list
        bulk_res = client.post("/api/sms/broadcast", json={
            "message": "Hi {name}, next cohort for {course} starts Saturday!",
            "sender_id": "TekTutors",
            "channel": "generic",
            "recipients": [
                {"phone": "08011112222", "name": "Amina", "course": "Data Analytics"},
                {"phone": "08033334444", "name": "Emeka", "course": "Power BI"}
            ]
        })
        assert bulk_res.status_code == 200
        bulk_data = bulk_res.json()
        assert bulk_data["success"] is True
        assert bulk_data["campaign_summary"]["total"] == 2

        # 5. Verify SMS logs
        logs_res = client.get("/api/sms/logs")
        assert logs_res.status_code == 200
        logs = logs_res.json()
        assert len(logs) >= 2

