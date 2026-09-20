import pytest
import asyncio
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app, init_db_and_seed
from app.database import AsyncSessionLocal
from app.models import Lead, EmailLog
from unittest.mock import patch
from app.tools import (
    qualify_and_capture_lead,
    schedule_advisor_call,
    generate_enrollment_checkout,
    trigger_conversion_email_campaign
)

@pytest.fixture(autouse=True)
def mock_smtp_sender():
    """Mock external SMTP and API email delivery in unit tests so test suite runs fast and isolated."""
    with patch("app.email_service._send_smtp_email_sync", return_value=True), \
         patch("app.email_service._send_resend_email_async", return_value=True), \
         patch("app.email_service._send_brevo_email_async", return_value=True):
        yield

@pytest.mark.asyncio
async def test_email_templates_api():
    """Verify templates endpoint returns categorized conversion, follow-up, marketing, and promotional templates."""
    await init_db_and_seed()
    with TestClient(app) as client:
        res = client.get("/api/emails/templates")
        assert res.status_code == 200
        templates = res.json()
        assert len(templates) >= 18

        categories = {t["category"] for t in templates}
        assert "conversion" in categories
        assert "follow_up" in categories
        assert "marketing" in categories
        assert "promotional" in categories

        template_ids = {t["id"] for t in templates}
        assert "cart_abandonment_recovery" in template_ids
        assert "career_roi_payback_breakdown" in template_ids
        assert "zero_coding_transition_blueprint" in template_ids
        assert "banker_accountant_switch" in template_ids

        # Check essential fields in every template
        for tpl in templates:
            assert "id" in tpl
            assert "title" in tpl
            assert "subject" in tpl
            assert "body" in tpl
            assert "cta_text" in tpl
            assert "cta_url" in tpl


@pytest.mark.asyncio
async def test_email_html_preview_api():
    """Verify branded HTML generation endpoint."""
    with TestClient(app) as client:
        payload = {
            "subject": "Exclusive 20% Scholarship Voucher",
            "body": "Hi Alex,\n\nHere is your **₦20,000 tuition discount** for Data Analytics.",
            "cta_text": "Claim Discount",
            "cta_url": "https://tektutors.com.ng/registration",
            "recipient_name": "Alex Morgan"
        }
        res = client.post("/api/emails/preview", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert "html" in data
        html = data["html"]
        assert "TekTutors" in html
        assert "Claim Discount" in html
        assert "https://tektutors.com.ng/registration" in html
        assert "₦20,000 tuition discount" in html


@pytest.mark.asyncio
async def test_send_single_email_simulation_and_audit():
    """Verify sending a single personalized email logs an audit trail in the database."""
    await init_db_and_seed()

    # Create a test lead with email
    async with AsyncSessionLocal() as db:
        lead = Lead(
            phone="2348099887766",
            name="Oluwaseun Ade",
            email="oluwaseun.test@example.com",
            course_interest="Power BI & Business Intelligence",
            status="hot",
            lead_score=85
        )
        db.add(lead)
        await db.commit()
        await db.refresh(lead)
        lead_id = lead.id

    with TestClient(app) as client:
        payload = {
            "recipient_email": "oluwaseun.test@example.com",
            "recipient_name": "Oluwaseun Ade",
            "subject": "Follow up for {{name}} regarding {{course}}",
            "body": "Hi {{name}},\n\nHere is the private onboarding link for **{{course}}**: {{registration_url}}",
            "campaign_type": "follow_up",
            "lead_id": lead_id,
            "cta_text": "Confirm Seat",
            "cta_url": "https://tektutors.com.ng/registration"
        }
        res = client.post("/api/emails/send-single", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        result = data["result"]
        assert result["status"] in ("sent", "delivered")
        assert "Oluwaseun Ade" in result["subject"]
        assert "Power BI" in result["subject"]

        # Verify audit log in GET /api/emails/logs
        log_res = client.get("/api/emails/logs?limit=10")
        assert log_res.status_code == 200
        logs = log_res.json()
        matching = [l for l in logs if l["recipient_email"] == "oluwaseun.test@example.com"]
        assert len(matching) >= 1
        assert matching[0]["campaign_type"] == "follow_up"


@pytest.mark.asyncio
async def test_broadcast_email_segmentation():
    """Verify audience segmentation (all, hot, qualified) in broadcast email dispatch."""
    await init_db_and_seed()

    async with AsyncSessionLocal() as db:
        db.add_all([
            Lead(
                phone="2348011112222",
                name="Hot Lead One",
                email="hot1@example.com",
                status="hot",
                lead_score=90
            ),
            Lead(
                phone="2348033334444",
                name="Qualified Lead Two",
                email="qualified2@example.com",
                status="qualified",
                lead_score=65
            ),
            Lead(
                phone="2348055556666",
                name="New Lead Three",
                email="new3@example.com",
                status="new",
                lead_score=40
            )
        ])
        await db.commit()

    with TestClient(app) as client:
        # Broadcast to hot leads only
        payload = {
            "target_audience": "hot",
            "campaign_type": "promotional",
            "subject": "VIP Scholarship for {{name}}",
            "body": "Special priority invitation for **{{course}}**.",
            "cta_text": "Claim Scholarship",
            "cta_url": "https://tektutors.com.ng/registration"
        }
        res = client.post("/api/emails/send-broadcast", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        # At least Hot Lead One should be included
        recipients = [r["email"] for r in data["results"]]
        assert "hot1@example.com" in recipients
        assert "new3@example.com" not in recipients


@pytest.mark.asyncio
async def test_email_stats_aggregation():
    """Verify /api/emails/stats aggregates telemetry metrics correctly."""
    await init_db_and_seed()

    with TestClient(app) as client:
        res = client.get("/api/emails/stats")
        assert res.status_code == 200
        stats = res.json()
        assert "total_dispatched" in stats
        assert "follow_up_count" in stats
        assert "marketing_count" in stats
        assert "promotional_count" in stats
        assert "delivery_rate" in stats
        assert stats["total_dispatched"] >= 1
        assert 0.0 <= stats["delivery_rate"] <= 100.0


@pytest.mark.asyncio
async def test_engagement_trigger_syllabus_on_lead_capture():
    """Verify qualify_and_capture_lead automatically triggers syllabus email when email is provided."""
    await init_db_and_seed()
    test_phone = "2348077889900"
    test_email = "syllabus.lead@example.com"

    res = await qualify_and_capture_lead.ainvoke({
        "phone": test_phone,
        "name": "Kemi Ade",
        "email": test_email,
        "course_interest": "Power BI & Business Intelligence"
    })
    assert "Lead captured successfully" in res

    # Allow background task to complete
    await asyncio.sleep(0.1)

    async with AsyncSessionLocal() as db:
        stmt = select(EmailLog).where(EmailLog.recipient_email == test_email).order_by(EmailLog.id.desc())
        db_res = await db.execute(stmt)
        log = db_res.scalars().first()
        assert log is not None
        assert "Power BI" in log.subject or "Syllabus" in log.subject or "Roadmap" in log.subject
        assert log.status in ("sent", "delivered")


@pytest.mark.asyncio
async def test_engagement_trigger_advisor_call():
    """Verify schedule_advisor_call automatically triggers consultation confirmation email."""
    await init_db_and_seed()
    test_phone = "2348033445566"
    test_email = "consultation.lead@example.com"

    # Ensure lead exists with email
    await qualify_and_capture_lead.ainvoke({
        "phone": test_phone,
        "name": "Chinedu Eze",
        "email": test_email,
        "course_interest": "Data Analytics & BI Accelerator"
    })

    call_res = await schedule_advisor_call.ainvoke({
        "phone": test_phone,
        "name": "Chinedu Eze",
        "preferred_time": "Friday 4:00 PM WAT",
        "course": "Data Analytics & BI Accelerator"
    })
    assert "Advisor Call Scheduled" in call_res

    # Allow background task to complete
    await asyncio.sleep(0.1)

    async with AsyncSessionLocal() as db:
        stmt = select(EmailLog).where(
            EmailLog.recipient_email == test_email,
            EmailLog.subject.ilike("%Appointment Confirmed%")
        ).order_by(EmailLog.id.desc())
        db_res = await db.execute(stmt)
        log = db_res.scalars().first()
        assert log is not None
        assert "Appointment Confirmed" in log.subject
        assert "Chinedu Eze" in log.recipient_name


@pytest.mark.asyncio
async def test_engagement_trigger_checkout_invoice():
    """Verify generate_enrollment_checkout automatically triggers invoice & payment link email."""
    await init_db_and_seed()
    test_phone = "2348055667788"
    test_email = "checkout.lead@example.com"

    await qualify_and_capture_lead.ainvoke({
        "phone": test_phone,
        "name": "Zainab Bello",
        "email": test_email,
        "course_interest": "SQL for Analytics & Data Engineering"
    })

    checkout_res = await generate_enrollment_checkout.ainvoke({
        "phone": test_phone,
        "student_name": "Zainab Bello",
        "course_title": "SQL for Analytics & Data Engineering",
        "payment_plan": "monthly_installment"
    })
    assert "TEK-" in checkout_res

    # Allow background task to complete
    await asyncio.sleep(0.1)

    async with AsyncSessionLocal() as db:
        stmt = select(EmailLog).where(
            EmailLog.recipient_email == test_email,
            EmailLog.subject.ilike("%Invoice%")
        ).order_by(EmailLog.id.desc())
        db_res = await db.execute(stmt)
        log = db_res.scalars().first()
        assert log is not None
        assert "Invoice" in log.subject


@pytest.mark.asyncio
async def test_trigger_conversion_email_campaign_tool():
    """Verify AI Agent tool trigger_conversion_email_campaign sends targeted campaigns."""
    await init_db_and_seed()
    test_phone = "2348099881122"
    test_email = "scholarship.lead@example.com"

    # First test when prospect has no email
    no_email_phone = "2348099999001"
    async with AsyncSessionLocal() as db:
        from sqlalchemy import delete
        await db.execute(delete(Lead).where(Lead.phone == no_email_phone))
        await db.commit()

    no_email_res = await trigger_conversion_email_campaign.ainvoke({
        "phone": no_email_phone,
        "campaign_stage": "scholarship"
    })
    assert "does not have an email address" in no_email_res

    # Capture lead with email
    await qualify_and_capture_lead.ainvoke({
        "phone": test_phone,
        "name": "Tolani Shittu",
        "email": test_email,
        "course_interest": "Data Analytics & BI Accelerator"
    })

    # Dispatch scholarship campaign
    tool_res = await trigger_conversion_email_campaign.ainvoke({
        "phone": test_phone,
        "campaign_stage": "scholarship",
        "course_name": "Data Analytics & BI Accelerator"
    })
    assert "Dispatched 'scholarship' conversion email" in tool_res

    async with AsyncSessionLocal() as db:
        stmt = select(EmailLog).where(
            EmailLog.recipient_email == test_email,
            EmailLog.subject.ilike("%Scholarship%")
        ).order_by(EmailLog.id.desc())
        db_res = await db.execute(stmt)
        log = db_res.scalars().first()
        assert log is not None
        assert "TEK-EARLY20" in log.body_html


@pytest.mark.asyncio
async def test_email_log_detail_and_test_send_api():
    """Verify GET /api/emails/logs/{id} and POST /api/emails/send-test."""
    await init_db_and_seed()

    with TestClient(app) as client:
        # 1. Test POST /api/emails/send-test
        test_payload = {
            "recipient_email": "admin.tester@tektutors.com.ng",
            "recipient_name": "QA Tester",
            "subject": "Pre-blast Checklist",
            "body": "Hello QA team, this is a test dispatch.",
            "course_name": "Data Analytics"
        }
        test_res = client.post("/api/emails/send-test", json=test_payload)
        assert test_res.status_code == 200
        test_data = test_res.json()
        assert test_data["success"] is True
        log_id = test_data["result"]["log_id"]
        assert log_id is not None

        # 2. Test GET /api/emails/logs/{log_id}
        detail_res = client.get(f"/api/emails/logs/{log_id}")
        assert detail_res.status_code == 200
        detail_data = detail_res.json()
        assert detail_data["id"] == log_id
        assert detail_data["recipient_email"] == "admin.tester@tektutors.com.ng"
        assert "<!DOCTYPE html>" in detail_data["body_html"]
        assert "Pre-blast Checklist" in detail_data["subject"]


@pytest.mark.asyncio
async def test_crm_trigger_engagement_api():
    """Verify POST /api/emails/trigger-engagement dispatches tailored conversion email."""
    await init_db_and_seed()

    # Create lead
    async with AsyncSessionLocal() as db:
        lead = Lead(
            phone="2348012349999",
            name="Femi Otedola",
            email="femi.invest@example.com",
            course_interest="Applied Python for Analytics & AI",
            status="hot",
            lead_score=95
        )
        db.add(lead)
        await db.commit()
        await db.refresh(lead)
        lead_id = lead.id

    with TestClient(app) as client:
        payload = {
            "lead_id": lead_id,
            "trigger_event": "invoice",
            "custom_notes": "10% upfront rebate pre-applied."
        }
        res = client.post("/api/emails/trigger-engagement", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert "femi.invest@example.com" in data["message"]


@pytest.mark.asyncio
async def test_broadcast_email_deduplication():
    """Verify send-broadcast deduplicates leads with identical email addresses."""
    await init_db_and_seed()

    shared_email = "duplicate.learner@example.com"
    async with AsyncSessionLocal() as db:
        db.add_all([
            Lead(
                phone="2348088880001",
                name="Duplicate One",
                email=shared_email,
                status="hot",
                lead_score=90
            ),
            Lead(
                phone="2348088880002",
                name="Duplicate Two",
                email=shared_email,
                status="hot",
                lead_score=92
            )
        ])
        await db.commit()

    with TestClient(app) as client:
        payload = {
            "target_audience": "hot",
            "campaign_type": "promotional",
            "subject": "Exclusive Discount",
            "body": "Special discount for **{{name}}**.",
            "cta_text": "Enroll Now",
            "cta_url": "https://tektutors.com.ng/registration"
        }
        res = client.post("/api/emails/send-broadcast", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        
        # Check that shared_email appears only ONCE in the dispatch results
        sent_emails = [r["email"] for r in data["results"]]
        assert sent_emails.count(shared_email) == 1

