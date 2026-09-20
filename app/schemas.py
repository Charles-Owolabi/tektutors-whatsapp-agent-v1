from pydantic import BaseModel, Field
from typing import Optional, List
import datetime

# --- Webhook Schemas ---
class WhatsAppMedia(BaseModel):
    id: Optional[str] = None
    mime_type: Optional[str] = None
    sha256: Optional[str] = None

class WhatsAppTextMessage(BaseModel):
    body: str

class WhatsAppMessageItem(BaseModel):
    from_number: str = Field(alias="from", default="")
    id: str
    timestamp: str
    type: str = "text"
    text: Optional[WhatsAppTextMessage] = None
    image: Optional[WhatsAppMedia] = None
    audio: Optional[WhatsAppMedia] = None

class WhatsAppValue(BaseModel):
    messaging_product: str = "whatsapp"
    metadata: dict = {}
    contacts: Optional[List[dict]] = None
    messages: Optional[List[WhatsAppMessageItem]] = None

class WhatsAppChange(BaseModel):
    value: WhatsAppValue
    field: str = "messages"

class WhatsAppEntry(BaseModel):
    id: str
    changes: List[WhatsAppChange]

class WhatsAppWebhookPayload(BaseModel):
    object: str = "whatsapp_business_account"
    entry: List[WhatsAppEntry]

# --- Admin & Simulator Schemas ---
class SimulatorChatRequest(BaseModel):
    phone: str = "2348000000000"
    message: str
    media_type: str = "text"
    media_url: Optional[str] = None

class HumanMessageRequest(BaseModel):
    phone: str
    message: str

class HandoffToggleRequest(BaseModel):
    phone: str
    ai_active: bool
    reason: Optional[str] = None

class LeadCreate(BaseModel):
    phone: str
    name: Optional[str] = None
    email: Optional[str] = None
    course_interest: Optional[str] = None
    skill_level: Optional[str] = None
    status: str = "new"
    budget_ready: bool = False
    lead_score: Optional[int] = 50
    notes: Optional[str] = None

class CourseCreate(BaseModel):
    title: str
    slug: str
    price: float
    duration_weeks: int
    description: str
    syllabus: str
    prerequisites: str
    career_outcomes: str
    is_active: bool = True

class CourseUpdate(BaseModel):
    title: Optional[str] = None
    slug: Optional[str] = None
    price: Optional[float] = None
    duration_weeks: Optional[int] = None
    description: Optional[str] = None
    syllabus: Optional[str] = None
    prerequisites: Optional[str] = None
    career_outcomes: Optional[str] = None
    is_active: Optional[bool] = None

class FAQCreate(BaseModel):
    category: str = "General"
    question: str
    answer: str

class FAQUpdate(BaseModel):
    category: Optional[str] = None
    question: Optional[str] = None
    answer: Optional[str] = None

class LeadStatusUpdate(BaseModel):
    status: str
    notes: Optional[str] = None

class LeadNotesUpdate(BaseModel):
    notes: str

class CampaignSendRequest(BaseModel):
    campaign_id: str
    target_audience: str = "all"  # all, hot, qualified, new, custom
    custom_message: Optional[str] = None
    target_phone: Optional[str] = None
    custom_numbers: Optional[List[str]] = None
    custom_numbers_raw: Optional[str] = None

class CampaignUpdateRequest(BaseModel):
    template_body: str
    title: Optional[str] = None
    suggested_actions: Optional[List[str]] = None

class LeadBulkImportItem(BaseModel):
    phone: str
    name: Optional[str] = None
    email: Optional[str] = None
    course_interest: Optional[str] = None
    status: Optional[str] = "new"
    notes: Optional[str] = None

class LeadBulkImportRequest(BaseModel):
    leads: Optional[List[LeadBulkImportItem]] = None
    raw_text: Optional[str] = None  # CSV or newline/comma separated text

class AppointmentStatusUpdate(BaseModel):
    status: str  # scheduled, completed, cancelled

class SystemConfigResponse(BaseModel):
    agent_name: str
    system_prompt: str
    global_ai_enabled: bool
    persona_tone: Optional[str] = "consultative"
    business_hours: Optional[str] = "9:00 AM - 6:00 PM (Mon-Sat)"
    away_message: Optional[str] = "Thanks for contacting TekTutors! We are currently outside business hours, but our AI advisor is here to help you explore courses."
    currency: Optional[str] = "NGN"
    currency_symbol: Optional[str] = "₦"
    outbound_webhook_url: Optional[str] = None
    outbound_webhook_secret: Optional[str] = None
    # Editable Email Branding
    email_header_title: Optional[str] = "TekTutors"
    email_header_subtitle: Optional[str] = "Practical Data Analytics & AI Mentorship Academy"
    email_header_badge: Optional[str] = "Live 1-on-1 Mentorship"
    email_primary_color: Optional[str] = "#eb6711"
    email_footer_contact: Optional[str] = "Have questions or need help? Reply to this email or message Tara on WhatsApp: +234 806 358 4517"
    email_footer_copyright: Optional[str] = "TekTutors Academy. All rights reserved."
    email_footer_extra: Optional[str] = ""
    email_custom_header_html: Optional[str] = None
    email_custom_footer_html: Optional[str] = None

class SystemConfigUpdate(BaseModel):
    agent_name: Optional[str] = None
    system_prompt: Optional[str] = None
    global_ai_enabled: Optional[bool] = None
    persona_tone: Optional[str] = None
    business_hours: Optional[str] = None
    away_message: Optional[str] = None
    currency: Optional[str] = None
    currency_symbol: Optional[str] = None
    outbound_webhook_url: Optional[str] = None
    outbound_webhook_secret: Optional[str] = None
    # Editable Email Branding
    email_header_title: Optional[str] = None
    email_header_subtitle: Optional[str] = None
    email_header_badge: Optional[str] = None
    email_primary_color: Optional[str] = None
    email_footer_contact: Optional[str] = None
    email_footer_copyright: Optional[str] = None
    email_footer_extra: Optional[str] = None
    email_custom_header_html: Optional[str] = None
    email_custom_footer_html: Optional[str] = None

class EmailBrandingResponse(BaseModel):
    header_title: str = "TekTutors"
    header_subtitle: str = "Practical Data Analytics & AI Mentorship Academy"
    header_badge: str = "Live 1-on-1 Mentorship"
    primary_color: str = "#eb6711"
    footer_contact: str = "Have questions or need help? Reply to this email or message Tara on WhatsApp: +234 806 358 4517"
    footer_copyright: str = "TekTutors Academy. All rights reserved."
    footer_extra: Optional[str] = ""
    custom_header_html: Optional[str] = None
    custom_footer_html: Optional[str] = None

class EmailBrandingUpdate(BaseModel):
    header_title: Optional[str] = None
    header_subtitle: Optional[str] = None
    header_badge: Optional[str] = None
    primary_color: Optional[str] = None
    footer_contact: Optional[str] = None
    footer_copyright: Optional[str] = None
    footer_extra: Optional[str] = None
    custom_header_html: Optional[str] = None
    custom_footer_html: Optional[str] = None

class EmailBrandingPreviewRequest(BaseModel):
    header_title: Optional[str] = "TekTutors"
    header_subtitle: Optional[str] = "Practical Data Analytics & AI Mentorship Academy"
    header_badge: Optional[str] = "Live 1-on-1 Mentorship"
    primary_color: Optional[str] = "#eb6711"
    footer_contact: Optional[str] = "Have questions or need help? Reply to this email or message Tara on WhatsApp: +234 806 358 4517"
    footer_copyright: Optional[str] = "TekTutors Academy. All rights reserved."
    footer_extra: Optional[str] = ""
    custom_header_html: Optional[str] = None
    custom_footer_html: Optional[str] = None
    sample_subject: Optional[str] = "Welcome to TekTutors Live 1-on-1 Mentorship"
    sample_body: Optional[str] = "Hi Student,\n\nWe are excited to share your personalized curriculum roadmap. Here is what makes our 1-on-1 model exceptional:\n\n• **100% Dedicated Live Mentor** guiding every line of code\n• **3 Employer-Grade Portfolio Projects** deployed to GitHub\n• **Flexible Month-to-Month Tuition** with zero long-term lock-in\n\nReady to get started?"
    cta_text: Optional[str] = "Register Online"
    cta_url: Optional[str] = "https://tektutors.com.ng/registration"

# --- Email Hub & Marketing Schemas ---
class SingleEmailSendRequest(BaseModel):
    recipient_email: str
    recipient_name: Optional[str] = "Student"
    subject: str
    body: str
    campaign_type: str = "follow_up"  # follow_up, marketing, promotional, direct
    lead_id: Optional[int] = None
    cta_text: Optional[str] = "Register Online"
    cta_url: Optional[str] = "https://tektutors.com.ng/registration"

class BroadcastEmailSendRequest(BaseModel):
    template_id: Optional[str] = None
    target_audience: str = "all"  # all, hot, qualified, new
    campaign_type: str = "marketing"  # follow_up, marketing, promotional
    subject: str
    body: str
    cta_text: Optional[str] = "Enroll Now"
    cta_url: Optional[str] = "https://tektutors.com.ng/registration"



