import pytest
import io
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app, init_db_and_seed
from app.database import AsyncSessionLocal
from app.models import Lead, EmailLog, ScheduledEmail
from app.email_service import (
    parse_campaign_csv_data,
    DAILY_DRIP_SEQUENCE,
    PREBUILT_EMAIL_TEMPLATES,
    render_branded_email_html,
    send_email_async
)

@pytest.mark.asyncio
async def test_parse_campaign_csv_data_standards():
    sample_csv = """Full Name,Email Address,Course Track,WhatsApp Number
Tunde Bakare,tunde@example.com,Data Analytics & BI Accelerator,08012345678
Ngozi Eze,ngozi.eze@globaltech.io,AI & Machine Learning Foundations,+2348098765432
Duplicate Person,tunde@example.com,Data Analytics,08011112222
Invalid Contact,not-an-email,Excel,08099999999
Empty Email,,SQL,
"""
    parsed = parse_campaign_csv_data(sample_csv)
    assert parsed["total_rows"] == 5
    assert parsed["valid_count"] == 2
    assert parsed["invalid_count"] == 3
    assert len(parsed["valid_recipients"]) == 2

    r1 = parsed["valid_recipients"][0]
    assert r1["email"] == "tunde@example.com"
    assert r1["name"] == "Tunde Bakare"
    assert r1["course"] == "Data Analytics & BI Accelerator"
    assert r1["phone"] == "08012345678"

    r2 = parsed["valid_recipients"][1]
    assert r2["email"] == "ngozi.eze@globaltech.io"
    assert r2["name"] == "Ngozi Eze"


@pytest.mark.asyncio
async def test_parse_campaign_csv_data_headerless_and_delimiters():
    # Semicolon delimited without header
    sample_semicolon = """bolanle@corp.ng;Bolanle Adeleke;Power BI;08033334444
korede@startup.co;Korede Williams;Python & AI;2348055556666
"""
    parsed = parse_campaign_csv_data(sample_semicolon)
    assert parsed["valid_count"] == 2
    assert parsed["valid_recipients"][0]["email"] == "bolanle@corp.ng"
    assert parsed["valid_recipients"][0]["name"] == "Bolanle Adeleke"


@pytest.mark.asyncio
async def test_render_branded_email_html_includes_tara_chat_link():
    html = render_branded_email_html(
        subject="The Japa Tech Blueprint",
        body_markdown="Hi Jane,\n\nReady to earn in dollars?\n\n👉 [Chat with Tara on WhatsApp](https://wa.me/2348063584517?text=Hi)",
        cta_text="Claim Voucher",
        cta_url="https://tektutors.com.ng/registration",
        recipient_name="Jane",
        tara_chat_url="https://wa.me/2348063584517?text=CustomTaraChat"
    )

    # Must contain direct WhatsApp link to chat with Tara
    assert "https://wa.me/2348063584517" in html
    assert "Chat Directly with Tara on WhatsApp" in html
    assert "CustomTaraChat" in html
    assert "💬" in html


@pytest.mark.asyncio
async def test_csv_preview_endpoint():
    await init_db_and_seed()
    sample_csv = "Name,Email,Course,Phone\nZainab Aliyu,zainab.aliyu@example.com,Data Analytics,08022223333\n"
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # JSON preview
        resp = await client.post("/api/emails/csv-preview", json={"csv_text": sample_csv})
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid_count"] == 1
        assert data["valid_recipients"][0]["email"] == "zainab.aliyu@example.com"


@pytest.mark.asyncio
async def test_csv_campaign_broadcast_execution():
    await init_db_and_seed()
    tag = uuid.uuid4().hex[:6]
    test_email = f"lead.{tag}@example.com"

    payload = {
        "recipients": [
            {
                "email": test_email,
                "name": "Ifeanyi Broadcast",
                "course": "Data Analytics & BI Accelerator",
                "phone": f"23480{tag}"
            }
        ],
        "action": "broadcast",
        "subject": "The Japa Blueprint: How {{course}} Unlocks Global Remote Roles",
        "body": "Hi {{name}},\n\nTekTutors 1-on-1 mentorship helps you earn in dollars.\n\n💬 [Chat with Tara]({{tara_chat_url}})",
        "save_to_crm": True
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/emails/csv-campaign", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "broadcast"
        assert data["success_count"] == 1

    # Verify EmailLog was written
    async with AsyncSessionLocal() as db:
        stmt = select(EmailLog).where(EmailLog.recipient_email == test_email)
        log = (await db.execute(stmt)).scalars().first()
        assert log is not None
        assert "Japa Blueprint" in log.subject
        assert "https://wa.me/2348063584517" in log.body_html

        # Verify Lead was saved to CRM
        l_stmt = select(Lead).where(Lead.email == test_email)
        lead = (await db.execute(l_stmt)).scalars().first()
        assert lead is not None
        assert lead.name == "Ifeanyi Broadcast"


@pytest.mark.asyncio
async def test_csv_campaign_drip_enroll_execution():
    await init_db_and_seed()
    tag = uuid.uuid4().hex[:6]
    test_email = f"drip.csv.{tag}@gmail.com"

    payload = {
        "recipients": [
            {
                "email": test_email,
                "name": "Kelechi Drip",
                "course": "AI & Machine Learning Foundations",
                "phone": f"23480{tag}"
            }
        ],
        "action": "drip_enroll",
        "drip_days": 7
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/emails/csv-campaign", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "drip_enroll"
        assert data["success_count"] == 1
        assert data["scheduled_total"] == 7

    # Verify ScheduledEmail records
    async with AsyncSessionLocal() as db:
        stmt = select(ScheduledEmail).where(
            ScheduledEmail.recipient_email == test_email,
            ScheduledEmail.status == "pending"
        ).order_by(ScheduledEmail.sequence_day.asc())
        scheduled = (await db.execute(stmt)).scalars().all()
        assert len(scheduled) == 7
        assert scheduled[0].sequence_day == 1
        assert scheduled[6].sequence_day == 7
        # Ensure Tara WhatsApp link is in all scheduled bodies
        for s in scheduled:
            assert "tara" in s.body_markdown.lower() or "tara_chat_url" in s.body_markdown
