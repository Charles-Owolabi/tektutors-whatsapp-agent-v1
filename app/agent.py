import os
import re
import json
import logging
import operator
import asyncio
from typing import Dict, Any, List, Optional, Sequence, Annotated, TypedDict, Literal
from langchain_groq import ChatGroq
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver

from app.config import settings
from app.tools import (
    TEKTUTORS_TOOLS,
    search_tektutors_courses,
    get_course_faq_answer,
    qualify_and_capture_lead,
    schedule_advisor_call,
    escalate_to_human_advisor,
    generate_enrollment_checkout,
    calculate_career_roi,
    check_scholarship_and_discounts,
    trigger_conversion_email_campaign,
    schedule_followup_email
)

logger = logging.getLogger(__name__)


def strip_asterisks(text: str) -> str:
    """
    Remove all asterisks (*) from WhatsApp messages to ensure a clean, professional,
    and elegant presentation without distracting asterisks showing to customers.
    Also transforms any markdown bullet asterisks ('* ') to clean bullets ('• ').
    """
    if not text or not isinstance(text, str):
        return text
    # Convert markdown list bullets (* item) to clean bullets (• item)
    text = re.sub(r'(?m)^\s*\*\s+', '• ', text)
    # Remove all remaining asterisks
    text = text.replace('*', '')
    return text


def convert_markdown_tables_to_whatsapp(text: str) -> str:
    """
    Detect markdown tables in text and convert them into clean, mobile-friendly WhatsApp bullet cards.
    WhatsApp mobile does NOT render markdown tables; raw tables display as broken, unreadable walls of pipe symbols.
    """
    if not text or "|" not in text:
        return text

    number_emojis = {
        "1": "1️⃣", "2": "2️⃣", "3": "3️⃣", "4": "4️⃣",
        "5": "5️⃣", "6": "6️⃣", "7": "7️⃣", "8": "8️⃣", "9": "9️⃣"
    }

    lines = text.split("\n")
    output_lines = []
    table_lines = []

    def format_table_block(tbl_lines: List[str]) -> str:
        parsed_rows = []
        for line in tbl_lines:
            stripped = line.strip()
            # Ignore divider line like |---|---|
            if re.match(r'^\|?[\s\-:|]+\|?$', stripped):
                continue
            cells = [c.strip() for c in stripped.split("|")]
            if cells and cells[0] == "":
                cells.pop(0)
            if cells and cells[-1] == "":
                cells.pop()
            if any(c for c in cells):
                parsed_rows.append(cells)

        if len(parsed_rows) <= 1:
            return "\n".join(tbl_lines)

        headers = [re.sub(r'[*_`]', '', h).strip() for h in parsed_rows[0]]
        data_rows = parsed_rows[1:]

        cards = []
        for row in data_rows:
            if not any(row):
                continue
            while len(row) < len(headers):
                row.append("")

            card_lines = []
            raw_first = row[0].strip()
            first_digits = re.sub(r"[^\d]", "", raw_first)

            # Check if first column is an index/number (#, 1, 2, etc.)
            if first_digits and len(row) >= 3:
                badge = number_emojis.get(first_digits, f"{first_digits}.")
                track_title = row[1].strip()
                clean_title = re.sub(r'[*_`]', '', track_title).strip()
                duration = row[2].strip()
                clean_duration = re.sub(r'[*_`]', '', duration).strip()
                details = row[3].strip() if len(row) > 3 else ""
                clean_details = re.sub(r'[*_`]', '', details).strip()

                header_dur_label = headers[2] if len(headers) > 2 else "Duration"
                header_det_label = headers[3] if len(headers) > 3 else "What You'll Master"

                card_lines.append(f"{badge} {clean_title}")
                if clean_duration:
                    card_lines.append(f"   ⏱️ {header_dur_label}: {clean_duration}")
                if clean_details:
                    card_lines.append(f"   💡 {header_det_label}: {clean_details}")
            else:
                clean_first = re.sub(r'[*_`]', '', raw_first).strip()
                card_lines.append(f"🔹 {clean_first}")
                for h, val in zip(headers[1:], row[1:]):
                    val_str = re.sub(r'[*_`]', '', val).strip()
                    if val_str:
                        card_lines.append(f"   • {h}: {val_str}")

            cards.append("\n".join(card_lines))

        return "\n\n".join(cards)

    in_table = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2:
            in_table = True
            table_lines.append(line)
        else:
            if in_table:
                output_lines.append(format_table_block(table_lines))
                table_lines = []
                in_table = False
            output_lines.append(line)

    if in_table:
        output_lines.append(format_table_block(table_lines))

    return "\n".join(output_lines)


def sanitize_pricing_hallucinations(text: str) -> str:
    """
    Guard against LLM multiplying course weeks by tuition (e.g. 10 wks = ₦900,000 or ₦1,000,000).
    TekTutors tuition is ₦100,000 / month, and with 10% upfront discount it is ₦90,000 (saving ₦10,000).
    """
    if not text or not isinstance(text, str):
        return text
    # Fix phrases like "(e.g., 10-wk Data Analytics = ₦900,000)" or "= ₦900,000"
    text = re.sub(
        r'(?:10-?wk|10\s*weeks?)[^.\n]*?[=:]\s*(?:₦|NGN|N)?\s*900[,.]?000',
        '10% upfront discount = ₦90,000 (saves ₦10,000)',
        text,
        flags=re.IGNORECASE
    )
    # Fix any remaining occurrences of 900,000 / ₦900,000
    text = re.sub(
        r'(?:₦|NGN|N)?\s*900[,.]?000\s*(?:naira|NGN)?',
        '₦90,000',
        text,
        flags=re.IGNORECASE
    )
    # Fix any 1,000,000 / ₦1,000,000 references to ₦100,000 / month
    text = re.sub(
        r'(?:₦|NGN|N)?\s*1[,.]000[,.]?000\s*(?:naira|NGN)?',
        '₦100,000 / month',
        text,
        flags=re.IGNORECASE
    )
    return text


def sanitize_whatsapp_message(text: str) -> str:
    """
    Apply comprehensive WhatsApp message formatting:
    1. Converts any markdown tables into clean, mobile-friendly WhatsApp cards.
    2. Enforces correct pricing guardrails against hallucinations.
    3. Strips all markdown asterisks (*) so customers never see raw asterisk symbols.
    """
    if not text or not isinstance(text, str):
        return text
    text = convert_markdown_tables_to_whatsapp(text)
    text = sanitize_pricing_hallucinations(text)
    text = strip_asterisks(text)
    return text


SYSTEM_PROMPT_TEXT = """You are Tara, Senior AI Admissions Advisor for TekTutors (Practical Data Analytics & AI Academy).

ACADEMY ESSENTIALS:
• Model: Live 1-on-1 private video mentorship with industry mentors (never crowded lecture halls).
• Pathways & Durations:
  - Track 1: Data Analytics & BI Accelerator (10 wks: Excel + SQL + Power BI + Python)
  - Single-tool tracks (6-8 wks): Track 2 (Excel), Track 3 (SQL), Track 4 (Power BI), Track 5 (Python for AI), R for Data, Advanced Excel.
  - Specialized tracks: Machine Learning (16 wks), Data Science (16-20 wks), Business Analysis (10 wks), Financial/HR/Marketing Analytics (6-8 wks).
  - RULE: Durations are in WEEKS, not months. Single tools are strictly 6-8 weeks; multi-tool bootcamps are 10 weeks.
• Tuition & Discounts:
  - Standard Plan: ₦100,000 / month flexible month-to-month billing (cancel anytime).
  - 10% Upfront Discount: Exactly ₦90,000 (saves ₦10,000 off standard monthly fee).
  - PRICING GUARD: NEVER multiply weeks by ₦100,000! Never quote ₦900,000 or ₦1,000,000.
• Location & Delivery: 100% live online worldwide (no commute/walk-in classes). Corporate HQ: Lagos, Nigeria. Contact: WhatsApp/Phone (+2348063584517), email (info@tektutors.com.ng).
• Portal: https://tektutors.com.ng/registration

OPERATIONAL RULES:
1. TRUTH & TOOLS: Use `search_tektutors_courses` and `get_course_faq_answer` for verified facts. Never invent unlisted policies or locations.
2. ADVISOR CALLS: To book a 1-on-1 discovery call, warmly ask for Full Name, preferred time/date, and course interest; call `schedule_advisor_call`. Do not confuse with human escalation.
3. CURRICULUM: For a specific course (e.g. Machine Learning, Data Science, Power BI, SQL, Python), summarize THAT exact course's modules and syllabus. NEVER mention Data Analytics, Excel, or Power BI when the prospect specifically asks for Machine Learning or Data Science! Without an email, summarize the specific modules for their chosen course and offer the syllabus PDF to their email. When an email is given, call `qualify_and_capture_lead` immediately with their specific `course_interest`, confirm dispatch, and do not ask again.
4. HUMAN ESCALATION: Only escalate (`escalate_to_human_advisor`) for formal payment/refund disputes or explicit demands for a human manager.
5. WHATSAPP PRESENTATION & STYLE (ZERO-ASTERISK POLICY):
   - CRITICAL ZERO-ASTERISK RULE: NEVER use asterisks (*) anywhere in your message. Do NOT use *bold* or **bold**.
     Asterisks appear as raw symbols on WhatsApp Web and mobile devices, looking messy and unprofessional.
   - For emphasis and section headers, use clean emojis (1️⃣, 2️⃣, 3️⃣, 🔹, 📌, 👉, 💡, ⏱️, 💵, 🎯, 🌟), natural capitalization, or clean spacing.
   - For bullet points, use clean dots (•) or emoji bullets (🔹, 👉), NEVER asterisks (*).
   - NEVER USE MARKDOWN TABLES (| # | Track | Duration |). WhatsApp mobile app cannot render tables.
   - Keep paragraphs under 3 sentences. Warm consultative tone ending with a guiding question.
6. COURSE PRESENTATION & CONSULTATION SEQUENCE:
• Broad inquiry/greeting or when asked what courses are offered:
  Present the pathways using this clean, mobile-optimized card layout with NO asterisks:

  🎓 TekTutors Practical Tech Pathways (1-on-1 Mentorship)

  1️⃣ Data Analytics & BI Accelerator (⏱️ 10 wks)
     💡 What You'll Master: Excel, SQL, Power BI, Python + 3 real capstone projects
     ⭐ Our #1 Most Popular Track!

  2️⃣ Excel for Data Analysis (⏱️ 6-8 wks)
     💡 What You'll Master: Advanced formulas, Power Query, automated reporting & dashboards

  3️⃣ SQL for Analytics & Data Engineering (⏱️ 6-8 wks)
     💡 What You'll Master: Relational databases, complex queries, joins, CTEs & ETL

  4️⃣ Power BI & Business Intelligence (⏱️ 6-8 wks)
     💡 What You'll Master: Data modeling, DAX measures, interactive KPI dashboards & publishing

  5️⃣ Applied Python for Analytics & AI (⏱️ 6-8 wks)
     💡 What You'll Master: Python basics, Pandas, NumPy, visualization & intro to AI/ML

  6️⃣ Explore Other Specialized Tracks (⏱️ 6-20 wks)
     💡 Tracks Available: Data Science, Machine Learning, Business Analysis, Financial/HR Analytics

  💰 Flexible Tuition: ₦100,000 / month (or ₦90,000 upfront with 10% discount).
  🎁 Fast-Action Perk: Free ₦35,000 CV Optimization & LinkedIn Audit included!

  👉 Please reply with the number of your choice (1-6) OR type the name of the track you'd like to explore!

• Specific course inquiry (e.g. Machine Learning, Power BI, SQL, Python): NEVER dump all 6 tracks. Focus 100% on the requested course:
  a. Confirm course highlights and outcomes (1-on-1 mentor, 3 capstone projects, ₦100,000/month or ₦90,000 upfront).
  b. Ask ONE diagnostic qualification question (e.g., "Do you have prior experience with Python/math, or are you starting from scratch?").
  c. Guide toward next step: offer syllabus PDF to email or booking a free 15-min discovery call.
7. SALES EXCELLENCE: Highlight beginner transformation, 1,200+ graduates, free ₦35,000 CV/LinkedIn audit for enrolling this week, and registration link (https://tektutors.com.ng/registration).
8. CAMPAIGN EMAILS: Call `trigger_conversion_email_campaign` when email is provided or for syllabus, consultation, or scholarship requests.
9. SCHEDULED EMAILS: If a prospect asks to receive an email later (e.g. "tomorrow", "in 2 hours", "next week"), call `schedule_followup_email` with the specified delay/time and warmly confirm scheduled delivery."""

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    phone: str
    tool_logs: Annotated[List[str], operator.add]
    system_prompt: str
    is_escalated: bool


SUPPORTED_GROQ_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
    "groq/compound-mini",
    "allam-2-7b",
    "groq/compound"
]

_cached_system_config: Optional[Dict[str, Any]] = None
_cached_system_config_expiry: float = 0.0
_cached_config_lock = asyncio.Lock()

async def get_cached_system_config(force_refresh: bool = False) -> Dict[str, Any]:
    """Retrieve system configuration with a 60-second in-memory TTL to avoid DB overhead on every message."""
    global _cached_system_config, _cached_system_config_expiry
    now = asyncio.get_event_loop().time()
    if not force_refresh and _cached_system_config is not None and now < _cached_system_config_expiry:
        return _cached_system_config

    async with _cached_config_lock:
        now = asyncio.get_event_loop().time()
        if not force_refresh and _cached_system_config is not None and now < _cached_system_config_expiry:
            return _cached_system_config

        from app.database import AsyncSessionLocal
        from app.models import SystemConfig
        from sqlalchemy import select

        agent_name = "Tara"
        system_prompt = SYSTEM_PROMPT_TEXT
        ai_enabled = True

        try:
            async with AsyncSessionLocal() as db:
                stmt = select(SystemConfig).limit(1)
                res = await db.execute(stmt)
                config_record = res.scalar_one_or_none()
                if config_record:
                    agent_name = config_record.agent_name
                    system_prompt = config_record.system_prompt
                    ai_enabled = config_record.global_ai_enabled
                    tone = getattr(config_record, "persona_tone", "consultative")
                    tone_instructions = {
                        "friendly": "\n\nPERSONA TONE: Warm, encouraging, empathetic, and student-friendly. Speak like a welcoming mentor.",
                        "closer": "\n\nPERSONA TONE: High-converting sales closer. Be crisp, focus on ROI and enrollment momentum, and drive decisions.",
                        "formal": "\n\nPERSONA TONE: Executive, highly professional, structured, and formal B2B tone.",
                        "consultative": "\n\nPERSONA TONE: Consultative academic advisor. Ask diagnostic questions and tailor recommendations."
                    }.get(tone, "")
                    system_prompt += tone_instructions
        except Exception as e:
            logger.warning(f"Failed to fetch SystemConfig from DB; using defaults: {e}")

        _cached_system_config = {
            "agent_name": agent_name,
            "system_prompt": system_prompt,
            "ai_enabled": ai_enabled
        }
        _cached_system_config_expiry = now + 60.0  # 60s TTL
        return _cached_system_config

def invalidate_cached_system_config():
    """Immediately invalidate the cached system configuration."""
    global _cached_system_config_expiry
    _cached_system_config_expiry = 0.0


class TekTutorsAgentManager:
    def __init__(self):
        self.groq_api_key = settings.GROQ_API_KEY
        self.model_name = settings.GROQ_MODEL
        self.llm_with_tools = None

        # Build tool map by tool name
        self.tools_by_name = {tool.name: tool for tool in TEKTUTORS_TOOLS}
        self._init_llm()

        # Checkpointer for conversation state persistence
        self.checkpointer = MemorySaver()
        self.graph = self._build_graph()

    def _init_llm(self, preferred_model: Optional[str] = None):
        """Initialize LLM using preferred model or fallback cascade."""
        if not self.groq_api_key:
            logger.warning("GROQ_API_KEY not configured. Running in Mock fallback mode.")
            return

        target_model = preferred_model or self.model_name
        models_to_try = [target_model] + [m for m in SUPPORTED_GROQ_MODELS if m != target_model]

        for m in models_to_try:
            if not m:
                continue
            try:
                llm = ChatGroq(
                    model=m,
                    groq_api_key=self.groq_api_key,
                    temperature=0.2,
                    max_tokens=650,
                    max_retries=0,
                    request_timeout=15.0
                )
                self.llm_with_tools = llm.bind_tools(TEKTUTORS_TOOLS)
                self.model_name = m
                logger.info(f"TekTutors LangGraph Agent actively powered by Groq model '{m}'")
                return
            except Exception as e:
                logger.warning(f"Could not initialize Groq model '{m}': {e}")
        
        logger.error("Failed to initialize any Groq model from cascade list.")
        self.llm_with_tools = None

    def _build_graph(self):
        """Construct the LangGraph state machine workflow."""
        workflow = StateGraph(AgentState)

        # Nodes
        workflow.add_node("triage", self._triage_node)
        workflow.add_node("advisor", self._advisor_node)
        workflow.add_node("tools", self._tools_node)
        workflow.add_node("escalation", self._escalation_node)

        # Routing Edges
        workflow.add_edge(START, "triage")

        workflow.add_conditional_edges(
            "triage",
            self._route_after_triage,
            {
                "escalation": "escalation",
                "advisor": "advisor"
            }
        )

        workflow.add_conditional_edges(
            "advisor",
            self._route_after_advisor,
            {
                "tools": "tools",
                "end": END
            }
        )

        workflow.add_edge("tools", "advisor")
        workflow.add_edge("escalation", END)

        return workflow.compile(checkpointer=self.checkpointer)

    async def _triage_node(self, state: AgentState) -> Dict[str, Any]:
        """Triage incoming message for direct human escalation requests or disputes."""
        messages = state.get("messages", [])
        if not messages:
            return {"is_escalated": False}

        last_msg = messages[-1]
        content = getattr(last_msg, "content", "")
        if isinstance(content, str):
            lower = content.lower()
            escalation_triggers = [
                "speak to human", "talk to human", "human agent", "real person",
                "speak to someone", "customer service representative", "talk to manager",
                "fraud", "scam", "report", "sue", "legal action"
            ]
            if any(trig in lower for trig in escalation_triggers):
                logger.info(f"LangGraph Triage triggered direct human escalation for {state.get('phone')}")
                return {"is_escalated": True}

        return {"is_escalated": False}

    def _route_after_triage(self, state: AgentState) -> str:
        """Route to human escalation node or admissions advisor."""
        if state.get("is_escalated"):
            return "escalation"
        return "advisor"

    async def _escalation_node(self, state: AgentState) -> Dict[str, Any]:
        """Handle immediate human escalation node."""
        phone = state.get("phone", "")
        clean_phone = phone.strip().replace("+", "")
        try:
            await escalate_to_human_advisor.ainvoke({
                "phone": clean_phone,
                "reason": "Customer triggered human escalation in LangGraph triage."
            })
        except Exception as err:
            logger.error(f"Error escalating in LangGraph triage node: {err}")

        reply = "I am connecting you right away with a Senior TekTutors Admissions Advisor! They have been notified and will join this chat shortly. 📱"
        return {
            "messages": [AIMessage(content=reply)],
            "tool_logs": ["escalate_to_human_advisor"]
        }

    async def _advisor_node(self, state: AgentState) -> Dict[str, Any]:
        """Generate response or tool calls using ChatGroq or fallback engine with context windowing."""
        raw_messages = list(state.get("messages", []))
        system_prompt = state.get("system_prompt", SYSTEM_PROMPT_TEXT)

        # Context windowing: Always anchor with system prompt, bound to last 6 messages for speed and low cost
        formatted_messages = [SystemMessage(content=system_prompt)]
        non_system_msgs = [m for m in raw_messages if not isinstance(m, SystemMessage)]
        recent_msgs = non_system_msgs[-6:] if len(non_system_msgs) > 6 else non_system_msgs

        # Prune older ToolMessages to prevent multi-thousand token dumps from accumulating
        pruned_msgs = []
        for idx, m in enumerate(recent_msgs):
            if isinstance(m, ToolMessage) and idx < len(recent_msgs) - 3:
                compact_content = m.content[:80] + "..." if len(m.content) > 80 else m.content
                pruned_msgs.append(ToolMessage(content=compact_content, tool_call_id=m.tool_call_id))
            else:
                pruned_msgs.append(m)

        formatted_messages.extend(pruned_msgs)

        # Primary attempt with bound LLM
        if self.llm_with_tools:
            try:
                ai_msg = await self.llm_with_tools.ainvoke(formatted_messages)
                if hasattr(ai_msg, "content") and isinstance(ai_msg.content, str):
                    ai_msg.content = sanitize_whatsapp_message(ai_msg.content)
                return {"messages": [ai_msg]}
            except Exception as e:
                logger.warning(f"Error invoking model '{self.model_name}': {e}. Attempting fallback cascade...")
                for alt_model in SUPPORTED_GROQ_MODELS:
                    if alt_model == self.model_name:
                        continue
                    try:
                        alt_llm = ChatGroq(
                            model=alt_model,
                            groq_api_key=self.groq_api_key,
                            temperature=0.2,
                            max_tokens=650,
                            max_retries=0,
                            request_timeout=12.0
                        ).bind_tools(TEKTUTORS_TOOLS)
                        ai_msg = await alt_llm.ainvoke(formatted_messages)
                        if hasattr(ai_msg, "content") and isinstance(ai_msg.content, str):
                            ai_msg.content = sanitize_whatsapp_message(ai_msg.content)
                        logger.info(f"Fallback model '{alt_model}' succeeded! Switching active model.")
                        self.model_name = alt_model
                        self.llm_with_tools = alt_llm
                        return {"messages": [ai_msg]}
                    except Exception as alt_err:
                        logger.warning(f"Fallback model '{alt_model}' failed: {alt_err}")

        # Fallback to consultative mock engine if all remote models unavailable
        phone = state.get("phone", "")
        last_msg = state["messages"][-1]
        user_text = getattr(last_msg, "content", "")
        mock_res = await self._mock_ai_response(phone, user_text)
        return {
            "messages": [AIMessage(content=mock_res["response"])],
            "tool_logs": mock_res.get("tool_logs", [])
        }

    def _route_after_advisor(self, state: AgentState) -> str:
        """Route to tools node if tool calls were requested, else finish."""
        messages = state.get("messages", [])
        if not messages:
            return "end"
        last_msg = messages[-1]
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            return "tools"
        return "end"

    async def _tools_node(self, state: AgentState) -> Dict[str, Any]:
        """Execute tool calls invoked by the model, injecting customer phone when needed."""
        messages = state.get("messages", [])
        if not messages:
            return {}

        last_msg = messages[-1]
        tool_calls = getattr(last_msg, "tool_calls", [])
        clean_phone = state.get("phone", "").strip().replace("+", "")

        tool_messages = []
        executed_tools = []

        for tool_call in tool_calls:
            t_name = tool_call["name"]
            t_args = dict(tool_call.get("args", {}))
            tool_call_id = tool_call["id"]

            executed_tools.append(t_name)
            logger.info(f"LangGraph executing Tool '{t_name}' with args {t_args}")

            selected_tool = self.tools_by_name.get(t_name)
            if selected_tool:
                if "phone" in getattr(selected_tool, "args", {}) and "phone" not in t_args:
                    t_args["phone"] = clean_phone
                try:
                    tool_output = await selected_tool.ainvoke(t_args)
                except Exception as e:
                    logger.error(f"Error executing tool {t_name}: {e}")
                    tool_output = f"Error executing tool {t_name}: {str(e)}"
            else:
                tool_output = f"Tool {t_name} not found."

            tool_messages.append(ToolMessage(content=str(tool_output), tool_call_id=tool_call_id))

        return {
            "messages": tool_messages,
            "tool_logs": executed_tools
        }

    async def process_user_message(
        self,
        phone: str,
        user_text: str,
        chat_history_messages: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Process incoming user text through the LangGraph State Machine or Mock fallback engine.
        Returns: {"response": str, "tool_logs": List[str]}
        """
        clean_phone = phone.strip().replace("+", "")
        if chat_history_messages is None:
            chat_history_messages = []

        # Load settings dynamically from cache (zero DB latency on hot path)
        cached_cfg = await get_cached_system_config()
        agent_name = cached_cfg.get("agent_name", "Tara")
        system_prompt = cached_cfg.get("system_prompt", SYSTEM_PROMPT_TEXT)
        ai_enabled = cached_cfg.get("ai_enabled", True)

        # Handle global AI toggle bypass
        if not ai_enabled:
            from app.tools import escalate_to_human_advisor
            await escalate_to_human_advisor.ainvoke({"phone": clean_phone, "reason": "AI support globally disabled by Administrator Settings."})
            return {
                "response": f"Hello! I am transferring you directly to a human support advisor right away. They will reply to you here shortly! 📱",
                "tool_logs": ["escalate_to_human_advisor"]
            }

        # 1. Zero-Cost Fast-Path Check (Saves 100% LLM tokens on deterministic queries)
        from app.cache import check_fast_path
        fast_res = await check_fast_path(clean_phone, user_text)
        if fast_res is not None:
            logger.info(f"Resolved via Zero-Cost Fast Path for {clean_phone} (Tokens saved: {fast_res.get('tokens_saved', 0)})")
            clean_fast_resp = sanitize_whatsapp_message(fast_res.get("response", ""))
            return {
                "response": clean_fast_resp,
                "tool_logs": fast_res.get("tool_logs", [])
            }

        config = {"configurable": {"thread_id": clean_phone}}
        contextualized_input = f"[Customer Phone: {clean_phone}]\nUser message: {user_text}"
        user_msg = HumanMessage(content=contextualized_input)

        try:
            # Check existing thread state in checkpointer
            existing_state = await self.graph.aget_state(config)

            initial_input: Dict[str, Any] = {
                "phone": clean_phone,
                "system_prompt": system_prompt,
                "tool_logs": []
            }

            # If thread is new in memory and historical messages exist, populate them
            if (not existing_state or not existing_state.values.get("messages")) and chat_history_messages:
                history_objs: List[BaseMessage] = [SystemMessage(content=system_prompt)]
                for msg in chat_history_messages[-6:]:
                    if msg.get("sender") == "user":
                        history_objs.append(HumanMessage(content=msg.get("body", "")))
                    elif msg.get("sender") == "assistant":
                        history_objs.append(AIMessage(content=msg.get("body", "")))
                history_objs.append(user_msg)
                initial_input["messages"] = history_objs
            else:
                initial_input["messages"] = [user_msg]

            try:
                final_state = await asyncio.wait_for(
                    self.graph.ainvoke(initial_input, config),
                    timeout=35.0
                )
            except (asyncio.TimeoutError, Exception) as e:
                logger.warning(f"Sub-second guard triggered or LLM exception ({e}). Immediate fallback to Smart Advisor Engine.")
                mock_res = await self._mock_ai_response(clean_phone, user_text)
                try:
                    from app.cache import cache_query_response, _normalize_key
                    cache_query_response(_normalize_key(user_text), mock_res)
                except Exception:
                    pass
                return mock_res

            # Extract the last assistant response
            final_messages = final_state.get("messages", [])
            response_text = ""
            for m in reversed(final_messages):
                if isinstance(m, AIMessage) and m.content:
                    response_text = str(m.content)
                    break

            if not response_text:
                response_text = "I'm checking those details for you. Let me connect you directly to an admissions advisor."

            response_text = sanitize_whatsapp_message(response_text)

            tool_logs = list(dict.fromkeys(final_state.get("tool_logs", [])))
            result_dict = {
                "response": response_text,
                "tool_logs": tool_logs
            }
            try:
                from app.cache import cache_query_response, _normalize_key
                cache_query_response(_normalize_key(user_text), result_dict)
            except Exception:
                pass
            return result_dict
        except Exception as e:
            logger.error(f"Error in LangGraph execution: {e}")
            return await self._mock_ai_response(clean_phone, user_text)

    async def _mock_ai_response(self, phone: str, text: str) -> Dict[str, Any]:
        """Wrapper ensuring every mock engine response is strictly sanitized with zero asterisks."""
        res = await self._raw_mock_ai_response(phone, text)
        if isinstance(res, dict) and "response" in res and isinstance(res["response"], str):
            res["response"] = sanitize_whatsapp_message(res["response"])
        return res

    async def _raw_mock_ai_response(self, phone: str, text: str) -> Dict[str, Any]:
        actual_text = text.split("User message:")[-1].strip() if "User message:" in text else text
        lower_text = actual_text.lower().strip()

        # Structured course catalogue tracks
        CATALOG_TRACKS = [
            {
                "num": 1,
                "badge": "1️⃣",
                "title": "Data Analytics & BI Accelerator",
                "duration": "10 Weeks",
                "level": "Beginner-Intermediate",
                "fee": "₦100,000 / month",
                "outcomes": "Data Analyst, BI Specialist, Insights Reporter",
                "highlights": "Foundational data workflows, cleaning, advanced Excel, SQL queries, interactive dashboards, and business insights.",
                "prereq": "None. 100% beginner friendly, zero coding background required."
            },
            {
                "num": 2,
                "badge": "2️⃣",
                "title": "Excel for Data Analysis & Business Modeling",
                "duration": "6-8 Weeks",
                "level": "Beginner-Advanced",
                "fee": "₦100,000 / month",
                "outcomes": "Excel Analyst, Reporting Specialist, Financial Modeler",
                "highlights": "Master Excel formulas, tables, PivotTables, charts, Power Query, automated reporting, and KPI dashboards.",
                "prereq": "Complete beginners welcome."
            },
            {
                "num": 3,
                "badge": "3️⃣",
                "title": "SQL & Enterprise Database Analytics",
                "duration": "6-8 Weeks",
                "level": "Beginner-Advanced",
                "fee": "₦100,000 / month",
                "outcomes": "SQL Data Analyst, Database Specialist, Data Engineer",
                "highlights": "Learn SELECT, filtering, joins, aggregations, subqueries, CTEs, window functions, and database performance.",
                "prereq": "Beginner friendly. Basic computer literacy."
            },
            {
                "num": 4,
                "badge": "4️⃣",
                "title": "Power BI & Business Intelligence",
                "duration": "6-8 Weeks",
                "level": "Beginner-Advanced",
                "fee": "₦100,000 / month",
                "outcomes": "Power BI Developer, BI Consultant, Dashboard Designer",
                "highlights": "Master Power Query, dimensional modeling, DAX measures, KPI design, drill-through reports, and storytelling.",
                "prereq": "Basic data understanding recommended."
            },
            {
                "num": 5,
                "badge": "5️⃣",
                "title": "Applied Python for Data Analysis & AI",
                "duration": "6-8 Weeks",
                "level": "Beginner-Intermediate",
                "fee": "₦100,000 / month",
                "outcomes": "Python Analyst, Junior Data Scientist, Automation Specialist",
                "highlights": "Python fundamentals, Jupyter, NumPy, Pandas, data cleaning, EDA, visualization, automation, and predictive modeling.",
                "prereq": "Basic computer skills. No prior programming needed."
            },
            {
                "num": 6,
                "badge": "6️⃣",
                "title": "Explore Other Courses & Specialized Tracks",
                "duration": "6-20 Weeks",
                "level": "Beginner to Advanced",
                "fee": "₦100,000 / month",
                "outcomes": "Data Scientist, ML Engineer, Business Analyst, Financial Analyst, HR Analyst, etc.",
                "highlights": "Data Science with Python, Machine Learning, Business Analysis, Financial Analytics, Marketing Analytics, HR Analytics, Data Governance & Quality, etc.",
                "prereq": "Tracks available for all backgrounds from complete beginners to advanced."
            }
        ]

        def render_catalog_outline():
            reply = (
                "🎓 *TekTutors Practical Tech Pathways (1-on-1 Mentorship):*\n"
                "🚀 *Fast-track into high-demand data & AI careers with real industry projects!*\n\n"
            )
            for t in CATALOG_TRACKS:
                reply += (
                    f"{t['badge']} *{t['title']}*\n"
                    f"   ⏱️ Duration: {t['duration']} | Level: {t['level']}\n"
                    f"   💵 Tuition: {t['fee']} (Dedicated private mentor)\n"
                    f"   🎯 Target Outcomes: {t['outcomes']}\n\n"
                )
            reply += (
                "🎁 *Special Fast-Action Perk:* Enroll this week to claim a *Free 1-on-1 CV Optimization & LinkedIn Audit* (valued at ₦35,000)!\n\n"
                "👉 *Please reply with the number of your choice (1-6) OR type the name of the course you'd like to explore!*"
            )
            return reply

        import re
        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', actual_text)
        extracted_email = email_match.group(0) if email_match else None
        if extracted_email and "tektutors.com.ng" in extracted_email.lower():
            extracted_email = None
        is_curriculum_req = any(w in lower_text for w in ["curriculum", "curriclum", "syllabus", "brochure", "outline", "send curriculum", "course outline"])

        # 1. Curriculum / Syllabus requests (e.g. "send curriculum to my email: name@example.com")
        if is_curriculum_req:
            course_title = "Machine Learning with Python"
            if "data analytic" in lower_text:
                course_title = "Data Analytics"
            elif "power bi" in lower_text or "powerbi" in lower_text or "bi" in lower_text:
                course_title = "Power BI Data Analytics"
            elif "sql" in lower_text or "database" in lower_text:
                course_title = "SQL for Data Analysis"
            elif "excel" in lower_text:
                course_title = "Excel for Data Analysis"

            if extracted_email:
                await qualify_and_capture_lead.ainvoke({
                    "phone": phone,
                    "email": extracted_email,
                    "course_interest": course_title,
                    "notes": f"Requested {course_title} curriculum to {extracted_email}"
                })
                reply = (
                    f"📧 *Curriculum Sent to Your Inbox!*\n\n"
                    f"I've noted down your email (**{extracted_email}**), and our admissions team is sending the full, detailed *{course_title}* curriculum and syllabus directly to your inbox! 🚀\n\n"
                    f"📚 *Here is an immediate overview of what you will master:*\n"
                    f"• *Core Foundations:* Practical tools, data wrangling, and industry workflows.\n"
                    f"• *Hands-On Applied Modules:* Live mentored exercises, real-world case studies, and code walkthroughs.\n"
                    f"• *Capstone Portfolio Projects:* 3 employer-ready portfolio projects built using live datasets.\n"
                    f"• *Personalized 1-on-1 Mentorship:* Dedicated weekly live sessions with an industry expert.\n\n"
                    f"⏱️ *Duration:* Flexible month-to-month learning (₦100,000 / month)\n\n"
                    f"👉 *Ready to lock in your mentorship slot?*\n"
                    f"You can register and make payment directly here: https://tektutors.com.ng/registration\n\n"
                    f"Would you like to schedule a quick 15-minute discovery call with our lead mentor?"
                )
                return {"response": reply, "tool_logs": ["qualify_and_capture_lead", "search_tektutors_courses"]}
            else:
                reply = (
                    f"📚 *TekTutors Practical Curriculum & Syllabus Breakdown ({course_title})*\n\n"
                    "All TekTutors pathways are 100% practical, project-based, and taught through live 1-on-1 mentorship. Here is our core syllabus architecture:\n\n"
                    "🔹 *Module 1: Foundations & Business Metrics* — Problem scoping, data collection, and diagnostic analytics.\n"
                    "🔹 *Module 2: Data Wrangling & Database Mastery* — Advanced Excel (Power Query, Dynamic Arrays) + Relational SQL (Joins, Window Functions, Subqueries).\n"
                    "🔹 *Module 3: Business Intelligence & Dashboards* — Power BI data modeling, DAX measures, and interactive executive reporting.\n"
                    "🔹 *Module 4: Advanced Analytics & AI Automation* — Python programming, Pandas data analysis, EDA, and predictive modeling.\n"
                    "🔹 *Module 5: Capstone Projects & Career Portfolio* — 3 real-world portfolio projects built to impress hiring managers.\n\n"
                    "📧 *Want the complete week-by-week PDF brochure?*\n"
                    "👉 Reply with your *Email Address* (e.g., name@gmail.com) and our admissions team will send the full syllabus straight to your inbox!\n\n"
                    "Or complete your registration directly here:\n🔗 https://tektutors.com.ng/registration"
                )
                return {"response": reply, "tool_logs": ["search_tektutors_courses", "qualify_and_capture_lead"]}

        # 2. Capture Lead with clean email or name
        if extracted_email or "my name is" in lower_text:
            name = None
            if "my name is" in lower_text:
                name = actual_text.lower().split("my name is")[-1].strip().title()
            await qualify_and_capture_lead.ainvoke({
                "phone": phone,
                "name": name,
                "email": extracted_email,
                "course_interest": "Data Analytics & BI Accelerator",
                "notes": "Captured via automated chat"
            })
            if extracted_email:
                try:
                    from app.email_service import dispatch_engagement_email
                    await dispatch_engagement_email(
                        trigger_event="syllabus",
                        course_name="Data Analytics & BI Accelerator",
                        recipient_email=extracted_email,
                        recipient_name=name or "Student"
                    )
                except Exception as err:
                    logger.error(f"Error dispatching syllabus email in mock fallback: {err}")

                reply = (
                    f"📧 *Curriculum Sent to Your Inbox!*\n\n"
                    f"I have dispatched the complete week-by-week syllabus directly to your inbox at: *{extracted_email}*! 🚀\n\n"
                    f"📚 *Quick Overview of What You Will Master:*\n"
                    f"• *Module 1:* Foundations & Diagnostic Business Scoping\n"
                    f"• *Module 2:* Practical Data Wrangling (Advanced Excel + Relational SQL)\n"
                    f"• *Module 3:* Business Intelligence & Executive Dashboards (Power BI)\n"
                    f"• *Module 4:* Python Data Analysis, EDA & Automation\n"
                    f"• *Module 5:* 3 End-to-End Employer-Ready Capstone Projects\n\n"
                    f"💵 *Tuition:* ₦100,000 / month (or ₦90,000 upfront, saving ₦10,000) with dedicated private 1-on-1 mentorship.\n\n"
                    f"👉 Secure your slot & assigned mentor here: https://tektutors.com.ng/registration\n\n"
                    f"Have you worked with any data tools before, or are you starting completely fresh?"
                )
            else:
                reply = f"Awesome! Nice to meet you, {name}! How can I help you with TekTutors courses today?"
            return {"response": reply, "tool_logs": ["qualify_and_capture_lead"]}

        # 3. Check if user selected by number (e.g. "1", "2", "3", "4", "5", "option 1", "track 1")
        number_map = {
            "1": 1, "one": 1, "1️⃣": 1, "first": 1,
            "2": 2, "two": 2, "2️⃣": 2, "second": 2,
            "3": 3, "three": 3, "3️⃣": 3, "third": 3,
            "4": 4, "four": 4, "4️⃣": 4, "fourth": 4,
            "5": 5, "five": 5, "5️⃣": 5, "fifth": 5,
            "6": 6, "six": 6, "6️⃣": 6, "sixth": 6,
        }
        
        selected_track = None
        for k, num in number_map.items():
            if lower_text == k or f"track {k}" in lower_text or f"option {k}" in lower_text or f"course {k}" in lower_text or f"#{k}" in lower_text or f"number {k}" in lower_text or lower_text.startswith(f"{k} ") or lower_text.startswith(f"{k}.") or lower_text.startswith(f"{k}-"):
                selected_track = next((t for t in CATALOG_TRACKS if t["num"] == num), None)
                break

        # Check if user typed the name of a course wanted
        if not selected_track:
            if "data analytic" in lower_text or "bi accelerator" in lower_text:
                selected_track = CATALOG_TRACKS[0]
            elif "excel" in lower_text and "power query" not in lower_text:
                selected_track = CATALOG_TRACKS[1]
            elif "sql" in lower_text or "database" in lower_text:
                selected_track = CATALOG_TRACKS[2]
            elif "power bi" in lower_text or "powerbi" in lower_text or "business intelligence" in lower_text:
                selected_track = CATALOG_TRACKS[3]
            elif "applied python" in lower_text:
                selected_track = CATALOG_TRACKS[4]
            elif any(w in lower_text for w in ["other course", "others", "more course", "all course"]):
                selected_track = CATALOG_TRACKS[5]

        # If a specific track was chosen (by number OR by typed name):
        if selected_track:
            if selected_track["num"] == 6:
                reply = (
                    "🎓 *Other Available Courses & Specialized Tracks at TekTutors:*\n\n"
                    "All programs feature personalized 1-on-1 industry mentorship, practical hands-on projects, and flexible month-to-month tuition (₦100,000/month):\n\n"
                    "🤖 *Advanced AI & Data Science:*\n"
                    "• *Data Science with Python* (20 wks) — Statistics, EDA, feature engineering, machine learning pipelines\n"
                    "• *Machine Learning with Python* (16 wks) — Regression, classification, clustering & model deployment\n"
                    "• *Predictive Analytics* (12 wks) — Business forecasting, predictive modelling & risk assessment\n"
                    "• *Statistical Analysis for Data Analytics* (10 wks) — Distributions, hypothesis testing & inferential stats\n"
                    "• *R for Data Analysis* (6-8 wks) — RStudio, tidyverse, data wrangling & statistical reporting\n"
                    "• *Time Series Analysis* (10 wks) — Trend decomposition, seasonality & forecasting\n\n"
                    "💼 *Business, Finance & Domain Analytics:*\n"
                    "• *Business Analysis* (10 wks) — Stakeholder management, requirements gathering & process mapping\n"
                    "• *Business Analytics* (12 wks) — KPI frameworks, diagnostic analytics & executive decision support\n"
                    "• *Financial Data Analytics* (8 wks) — Revenue modeling, profitability & financial KPI dashboards\n"
                    "• *Marketing Analytics* (8 wks) — Funnel conversion, customer segmentation & attribution\n"
                    "• *HR / People Analytics* (8 wks) — Workforce metrics, recruitment pipelines & retention dashboards\n"
                    "• *Operations Analytics* (8 wks) — Operational KPIs, supply chain & process optimization\n"
                    "• *Data Governance & Quality* (10 wks) — Data validation, metadata, standards & compliance\n"
                    "• *Advanced Excel & Power Query* (6 wks) — Advanced formulas, automated data transformation\n\n"
                    "👉 *Which of these courses interests you?*\n"
                    "Reply with the course title (or your target career goal) to get the full curriculum details, or secure your slot directly:\n"
                    "🔗 https://tektutors.com.ng/registration"
                )
                return {"response": reply, "tool_logs": ["search_tektutors_courses"]}

            reply = (
                f"🎯 *Excellent choice! Track {selected_track['num']}: {selected_track['title']}*\n\n"
                f"This program is 100% practical, project-driven, and delivered via personalized 1-on-1 mentorship with an experienced industry mentor.\n\n"
                f"📚 *What you will master:*\n• {selected_track['highlights']}\n\n"
                f"⏱️ *Duration:* {selected_track['duration']} ({selected_track['level']})\n"
                f"💵 *Tuition:* {selected_track['fee']} (Flexible month-to-month billing)\n"
                f"🎯 *Career Outcomes:* {selected_track['outcomes']}\n"
                f"📌 *Prerequisites:* {selected_track['prereq']}\n\n"
                f"To personalize your learning roadmap:\n"
                f"*Have you worked with data tools before, or are you starting completely fresh?* "
                f"(You can also share your email to receive the detailed syllabus or book a free discovery call!)"
            )
            return {"response": reply, "tool_logs": ["search_tektutors_courses"]}

        # Check if user asked about a specific specialized course (e.g. Machine Learning, Data Science, Business Analysis, etc.)
        elif any(kw in lower_text for kw in [
            "machine learning", "data science", "predictive analytic", "business analysis",
            "business analytic", "financial analytic", "marketing analytic", "hr analytic",
            "people analytic", "operations analytic", "time series", "deep learning", "nlp", "r for data"
        ]):
            try:
                courses_raw = await search_tektutors_courses.ainvoke({"query": actual_text})
                found_courses = json.loads(courses_raw)
                if found_courses and isinstance(found_courses, list):
                    top_c = found_courses[0]
                    prereq_q = "Do you already have some experience with Python and basic math/statistics, or are you starting from scratch?" if "machine learning" in lower_text or "data science" in lower_text else "Have you worked with data tools before, or are you starting fresh?"
                    reply = (
                        f"🎯 *Yes, absolutely! {top_c['title']}*\n\n"
                        f"This program is 100% practical, project-driven, and delivered via dedicated **private 1-on-1 mentorship** with an experienced industry practitioner.\n\n"
                        f"📚 *What you will master:*\n• {top_c.get('syllabus') or top_c.get('description', '')}\n\n"
                        f"⏱️ *Duration:* {top_c['duration']}\n"
                        f"💵 *Tuition:* {top_c['price_monthly']} (or pay upfront for just **₦90,000** with our 10% discount, saving ₦10,000!)\n"
                        f"🎯 *Career Outcomes:* {top_c['career_outcomes']}\n"
                        f"📌 *Prerequisites:* {top_c['prerequisites']}\n\n"
                        f"To personalize your learning roadmap:\n"
                        f"👉 *{prereq_q}*\n\n"
                        f"*(Reply with your **Email Address** to receive the complete syllabus PDF, or schedule a free 15-minute 1-on-1 discovery call with an Admissions Advisor!)*\n"
                        f"🔗 https://tektutors.com.ng/registration"
                    )
                    return {"response": reply, "tool_logs": ["search_tektutors_courses"]}
            except Exception as e:
                logger.warning(f"Error querying courses in mock fallback: {e}")
        elif any(w in lower_text for w in [
            "book a call", "schedule a call", "book 1-on-1", "1-on-1 call", "discovery call",
            "admissions advisor call", "book me a call", "schedule an advisor call"
        ]) or ("book" in lower_text and "call" in lower_text):
            await qualify_and_capture_lead.ainvoke({
                "phone": phone,
                "notes": f"Advisor discovery call requested: {actual_text}"
            })
            reply = (
                "📅 *Book Your 1-on-1 Admissions Discovery Call*\n\n"
                "I'd love to set up your personalized 15-minute consultation with a Senior TekTutors Admissions Advisor! 🎯\n\n"
                "During this private call, we will:\n"
                "• Review your current background & career aspirations\n"
                "• Recommend the optimal learning track for you\n"
                "• Walk you through our live 1-on-1 industry mentor format & practical projects\n"
                "• Answer any questions about our flexible schedule and tuition\n\n"
                "👉 *To lock in your call slot, please reply with:*\n"
                "1. *Your Full Name*\n"
                "2. *Preferred Time & Day* (e.g., Tomorrow at 2:00 PM)\n"
                "3. *Course Track of interest* (or reply 'Not sure yet')\n\n"
                "You can also secure your enrollment directly anytime at:\n🔗 https://tektutors.com.ng/registration"
            )
            return {"response": reply, "tool_logs": ["qualify_and_capture_lead", "schedule_advisor_call"]}

        # Payment Plans and Month-to-Month Tuition
        elif any(w in lower_text for w in [
            "payment plan", "payment plans", "month-to-month", "installment plan",
            "tuition plan", "tuition options", "view payment plans"
        ]):
            await qualify_and_capture_lead.ainvoke({
                "phone": phone,
                "notes": f"Payment plans inquiry: {actual_text}"
            })
            reply = (
                "💳 *TekTutors Flexible Tuition & Payment Plans*\n\n"
                "We believe quality tech training should be accessible without financial pressure. Here are our flexible options:\n\n"
                "1️⃣ *Flexible Month-to-Month Plan (Most Popular):*\n"
                "• *₦100,000 / month* — flexible month-to-month billing (cancel anytime)\n"
                "• Zero long-term debt or huge upfront lump sum\n"
                "• Includes weekly 1-on-1 private mentorship with an industry practitioner\n"
                "• Progress at your own pace\n\n"
                "2️⃣ *Upfront Full-Payment Plan:*\n"
                "• Receive an exclusive *10% tuition discount* when you pay upfront — pay just *₦90,000* instead of ₦100,000 (save ₦10,000!)\n"
                "• Immediate onboarding and priority mentor allocation\n\n"
                "👉 *Ready to get started? Enroll securely on our official portal:*\n"
                "🔗 https://tektutors.com.ng/registration\n\n"
                "Which course track would you like to enroll in? (Reply with a track number 1-6 or course name!)"
            )
            return {"response": reply, "tool_logs": ["get_course_faq_answer", "qualify_and_capture_lead"]}

        # Tuition Discounts, Scholarships & Promo Codes
        elif any(w in lower_text for w in [
            "discount", "scholarship", "promo", "voucher", "coupon", "financial aid",
            "cheaper", "reduce fee", "price slash"
        ]):
            reply = (
                "🎁 *Exclusive TekTutors Tuition Discounts & Savings!*\n\n"
                "We want to ensure financial constraints never hold you back from acquiring high-income tech skills. Here are our active offers:\n\n"
                "1️⃣ *10% Full-Payment Discount:*\n"
                "Pay your course tuition upfront and instantly save *10%* — pay just *₦90,000* instead of ₦100,000 (save ₦10,000)!\n\n"
                "2️⃣ *Fast-Action Voucher (Code: TEK10):*\n"
                "Enter promo code *TEK10* on our checkout portal to claim a special tuition discount.\n\n"
                "3️⃣ *Free Bonuses Included with Every Track (Valued at ₦85,000):*\n"
                "• Free 1-on-1 CV Optimization & LinkedIn Audit (Worth ₦35,000)\n"
                "• 3 Employer-Ready Capstone Portfolio Reviews with Senior Tech Leads\n"
                "• Flexible ₦100,000/month pay-as-you-learn plan with zero debt\n\n"
                "👉 *Claim your discount and enroll securely online:*\n"
                "🔗 https://tektutors.com.ng/registration\n\n"
                "Which skill track would you like to enroll in? (Reply with a track number 1-6 or course name!)"
            )
            return {"response": reply, "tool_logs": ["check_scholarship_and_discounts"]}

        # Human escalation (explicit requests to speak to human or dispute/complaints)
        elif any(w in lower_text for w in ["speak to human", "talk to human", "human agent", "real person", "representative", "manager", "supervisor", "fraud", "scam"]):
            await escalate_to_human_advisor.ainvoke({"phone": phone, "reason": "Customer requested human escalation"})
            reply = "I am connecting you right away with a Senior TekTutors Admissions Advisor! They will join this chat shortly. 📱"
            return {"response": reply, "tool_logs": ["escalate_to_human_advisor"]}

        # Registration and Payment Redirection
        elif any(w in lower_text for w in [
            "register", "registration", "how to pay", "where to pay", "payment link",
            "pay link", "enroll link", "registration link", "sign up", "signup",
            "how do i pay", "make payment", "ready to pay", "enrollment link", "enroll now", "register now"
        ]):
            reply = (
                "🚀 *Ready to start your 1-on-1 practical tech training with TekTutors?*\n\n"
                "You can complete your course registration and submit your payment securely online right here:\n\n"
                "👉 *Official Registration & Payment Portal:*\n"
                "https://tektutors.com.ng/registration\n\n"
                "💳 *Tuition Details:*\n"
                "• Standard fee: ₦100,000 / month\n"
                "• Live 1-on-1 expert mentor guidance\n"
                "• Real-world capstone portfolio projects\n\n"
                "Once you complete your registration at the link above, our admissions team and your mentor will reach out immediately to finalize your schedule and onboarding! 🎓\n\n"
                "Do you have any questions before completing your registration?"
            )
            return {"response": reply, "tool_logs": ["generate_enrollment_checkout"]}

        # Career Background & Transition Advisory (Banking, Accounting, Finance, Non-Tech, HR, Healthcare)
        elif any(w in lower_text for w in [
            "banker", "banking", "accountant", "accounting", "finance", "financial",
            "audit", "economics", "non-tech", "no coding", "zero coding", "no experience",
            "beginner", "can i cope", "background", "transition", "switch to tech"
        ]):
            is_finance = any(w in lower_text for w in ["bank", "account", "finance", "audit", "econ"])
            if is_finance:
                reply = (
                    "📊 *Perfect fit for Banking & Financial Professionals!*\n\n"
                    "Many of our most successful learners come from accounting, banking, and audit backgrounds. For your career path, we highly recommend:\n\n"
                    "1️⃣ *Data Analytics & BI Accelerator* (Track 1) — Master advanced Excel, SQL, and Power BI to automate financial modeling, reconciliations, and executive dashboards.\n"
                    "2️⃣ *Financial Analytics* (Track 6) — Focus on financial KPIs, forecasting models, variance analysis, and balance sheet analytics.\n\n"
                    "💡 *Good news:* All training is delivered **live 1-on-1 with an industry mentor** who adapts directly to your financial domain experience.\n\n"
                    "Would you like to start with Data Analytics or Financial Analytics?"
                )
            else:
                reply = (
                    "🌟 *You can 100% succeed with TekTutors!*\n\n"
                    "Over 70% of our learners begin with **zero coding or technical background**. Here is why our model works where others fail:\n\n"
                    "• **Private 1-on-1 Mentorship:** You never get lost in a crowded lecture hall. Your mentor moves at your exact pace.\n"
                    "• **No Jargon, Hands-On Projects:** We start from the ground up with visual tools (Excel & Power BI) before touching code.\n"
                    "• **Employer Portfolio:** You build 3 real-world portfolio capstones you can showcase to employers with confidence.\n\n"
                    "Which career track would you like to explore first? (Track 1: Data Analytics, Track 2: Excel, or Track 4: Power BI?)"
                )
            return {"response": reply, "tool_logs": ["search_tektutors_courses", "qualify_and_capture_lead"]}

        # Laptop & System Requirements
        elif any(w in lower_text for w in ["laptop", "computer", "system requirement", "pc", "mac", "ram", "specs"]):
            reply = (
                "💻 *Laptop & System Requirements for TekTutors Training:*\n\n"
                "You only need a standard personal laptop to get started:\n"
                "• **Operating System:** Windows 10/11, macOS, or Linux\n"
                "• **Memory (RAM):** 4GB minimum (8GB recommended for smooth multitasking)\n"
                "• **Internet:** Reliable connection for live 1-on-1 video mentoring sessions\n\n"
                "💡 *All software is free:* Tools like Power BI Desktop, VS Code, Python/Jupyter, and MySQL are completely free. Your 1-on-1 mentor will guide you step-by-step through installing everything in session 1!\n\n"
                "Ready to begin? Complete your registration online:\n🔗 https://tektutors.com.ng/registration"
            )
            return {"response": reply, "tool_logs": ["get_course_faq_answer"]}

        # Schedule, Weekend Classes & Working Professionals
        elif any(w in lower_text for w in ["schedule", "weekend", "working professional", "time of class", "when are classes", "hours", "miss a class"]):
            reply = (
                "⏰ *Flexible Schedule for Busy Working Professionals:*\n\n"
                "Because your training is **live 1-on-1 with a private mentor**, your schedule is 100% tailored to you!\n\n"
                "• **Weekend Options:** Saturday and Sunday sessions available (morning, afternoon, or evening).\n"
                "• **Weekday Evenings:** After-work sessions available (e.g. 7:00 PM - 9:00 PM).\n"
                "• **Pace:** Typically 3-5 hours of dedicated practice per week.\n"
                "• **Never Fall Behind:** If an emergency comes up, simply reschedule with your mentor in advance.\n\n"
                "Would you prefer weekend sessions or weekday evening sessions?"
            )
            return {"response": reply, "tool_logs": ["get_course_faq_answer"]}

        # International & Foreign Currency Payments (USD, GBP, EUR)
        elif any(w in lower_text for w in ["dollar", "usd", "gbp", "pounds", "foreign currency", "outside nigeria", "international student", "pay from abroad"]):
            reply = (
                "🌍 *International Students & Foreign Currency Payments:*\n\n"
                "Yes, we welcome learners globally! Our training is 100% online live via interactive screen sharing.\n\n"
                "• **Tuition Rate:** Approximately **$75 - $80 USD / month** (equivalent to ₦100,000 NGN/month).\n"
                "• **Payment Methods:** You can pay with any international Mastercard, Visa, or debit card on our secure portal.\n"
                "• **Billing:** Month-to-month flexible billing with zero long-term commitments.\n\n"
                "👉 *Register securely online:* https://tektutors.com.ng/registration\n\n"
                "Which skill track would you like to enroll in?"
            )
            return {"response": reply, "tool_logs": ["get_course_faq_answer"]}

        # Location, Physical Address, Office, In-Person vs Online
        elif any(w in lower_text for w in [
            "physical address", "office address", "physical office", "physical location",
            "physical center", "physical class", "physical branch",
            "physical", "address", "office", "where are you", "where is your office", "where are you located",
            "where is your location", "what is your address", "located", "in-person", "in person",
            "walk in", "walk-in", "branch", "headquarters", "can i visit", "come to your office",
            "offline class", "office in lagos", "office in abuja"
        ]):
            reply = (
                "📍 *TekTutors Training Format & Location:*\n\n"
                "TekTutors is a **100% live online technology academy** serving learners across Nigeria and internationally! 🌍\n\n"
                "• **No Commute / No Physical Walk-ins:** We do not operate crowded physical classrooms. All training sessions, portfolio reviews, and code walkthroughs are conducted live 1-on-1 with your dedicated mentor over interactive video and screen sharing.\n"
                "• **Learn From Home or Office:** You enjoy flexible, personalized scheduling (weekday evenings or weekends) without the stress of daily traffic commute.\n"
                "• **Corporate Headquarters & Administrative Office:** Our administrative hub is based in **Lagos, Nigeria**.\n"
                "• **Administrative & Admissions Inquiries:** You can reach our team at **info@tektutors.com.ng** or call/WhatsApp **+2348063584517**.\n\n"
                "👉 *Official Portal & Registration:* https://tektutors.com.ng/registration\n\n"
                "Would you like to schedule a 1-on-1 discovery call with an Admissions Advisor or explore our courses?"
            )
            return {"response": reply, "tool_logs": ["get_course_faq_answer"]}

        # FAQs (installments, certificates, jobs, format)
        elif any(w in lower_text for w in [
            "installment", "pay", "discount", "certificate", "job", "career support",
            "live", "recorded", "remote", "online", "prerequisite"
        ]):
            faqs_str = await get_course_faq_answer.ainvoke({"question_or_topic": actual_text})
            try:
                faqs = json.loads(faqs_str)
            except Exception:
                faqs = []

            # Check if top FAQ genuinely matches the query tokens
            valid_faq = None
            if isinstance(faqs, list) and faqs:
                query_tokens = set(re.findall(r'\b\w{3,}\b', lower_text))
                for f in faqs:
                    f_q_tokens = set(re.findall(r'\b\w{3,}\b', (f.get("question") or "").lower()))
                    # Check token overlap between user query and FAQ question
                    if query_tokens & f_q_tokens:
                        valid_faq = f
                        break

            if valid_faq:
                reply = (
                    f"💡 *TekTutors Insights:*\n\n{valid_faq['answer']}\n\n"
                    f"Would you like to explore our training tracks or schedule a 1-on-1 advisor call?"
                )
                return {"response": reply, "tool_logs": ["get_course_faq_answer"]}
            else:
                reply = (
                    "💡 *TekTutors Key Essentials:*\n\n"
                    "• **Format:** 100% live online worldwide with dedicated 1-on-1 industry mentors.\n"
                    "• **Tuition:** Flexible month-to-month billing at ₦100,000/month (or save 10% on full upfront payment).\n"
                    "• **Certification & Portfolio:** Accredited completion certificate and 3 capstone portfolio projects.\n\n"
                    "👉 Explore courses & register: https://tektutors.com.ng/registration\n\n"
                    "Would you like to speak directly with an Admissions Advisor?"
                )
                return {"response": reply, "tool_logs": ["get_course_faq_answer"]}

        # General greetings
        elif any(w == lower_text or lower_text.startswith(w + " ") for w in ["hi", "hello", "hey", "good morning", "good afternoon", "good evening", "greetings", "start"]):
            reply = "Hello! 👋 Welcome to TekTutors — practical 1-on-1 technology training with expert mentors.\n\n" + render_catalog_outline()
            return {"response": reply, "tool_logs": ["search_tektutors_courses"]}

        # General course / track inquiries
        elif any(w in lower_text for w in ["course", "track", "program", "catalogue", "catalog", "training", "what do you offer"]):
            reply = render_catalog_outline()
            return {"response": reply, "tool_logs": ["search_tektutors_courses"]}

        # Unrecognized / complex edge cases -> Helpful consultative answer with invitation to chat with advisor
        else:
            reply = (
                "Hello! I am Tara, Admissions Advisor at TekTutors Academy. 🎓\n\n"
                "We provide **live 1-on-1 practical tech training** with experienced industry mentors in Data Analytics, Excel, SQL, Power BI, Python, and Machine Learning.\n\n"
                "• **Tuition:** ₦100,000 / month (flexible month-to-month billing)\n"
                "• **Schedule:** Personalized weekend or evening sessions\n"
                "• **Portal:** https://tektutors.com.ng/registration\n\n"
                "How can I best assist your tech career goals today? You can ask about our courses, schedule a 1-on-1 discovery call, or view our curriculum!"
            )
            return {"response": reply, "tool_logs": ["search_tektutors_courses"]}


agent_manager = TekTutorsAgentManager()
