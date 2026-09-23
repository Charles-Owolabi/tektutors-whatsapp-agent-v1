import datetime
from typing import Optional
from sqlalchemy import String, Text, Integer, Float, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    phone: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    course_interest: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    skill_level: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # Beginner, Intermediate, Advanced
    status: Mapped[str] = mapped_column(String(30), default="new")  # new, qualified, hot, enrolled, cold
    budget_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    lead_score: Mapped[int] = mapped_column(Integer, default=50)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    phone: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    customer_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    ai_active: Mapped[bool] = mapped_column(Boolean, default=True)  # True = AI, False = Human Handoff
    handoff_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ai_draft_reply: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_message_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=func.now())
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=func.now())

    messages: Mapped[list["Message"]] = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")

class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    sender: Mapped[str] = mapped_column(String(20), nullable=False)  # user, assistant, system, human
    body: Mapped[str] = mapped_column(Text, nullable=False)
    media_type: Mapped[str] = mapped_column(String(20), default="text")  # text, audio, image, interactive
    media_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    tool_calls_log: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime.datetime] = mapped_column(DateTime, default=func.now())

    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")

class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    duration_weeks: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    syllabus: Mapped[str] = mapped_column(Text, nullable=False)
    prerequisites: Mapped[str] = mapped_column(Text, nullable=False)
    career_outcomes: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class FAQ(Base):
    __tablename__ = "faqs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="General")
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)

class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    lead_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("leads.id"), nullable=True)
    phone: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    service_or_course: Mapped[str] = mapped_column(String(150), nullable=False)
    preferred_time: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="scheduled")  # scheduled, completed, cancelled
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=func.now())

class SystemConfig(Base):
    __tablename__ = "system_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    agent_name: Mapped[str] = mapped_column(String(100), default="Tara")
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    global_ai_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    persona_tone: Mapped[str] = mapped_column(String(50), default="consultative")
    business_hours: Mapped[str] = mapped_column(String(100), default="9:00 AM - 6:00 PM (Mon-Sat)")
    away_message: Mapped[str] = mapped_column(Text, default="Thanks for contacting TekTutors! Our admissions team is currently away, but our AI advisor Tara is available 24/7 to assist you.")
    currency: Mapped[str] = mapped_column(String(10), default="NGN")
    currency_symbol: Mapped[str] = mapped_column(String(5), default="₦")
    outbound_webhook_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    outbound_webhook_secret: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Editable Email Branding, Header & Footer Configuration
    email_header_title: Mapped[Optional[str]] = mapped_column(String(150), default="TekTutors")
    email_header_subtitle: Mapped[Optional[str]] = mapped_column(String(255), default="Practical Data Analytics & AI Mentorship Academy")
    email_header_badge: Mapped[Optional[str]] = mapped_column(String(100), default="Live 1-on-1 Mentorship")
    email_primary_color: Mapped[Optional[str]] = mapped_column(String(30), default="#eb6711")
    email_footer_contact: Mapped[Optional[str]] = mapped_column(Text, default="Have questions or need help? Reply to this email or message Tara on WhatsApp: +234 806 358 4517")
    email_footer_copyright: Mapped[Optional[str]] = mapped_column(String(255), default="TekTutors Academy. All rights reserved.")
    email_footer_extra: Mapped[Optional[str]] = mapped_column(Text, default="")
    email_custom_header_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    email_custom_footer_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

class CostTelemetry(Base):
    __tablename__ = "cost_telemetry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    phone: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    query_type: Mapped[str] = mapped_column(String(50), nullable=False)  # fast_path_greeting, fast_path_track, fast_path_registration, fast_path_curriculum, llm_call
    model_used: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    tokens_saved: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    estimated_savings_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=func.now())

class EmailLog(Base):
    __tablename__ = "email_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    lead_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("leads.id"), nullable=True)
    recipient_email: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    recipient_name: Mapped[str] = mapped_column(String(100), default="Student")
    campaign_type: Mapped[str] = mapped_column(String(50), default="follow_up")  # follow_up, marketing, promotional, direct
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body_html: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="sent")  # sent, delivered, failed
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=func.now())

class ScheduledEmail(Base):
    __tablename__ = "scheduled_emails"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    lead_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("leads.id"), nullable=True)
    recipient_email: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    recipient_name: Mapped[str] = mapped_column(String(100), default="Student")
    sequence_day: Mapped[int] = mapped_column(Integer, default=0)  # 0 to 5
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    campaign_type: Mapped[str] = mapped_column(String(50), default="drip_follow_up")
    course_name: Mapped[Optional[str]] = mapped_column(String(150), default="Data Analytics & BI Accelerator")
    cta_text: Mapped[Optional[str]] = mapped_column(String(100), default="Register Online")
    cta_url: Mapped[Optional[str]] = mapped_column(String(255), default="https://tektutors.com.ng/registration")
    scheduled_for: Mapped[datetime.datetime] = mapped_column(DateTime, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)  # pending, sent, failed, cancelled
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=func.now())
    sent_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)

class WhatsAppLog(Base):
    __tablename__ = "whatsapp_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    lead_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("leads.id"), nullable=True)
    recipient_phone: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    recipient_name: Mapped[str] = mapped_column(String(100), default="Student")
    message_type: Mapped[str] = mapped_column(String(50), default="broadcast")  # broadcast, direct, assistant, human, sequence
    campaign_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="delivered")  # sent, delivered, failed
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=func.now())

class ScheduledWhatsAppMessage(Base):
    __tablename__ = "scheduled_whatsapp_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    lead_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("leads.id"), nullable=True)
    recipient_phone: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    recipient_name: Mapped[str] = mapped_column(String(100), default="Student")
    sequence_step: Mapped[int] = mapped_column(Integer, default=1)  # 1, 2, or 3
    step_title: Mapped[str] = mapped_column(String(150), default="Step 1: Curriculum & Roadmap")
    body: Mapped[str] = mapped_column(Text, nullable=False)
    buttons_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scheduled_for: Mapped[datetime.datetime] = mapped_column(DateTime, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)  # pending, sent, delivered, failed, cancelled
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=func.now())
    sent_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)

