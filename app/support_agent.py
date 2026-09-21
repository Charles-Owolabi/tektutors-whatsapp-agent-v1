import os
import re
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from app.config import settings
from app.whatsapp import whatsapp_client

logger = logging.getLogger(__name__)

SUPPORT_SYSTEM_PROMPT = """You are the TekTutors In-App AI Support and Troubleshooting Copilot.
You are embedded directly inside the TekTutors WhatsApp CRM and AI Sales Agent Dashboard.
Your mission is to provide expert, clear, friendly, and practical guidance to the TekTutors administrator or marketing operator.

You specialize in:
1. EXPLAINING APP FEATURES AND BEST PRACTICES:
   - Campaign Broadcasts: How to launch broadcasts, target audiences ('all', 'hot', 'qualified', 'new', 'custom'), write compelling templates, use personalized variables ({{name}}, {{course}}), and action buttons.
   - Live Handoff and Human Advisor: How to monitor incoming WhatsApp conversations, view AI sentiment and lead score, take over conversations, toggle AI on/off, and send manual replies.
   - WhatsApp Simulator: How to test simulated student queries, explore multi-turn flows, and inspect fast-path tools.
   - Leads CRM: Managing lead stages (new, contacted, qualified, hot, enrolled), budget readiness, and automated scoring.
   - Email Hub and Scheduled Drip: Setting up email campaigns, enrollment confirmation, curriculum emails, and automatic follow-up delays.
   - Course Catalog and FAQs: Updating course descriptions, syllabus links, tuition fees, and FAQs.
   - System Settings: Configuring AI model (Groq LLaMA 3.3), fallback parameters, fast-path triggers, and system prompt personality.

2. TROUBLESHOOTING TECHNICAL AND OPERATIONAL ISSUES (ESPECIALLY META WHATSAPP CLOUD API):
   - Why did only 1 or 2 out of 3 recipients receive a WhatsApp campaign?
     * REASON 1 (The 24-Hour Customer Care Window): Meta strictly forbids free-form text or interactive button messages to contacts who haven't messaged the business in the last 24 hours. If an operator sends a campaign, only users who recently messaged the bot within 24 hours will receive it. Meta rejects the rest with error 131047. To reach cold contacts or those outside 24h, you MUST submit and use a pre-approved Meta Message Template.
     * REASON 2 (Development/Sandbox Test Numbers): If the WhatsApp app is in Development Mode in the Meta Developer Portal, Meta only delivers messages to phone numbers added to the verified test recipients list (Manage phone number list under API Setup). If recipient #1 was verified but #2 and #3 were not, Meta drops them (error 131030).
     * REASON 3 (Phone Formatting): Phone numbers must be in international E.164 format without '+' or leading '0' (e.g. 2348012345678). Numbers with invalid lengths, wrong country codes, or without an active WhatsApp account fail with error 131026.
   - Why is the WhatsApp bot not responding to incoming student messages?
     * Check if WHATSAPP_TOKEN has expired (temporary tokens expire in 24 hours; a permanent System User Token is required for production).
     * Check if Meta Webhook is verified with WHATSAPP_VERIFY_TOKEN.
     * Check if Webhook event subscriptions include 'messages'.
     * Verify Railway or server deployment URL is active and awake.
   - Email Hub issues:
     * Resend API key missing or invalid.
     * Domain not verified: If using a custom domain (e.g. info@tektutors.com.ng), DNS records (DKIM, SPF, MX) must be verified in Resend. Otherwise, Resend only allows sending from onboarding@resend.dev to the registered account email.

3. YOUR TONE AND STYLE:
   - Be encouraging, concise, and structured.
   - Use formatting: bold key terms, use bullet points, and provide step-by-step instructions.
   - If diagnosing an issue, provide both the Root Cause and How to Fix It in 2 Minutes.
   - Include direct guidance referencing the dashboard UI tabs (Broadcasts, Leads CRM, Simulator, Settings).
"""

def get_system_diagnostics() -> Dict[str, Any]:
    """Gather real-time operational status of core services."""
    wa_token = bool(settings.WHATSAPP_TOKEN)
    wa_phone_id = bool(settings.WHATSAPP_PHONE_NUMBER_ID)
    groq_key = bool(settings.GROQ_API_KEY)
    resend_key = bool(getattr(settings, "RESEND_API_KEY", None))
    smtp_configured = bool(getattr(settings, "SMTP_HOST", None) and getattr(settings, "SMTP_USER", None))

    is_live_wa = whatsapp_client.is_configured()
    token_preview = settings.WHATSAPP_TOKEN[:10] + "..." if settings.WHATSAPP_TOKEN else "Not Set"

    return {
        "timestamp": datetime.now().isoformat(),
        "whatsapp": {
            "status": "configured" if is_live_wa else "mock_mode",
            "phone_number_id": settings.WHATSAPP_PHONE_NUMBER_ID or "Not Set",
            "token_preview": token_preview,
            "is_live": is_live_wa,
        },
        "groq_ai": {
            "status": "configured" if groq_key else "missing_key",
            "model": settings.GROQ_MODEL or "llama-3.3-70b-versatile",
        },
        "email": {
            "resend_configured": resend_key,
            "smtp_configured": smtp_configured,
            "active_engine": "Resend API" if resend_key else ("SMTP" if smtp_configured else "Mock Mode"),
        },
        "database": {
            "type": "PostgreSQL" if "postgresql" in settings.DATABASE_URL.lower() else "SQLite",
        }
    }

async def generate_support_reply(query: str, chat_history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    """Generate a context-aware troubleshooting and guidance response."""
    diagnostics = get_system_diagnostics()
    diag_summary = json.dumps(diagnostics, indent=2)

    messages = [
        SystemMessage(content=f"{SUPPORT_SYSTEM_PROMPT}\n\nCURRENT SYSTEM DIAGNOSTIC TELEMETRY:\n{diag_summary}")
    ]

    if chat_history:
        for msg in chat_history[-6:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))

    messages.append(HumanMessage(content=query))

    try:
        llm = ChatGroq(
            api_key=settings.GROQ_API_KEY,
            model_name=settings.GROQ_MODEL or "llama-3.3-70b-versatile",
            temperature=0.3,
            max_tokens=1024,
        )
        response = await llm.ainvoke(messages)
        reply_text = response.content
    except Exception as e:
        logger.error(f"Error invoking Groq LLM for AI Support: {e}")
        lower_q = query.lower()
        if any(term in lower_q for term in ["campaign", "recipien", "whatsapp", "not recieved", "not received", "only 1", "failed"]):
            reply_text = (
                "### 🩺 Diagnostics: Why Some Recipients Did Not Receive the WhatsApp Campaign\n\n"
                "Even though the app recorded all recipients, WhatsApp only delivered to 1 due to **Meta WhatsApp Cloud API restrictions**:\n\n"
                "1. **The 24-Hour Customer Care Window (Most Common)**:\n"
                "   * Meta strictly blocks free-form text or button messages to numbers that have **not messaged your WhatsApp bot within the last 24 hours**.\n"
                "   * Only recipients who recently chatted with your bot will receive standard campaign broadcasts. The others are rejected with Meta error `131047`.\n"
                "   * **Solution:** Have those recipients message your WhatsApp bot first to open the 24-hour window, or use a pre-approved Meta Template Message for cold outreach.\n\n"
                "2. **Meta Developer Sandbox Mode (Test Numbers)**:\n"
                "   * If your WhatsApp app is in **Development Mode**, Meta only delivers to up to 5 verified numbers listed in your Meta Developer Console (*WhatsApp > API Setup > To*).\n"
                "   * **Solution:** Add and verify the remaining phone numbers in your Meta Developer Dashboard.\n\n"
                "3. **Phone Number Formatting**:\n"
                "   * Ensure phone numbers use international format without '+' (e.g., `2348012345678`)."
            )
        else:
            reply_text = (
                f"I am here to assist you with the TekTutors WhatsApp CRM! (Live AI status note: {e}).\n\n"
                "You can ask me about:\n"
                "- How to send WhatsApp broadcasts and why deliveries might fail\n"
                "- How to configure the 24-hour customer window and Meta templates\n"
                "- Managing leads, automated scoring, and email drip sequences\n"
                "- System settings, Groq LLM, and Railway deployment"
            )

    return {
        "reply": reply_text,
        "diagnostics": diagnostics
    }
