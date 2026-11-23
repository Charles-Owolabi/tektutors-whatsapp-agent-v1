import sys
import os
from pathlib import Path

# Add project root directory to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import time
import json
import logging
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import select

from app.config import settings
from app.database import engine, Base, AsyncSessionLocal
from app.models import Course, FAQ, SystemConfig, EmailLog, Lead, ScheduledEmail, WhatsAppLog, ScheduledWhatsAppMessage, EmailSender
from app.data import SEED_COURSES, SEED_FAQS
from app.webhook import router as webhook_router
from app.dashboard_routes import router as dashboard_router

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("tektutors")

async def init_db_and_seed():
    """Create database tables and seed TekTutors course catalog if empty."""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            
            # Safe column check depending on database dialect
            from sqlalchemy import text
            dialect_name = conn.dialect.name
            
            if dialect_name == "sqlite":
                sys_cols_res = await conn.execute(text("PRAGMA table_info(system_config)"))
                existing_sys_cols = {row[1] for row in sys_cols_res.fetchall()}
                for col, col_type in [
                    ("persona_tone", "VARCHAR(50) DEFAULT 'consultative'"),
                    ("business_hours", "VARCHAR(100) DEFAULT '9:00 AM - 6:00 PM (Mon-Sat)'"),
                    ("away_message", "TEXT DEFAULT 'Thanks for contacting TekTutors!'"),
                    ("currency", "VARCHAR(10) DEFAULT 'NGN'"),
                    ("currency_symbol", "VARCHAR(5) DEFAULT '₦'"),
                    ("outbound_webhook_url", "VARCHAR(255)"),
                    ("outbound_webhook_secret", "VARCHAR(100)"),
                    ("email_header_title", "VARCHAR(150) DEFAULT 'TekTutors'"),
                    ("email_header_subtitle", "VARCHAR(255) DEFAULT 'Practical Data Analytics & AI Mentorship Academy'"),
                    ("email_header_badge", "VARCHAR(100) DEFAULT 'Live 1-on-1 Mentorship'"),
                    ("email_primary_color", "VARCHAR(30) DEFAULT '#eb6711'"),
                    ("email_footer_contact", "TEXT DEFAULT 'Have questions or need help? Reply to this email or message Tara on WhatsApp: +234 911 212 0531'"),
                    ("email_footer_copyright", "VARCHAR(255) DEFAULT 'TekTutors Academy. All rights reserved.'"),
                    ("email_footer_extra", "TEXT DEFAULT ''"),
                    ("email_custom_header_html", "TEXT"),
                    ("email_custom_footer_html", "TEXT")
                ]:
                    if col not in existing_sys_cols:
                        await conn.execute(text(f"ALTER TABLE system_config ADD COLUMN {col} {col_type}"))

                lead_cols_res = await conn.execute(text("PRAGMA table_info(leads)"))
                existing_lead_cols = {row[1] for row in lead_cols_res.fetchall()}
                if "lead_score" not in existing_lead_cols:
                    await conn.execute(text("ALTER TABLE leads ADD COLUMN lead_score INTEGER DEFAULT 50"))

                email_log_cols_res = await conn.execute(text("PRAGMA table_info(email_logs)"))
                existing_email_log_cols = {row[1] for row in email_log_cols_res.fetchall()}
                for col, col_type in [
                    ("sender_id", "INTEGER"),
                    ("sender_name", "VARCHAR(100)"),
                    ("sender_email", "VARCHAR(120)")
                ]:
                    if col not in existing_email_log_cols:
                        await conn.execute(text(f"ALTER TABLE email_logs ADD COLUMN {col} {col_type}"))

                sched_email_cols_res = await conn.execute(text("PRAGMA table_info(scheduled_emails)"))
                existing_sched_cols = {row[1] for row in sched_email_cols_res.fetchall()}
                for col, col_type in [
                    ("sender_id", "INTEGER"),
                    ("sender_name", "VARCHAR(100)"),
                    ("sender_email", "VARCHAR(120)")
                ]:
                    if col not in existing_sched_cols:
                        await conn.execute(text(f"ALTER TABLE scheduled_emails ADD COLUMN {col} {col_type}"))

            elif dialect_name == "postgresql":
                # PostgreSQL natively supports ADD COLUMN IF NOT EXISTS without aborting transactions
                for col, col_type in [
                    ("persona_tone", "VARCHAR(50) DEFAULT 'consultative'"),
                    ("business_hours", "VARCHAR(100) DEFAULT '9:00 AM - 6:00 PM (Mon-Sat)'"),
                    ("away_message", "TEXT DEFAULT 'Thanks for contacting TekTutors!'"),
                    ("currency", "VARCHAR(10) DEFAULT 'NGN'"),
                    ("currency_symbol", "VARCHAR(5) DEFAULT '₦'"),
                    ("outbound_webhook_url", "VARCHAR(255)"),
                    ("outbound_webhook_secret", "VARCHAR(100)"),
                    ("email_header_title", "VARCHAR(150) DEFAULT 'TekTutors'"),
                    ("email_header_subtitle", "VARCHAR(255) DEFAULT 'Practical Data Analytics & AI Mentorship Academy'"),
                    ("email_header_badge", "VARCHAR(100) DEFAULT 'Live 1-on-1 Mentorship'"),
                    ("email_primary_color", "VARCHAR(30) DEFAULT '#eb6711'"),
                    ("email_footer_contact", "TEXT DEFAULT 'Have questions or need help? Reply to this email or message Tara on WhatsApp: +234 911 212 0531'"),
                    ("email_footer_copyright", "VARCHAR(255) DEFAULT 'TekTutors Academy. All rights reserved.'"),
                    ("email_footer_extra", "TEXT DEFAULT ''"),
                    ("email_custom_header_html", "TEXT"),
                    ("email_custom_footer_html", "TEXT")
                ]:
                    await conn.execute(text(f"ALTER TABLE system_config ADD COLUMN IF NOT EXISTS {col} {col_type}"))

                await conn.execute(text("ALTER TABLE leads ADD COLUMN IF NOT EXISTS lead_score INTEGER DEFAULT 50"))
                await conn.execute(text("ALTER TABLE email_logs ADD COLUMN IF NOT EXISTS sender_id INTEGER"))
                await conn.execute(text("ALTER TABLE email_logs ADD COLUMN IF NOT EXISTS sender_name VARCHAR(100)"))
                await conn.execute(text("ALTER TABLE email_logs ADD COLUMN IF NOT EXISTS sender_email VARCHAR(120)"))
                await conn.execute(text("ALTER TABLE scheduled_emails ADD COLUMN IF NOT EXISTS sender_id INTEGER"))
                await conn.execute(text("ALTER TABLE scheduled_emails ADD COLUMN IF NOT EXISTS sender_name VARCHAR(100)"))
                await conn.execute(text("ALTER TABLE scheduled_emails ADD COLUMN IF NOT EXISTS sender_email VARCHAR(120)"))

    except Exception as e:
        logger.error(f"Error creating or updating database schema: {e}", exc_info=True)

    try:
        async with AsyncSessionLocal() as db:
            # Seed Courses
            course_res = await db.execute(select(Course))
            existing_courses = course_res.scalars().all()
            if not existing_courses:
                logger.info("Seeding TekTutors courses dataset...")
                for c_data in SEED_COURSES:
                    db.add(Course(**c_data))
                await db.commit()
            else:
                # Sync course durations and descriptions from SEED_COURSES
                for c_data in SEED_COURSES:
                    for ec in existing_courses:
                        if ec.slug == c_data["slug"]:
                            if ec.duration_weeks != c_data["duration_weeks"] or ec.description != c_data["description"]:
                                ec.duration_weeks = c_data["duration_weeks"]
                                ec.description = c_data["description"]
                await db.commit()

            # Seed Default Email Senders if none exist
            sender_res = await db.execute(select(EmailSender))
            existing_senders = sender_res.scalars().all()
            existing_names = {s.name.lower() for s in existing_senders}
            
            default_senders_to_seed = [
                {
                    "name": "Tara from TekTutors",
                    "email": settings.SMTP_FROM_EMAIL or "tektutorsng@gmail.com",
                    "reply_to": settings.SMTP_FROM_EMAIL or "tektutorsng@gmail.com",
                    "role_title": "Lead Admissions Advisor",
                    "phone_or_whatsapp": "+234 911 212 0531",
                    "signature_markdown": "Best regards,\n**Tara Owolabi**\nLead Admissions Advisor | TekTutors Academy\nWhatsApp: +234 911 212 0531\nWebsite: https://tektutors.com.ng",
                    "provider_type": "system_default",
                    "is_default": len(existing_senders) == 0,
                    "is_active": True,
                    "daily_send_limit": 500
                },
                {
                    "name": "Charles from TekTutors",
                    "email": "charles@tektutors.com.ng",
                    "reply_to": settings.SMTP_FROM_EMAIL or "tektutorsng@gmail.com",
                    "role_title": "Founder & Senior Data Mentor",
                    "phone_or_whatsapp": "+234 911 212 0531",
                    "signature_markdown": "To your accelerated career,\n**Charles Owolabi**\nFounder & Lead Mentor | TekTutors Academy\nDirect Mentorship & Portfolio Reviews\nWebsite: https://tektutors.com.ng",
                    "provider_type": "system_default",
                    "is_default": False,
                    "is_active": True,
                    "daily_send_limit": 500
                },
                {
                    "name": "Ben from TekTutors",
                    "email": "ben@tektutors.com.ng",
                    "reply_to": settings.SMTP_FROM_EMAIL or "tektutorsng@gmail.com",
                    "role_title": "Academic Success & Career Advisor",
                    "phone_or_whatsapp": "+234 911 212 0531",
                    "signature_markdown": "Warm regards,\n**Ben Okon**\nAcademic Success & Career Advisor | TekTutors Academy\nWhatsApp: +234 911 212 0531\nWebsite: https://tektutors.com.ng",
                    "provider_type": "system_default",
                    "is_default": False,
                    "is_active": True,
                    "daily_send_limit": 500
                },
                {
                    "name": "Agnes from TekTutors",
                    "email": "agnes@tektutors.com.ng",
                    "reply_to": settings.SMTP_FROM_EMAIL or "tektutorsng@gmail.com",
                    "role_title": "Senior Student Admissions Advisor",
                    "phone_or_whatsapp": "+234 911 212 0531",
                    "signature_markdown": "Sincerely,\n**Agnes Adebayo**\nStudent Admissions Advisor | TekTutors Academy\nWhatsApp: +234 911 212 0531\nWebsite: https://tektutors.com.ng",
                    "provider_type": "system_default",
                    "is_default": False,
                    "is_active": True,
                    "daily_send_limit": 500
                },
                {
                    "name": "TekTutors Admissions",
                    "email": "admissions@tektutors.com.ng",
                    "reply_to": settings.SMTP_FROM_EMAIL or "tektutorsng@gmail.com",
                    "role_title": "Admissions & Enrollments Desk",
                    "phone_or_whatsapp": "+234 911 212 0531",
                    "signature_markdown": "Warm regards,\n**TekTutors Admissions Office**\nPractical 1-on-1 Mentorship Academy\nLagos, Nigeria | Global Remote Mentorship\nWhatsApp: +234 911 212 0531",
                    "provider_type": "system_default",
                    "is_default": False,
                    "is_active": True,
                    "daily_send_limit": 1000
                },
                {
                    "name": "Academic Mentorship Team",
                    "email": "mentors@tektutors.com.ng",
                    "reply_to": settings.SMTP_FROM_EMAIL or "tektutorsng@gmail.com",
                    "role_title": "Senior Industry Practitioners",
                    "phone_or_whatsapp": "+234 911 212 0531",
                    "signature_markdown": "Regards,\n**TekTutors Academic Faculty**\nPractical Data Analytics & AI Mentorship\nDirect 1-on-1 Code & Portfolio Reviews",
                    "provider_type": "system_default",
                    "is_default": False,
                    "is_active": True,
                    "daily_send_limit": 500
                }
            ]

            added_any = False
            for s_info in default_senders_to_seed:
                # If this sender not yet present in existing senders
                name_key = s_info["name"].lower()
                if not any(name_key in en or en in name_key for en in existing_names):
                    db.add(EmailSender(**s_info))
                    added_any = True

            if added_any:
                await db.commit()
                logger.info("Seeded TekTutors multi-sender identities: Charles, Ben, Agnes, Tara, Admissions.")

            # Seed FAQs
            faq_res = await db.execute(select(FAQ))
            existing_faqs = faq_res.scalars().all()
            if not existing_faqs:
                logger.info("Seeding TekTutors FAQs dataset...")
                for f_data in SEED_FAQS:
                    db.add(FAQ(**f_data))
                await db.commit()
            else:
                # Ensure all SEED_FAQS are synced to existing database
                existing_questions_res = await db.execute(select(FAQ.question))
                existing_questions = set(existing_questions_res.scalars().all())
                added_faqs = False
                for f_data in SEED_FAQS:
                    if f_data["question"] not in existing_questions:
                        db.add(FAQ(**f_data))
                        added_faqs = True
                if added_faqs:
                    await db.commit()

            # Ensure SystemConfig has updated prompt with registration link, Track 6, ₦90,000 discount rule, and 6-8 weeks single-tool duration
            try:
                from app.agent import SYSTEM_PROMPT_TEXT
                cfg_res = await db.execute(select(SystemConfig).limit(1))
                cfg = cfg_res.scalar_one_or_none()
                if cfg and ("WHATSAPP PRESENTATION & BOLD FORMATTING" not in (cfg.system_prompt or "") or "https://tektutors.com.ng/registration" not in (cfg.system_prompt or "") or "6)" not in (cfg.system_prompt or "") or "COURSE LISTING" not in (cfg.system_prompt or "") or "₦90,000" not in (cfg.system_prompt or "") or "6-8 wks" not in (cfg.system_prompt or "") or "NEVER USE MARKDOWN TABLES" not in (cfg.system_prompt or "") or "NEVER EVER use markdown link syntax" not in (cfg.system_prompt or "")):
                    cfg.system_prompt = SYSTEM_PROMPT_TEXT.strip()
                    await db.commit()
            except Exception as e:
                logger.warning(f"Note: SystemConfig sync skipped: {e}")

            # Note: Email logs start pristine in production and record actual email activity.
            pass

    except Exception as e:
        logger.error(f"Error seeding database: {e}", exc_info=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting TekTutors WhatsApp AI Sales Agent Server...")
    try:
        await init_db_and_seed()
    except Exception as e:
        logger.error(f"Error during startup init_db_and_seed: {e}", exc_info=True)

    from app.email_service import start_scheduled_email_worker, stop_scheduled_email_worker, sync_email_branding_from_db
    from app.whatsapp_sequence import start_scheduled_whatsapp_worker, stop_scheduled_whatsapp_worker
    try:
        await sync_email_branding_from_db()
    except Exception as e:
        logger.warning(f"Note: Email branding cache sync skipped: {e}")
    start_scheduled_email_worker()
    start_scheduled_whatsapp_worker()

    yield

    stop_scheduled_whatsapp_worker()
    stop_scheduled_email_worker()
    logger.info("Shutting down TekTutors Server...")

START_TIME = time.time()


def _safe_int_env(name: str, default: int) -> int:
    """Accept only numeric env values; reject literal shell placeholders like '$PORT'."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return int(default)
    value = raw.strip().strip('"').strip("'")
    if value.startswith("$"):
        return int(default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

app = FastAPI(
    title=settings.APP_NAME,
    description="Production-Ready WhatsApp AI Customer Service & Sales Agent for TekTutors AI Academy",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Static Assets & Routers
app.mount("/static", StaticFiles(directory=str(ROOT_DIR / "static")), name="static")
app.include_router(webhook_router)
app.include_router(dashboard_router)

@app.get("/")
async def root():
    """Redirect root to dashboard."""
    return RedirectResponse(url="/dashboard")

@app.get("/health")
async def health_check():
    """Lightweight liveness probe for orchestrators and load balancers."""
    uptime_seconds = int(time.time() - START_TIME)
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "env": settings.APP_ENV,
        "uptime_seconds": uptime_seconds,
        "version": "1.0.0"
    }

@app.get("/ready")
async def readiness_check():
    """Readiness probe verifying DB connectivity and Groq configuration."""
    db_status = "ok"
    try:
        from sqlalchemy import text
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"error: {str(e)}"

    groq_status = "configured" if settings.GROQ_API_KEY else "not_configured"
    is_ready = (db_status == "ok") and (groq_status == "configured")

    from app.whatsapp import whatsapp_client
    from app.webhook import webhook_diagnostics

    return Response(
        content=json.dumps({
            "status": "ready" if is_ready else "degraded",
            "database": db_status,
            "groq_engine": groq_status,
            "whatsapp_configured": whatsapp_client.is_configured(),
            "whatsapp_phone_number_id_set": bool(settings.WHATSAPP_PHONE_NUMBER_ID),
            "whatsapp_token_set": bool(settings.WHATSAPP_TOKEN),
            "webhook_diagnostics": webhook_diagnostics,
            "model": settings.GROQ_MODEL,
            "env": settings.APP_ENV
        }),
        status_code=200 if is_ready else 503,
        media_type="application/json"
    )

if __name__ == "__main__":
    port = _safe_int_env("PORT", settings.PORT)
    workers = _safe_int_env("WORKERS", 1)
    if settings.DEBUG:
        uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
    elif workers <= 1:
        uvicorn.run(
            "app.main:app",
            host="0.0.0.0",
            port=port,
            proxy_headers=True,
            forwarded_allow_ips="*"
        )
    else:
        uvicorn.run(
            "app.main:app",
            host="0.0.0.0",
            port=port,
            workers=workers,
            proxy_headers=True,
            forwarded_allow_ips="*"
        )
