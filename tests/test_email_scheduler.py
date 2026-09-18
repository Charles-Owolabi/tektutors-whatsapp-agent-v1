import pytest
import datetime
from fastapi.testclient import TestClient
from sqlalchemy import select
from unittest.mock import patch

from app.main import app, init_db_and_seed
from app.database import AsyncSessionLocal
from app.models import ScheduledEmail, Lead
from app.email_service import (
    parse_schedule_time,
    schedule_email_async,
    enroll_lead_in_daily_drip_sequence,
    process_due_scheduled_emails,
    cancel_scheduled_email,
    DAILY_DRIP_SEQUENCE
)
from app.tools import schedule_followup_email


@pytest.fixture(autouse=True)
def mock_smtp_sender():
    """Mock external SMTP delivery in unit tests so test suite runs fast and isolated."""
    with patch("app.email_service._send_smtp_email_sync", return_value=True):
        yield


def test_parse_schedule_time_variations():
    now = datetime.datetime.now()

    # 1. "in 2 hours"
    t_2h = parse_schedule_time("in 2 hours")
    diff_h = (t_2h - now).total_seconds() / 3600.0
    assert 1.9 <= diff_h <= 2.1

    # 2. "in 3 days"
    t_3d = parse_schedule_time("in 3 days")
    diff_d = (t_3d - now).total_seconds() / 86400.0
    assert 2.9 <= diff_d <= 3.1

    # 3. "tomorrow morning"
    t_tm = parse_schedule_time("tomorrow morning")
    assert t_tm.hour == 9
    assert t_tm.day == (now + datetime.timedelta(days=1)).day

    # 4. ISO string
    target_iso = "2026-11-20T14:30:00"
    t_iso = parse_schedule_time(target_iso)
    assert t_iso.year == 2026
    assert t_iso.month == 11
    assert t_iso.day == 20
    assert t_iso.hour == 14
    assert t_iso.minute == 30


@pytest.mark.asyncio
async def test_schedule_email_creation_and_cancellation():
    await init_db_and_seed()
    test_email = f"scheduler.{uuid.uuid4().hex[:6]}@gmail.com"
    delivery_time = datetime.datetime.now() + datetime.timedelta(hours=4)

    # Schedule email
    res = await schedule_email_async(
        to_email=test_email,
        subject="Scheduled Follow-up Test",
        body_markdown="Hello {{name}}, this is a scheduled message.",
        scheduled_for=delivery_time,
        to_name="Ada Lovelace",
        campaign_type="test_scheduled"
    )

    assert res["status"] == "pending"
    assert res["recipient_email"] == test_email
    sched_id = res["scheduled_id"]

    # Verify in DB
    async with AsyncSessionLocal() as db:
        rec = (await db.execute(select(ScheduledEmail).where(ScheduledEmail.id == sched_id))).scalar_one_or_none()
        assert rec is not None
        assert rec.status == "pending"
        assert rec.recipient_name == "Ada Lovelace"

    # Cancel email
    cancelled = await cancel_scheduled_email(sched_id)
    assert cancelled is True

    # Verify status changed
    async with AsyncSessionLocal() as db:
        rec = (await db.execute(select(ScheduledEmail).where(ScheduledEmail.id == sched_id))).scalar_one_or_none()
        assert rec.status == "cancelled"


import uuid

@pytest.mark.asyncio
async def test_enroll_lead_in_daily_drip_sequence():
    await init_db_and_seed()
    unique_tag = uuid.uuid4().hex[:6]
    drip_email = f"drip.learner.{unique_tag}@gmail.com"

    # Create lead first
    async with AsyncSessionLocal() as db:
        lead = Lead(
            phone=f"23480{unique_tag[:8]}",
            email=drip_email,
            name="Chinedu Drip",
            course_interest="Machine Learning with Python",
            status="qualified"
        )
        db.add(lead)
        await db.commit()
        await db.refresh(lead)
        lead_id = lead.id

    # Enroll in 5-day daily follow-up drip
    res = await enroll_lead_in_daily_drip_sequence(
        lead_id=lead_id,
        email=drip_email,
        name="Chinedu Drip",
        course_name="Machine Learning with Python"
    )

    assert res["status"] == "enrolled"
    assert res["scheduled_emails_count"] == 5

    # Verify 5 scheduled records created for Days 1 through 5
    async with AsyncSessionLocal() as db:
        stmt = select(ScheduledEmail).where(
            ScheduledEmail.recipient_email == drip_email,
            ScheduledEmail.campaign_type == "daily_drip_nurture"
        ).order_by(ScheduledEmail.sequence_day.asc())
        records = (await db.execute(stmt)).scalars().all()

        assert len(records) == 5
        days = [r.sequence_day for r in records]
        assert days == [1, 2, 3, 4, 5]

        # Verify themes
        # Day 1: 1-on-1 Mentorship (What makes us different)
        assert "1-on-1" in records[0].subject or "Screen Sharing" in records[0].subject
        # Day 2: Irresistible offer / tuition flexibility
        assert "Tuition" in records[1].subject or "₦90,000" in records[1].subject or "Bonus" in records[1].subject
        # Day 3: Relevance & ROI / math
        assert "Math" in records[2].subject or "Pays for Itself" in records[2].subject
        # Day 4: Competitive advantages / 3 capstone projects
        assert "Projects" in records[3].subject or "Portfolio" in records[3].subject
        # Day 5: Urgency & mentor reservation
        assert "Reserved" in records[4].subject or "Expiring" in records[4].subject


@pytest.mark.asyncio
async def test_process_due_scheduled_emails():
    await init_db_and_seed()
    due_email = "due.test@gmail.com"

    # Insert a scheduled email with a scheduled_for in the past (-1 minute)
    past_due_time = datetime.datetime.now() - datetime.timedelta(minutes=1)
    sched_res = await schedule_email_async(
        to_email=due_email,
        subject="Due Scheduled Email",
        body_markdown="Hi {{name}}, your requested material is ready.",
        scheduled_for=past_due_time,
        to_name="Due Student"
    )

    sched_id = sched_res["scheduled_id"]

    # Process due emails
    processed = await process_due_scheduled_emails()
    assert len(processed) >= 1
    found = next((p for p in processed if p["id"] == sched_id), None)
    assert found is not None
    assert found["status"] in ("sent", "delivered")

    # Verify DB record updated
    async with AsyncSessionLocal() as db:
        rec = (await db.execute(select(ScheduledEmail).where(ScheduledEmail.id == sched_id))).scalar_one_or_none()
        assert rec.status in ("sent", "delivered")
        assert rec.sent_at is not None


@pytest.mark.asyncio
async def test_schedule_followup_email_tool():
    await init_db_and_seed()
    tool_phone = "2348077665544"
    tool_email = "agent.scheduled@gmail.com"

    tool_res = await schedule_followup_email.ainvoke({
        "phone": tool_phone,
        "delay_or_datetime": "tomorrow morning",
        "campaign_stage": "syllabus",
        "email": tool_email,
        "course_name": "Power BI & Business Intelligence"
    })

    assert "Successfully scheduled" in tool_res
    assert tool_email in tool_res

    # Check DB
    async with AsyncSessionLocal() as db:
        stmt = select(ScheduledEmail).where(ScheduledEmail.recipient_email == tool_email)
        rec = (await db.execute(stmt)).scalars().first()
        assert rec is not None
        assert rec.status == "pending"
        assert "Power BI" in rec.course_name


def test_scheduled_email_api_endpoints():
    with TestClient(app) as client:
        api_email = f"api.scheduled.{uuid.uuid4().hex[:6]}@gmail.com"
        # 1. Schedule via API
        post_res = client.post("/api/emails/schedule", json={
            "recipient_email": api_email,
            "recipient_name": "API Student",
            "subject": "API Schedule Test",
            "body": "Hello API world",
            "scheduled_for": "in 5 hours",
            "course_name": "Data Analytics & BI Accelerator"
        })
        assert post_res.status_code == 200
        data = post_res.json()
        assert data["success"] is True
        sched_id = data["result"]["scheduled_id"]

        # 2. Get scheduled queue
        get_res = client.get("/api/emails/scheduled?status=pending")
        assert get_res.status_code == 200
        queue_data = get_res.json()
        assert queue_data["total"] >= 1
        found = next((item for item in queue_data["scheduled_emails"] if item["id"] == sched_id), None)
        assert found is not None
        assert found["recipient_email"] == api_email

        # 3. Cancel via API
        cancel_res = client.post(f"/api/emails/scheduled/{sched_id}/cancel")
        assert cancel_res.status_code == 200
        assert cancel_res.json()["success"] is True

        # 4. Trigger process-now via API
        flush_res = client.post("/api/emails/scheduled/process-now")
        assert flush_res.status_code == 200
        assert flush_res.json()["success"] is True
