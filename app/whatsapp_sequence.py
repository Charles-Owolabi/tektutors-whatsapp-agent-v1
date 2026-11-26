import os
import sys
import logging
import json
import re
import datetime
import asyncio
from typing import Dict, Any, List, Optional
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Lead, Conversation, Message, WhatsAppLog, ScheduledWhatsAppMessage
from app.whatsapp import whatsapp_client

def strip_asterisks(text: str) -> str:
    return re.sub(r"\*", "", text) if text else ""

logger = logging.getLogger(__name__)


def clean_phone_number(raw_phone: str) -> str:
    """Sanitize phone number to international E.164 without plus sign for WhatsApp Cloud API."""
    if not raw_phone:
        return ""
    digits = re.sub(r"[^\d]", "", raw_phone)
    if digits.startswith("0") and len(digits) == 11:
        digits = "234" + digits[1:]
    elif not digits.startswith("234") and len(digits) == 10:
        digits = "234" + digits
    return digits


def format_whatsapp_cloud_text(text: str) -> str:
    """
    Format and sanitize text strictly according to WhatsApp Cloud API standards:
    1. Single asterisk for bold (*text*), never double (**text**).
    2. Clean unicode bullets (• item), avoiding markdown hyphens or stray asterisks.
    3. Remove raw HTML tags (<p>, <br>, etc.).
    4. Keep within safe message length limits.
    """
    if not text:
        return ""
    # Strip raw HTML tags if any
    cleaned = re.sub(r"<[^>]+>", " ", text)
    # Convert markdown headers (### Header) to bold caps (*HEADER*)
    cleaned = re.sub(r"(?m)^#{1,6}\s*(.*?)$", r"*\1*", cleaned)
    # Convert double or triple asterisks to single asterisks for bold
    cleaned = re.sub(r"\*{2,}([^*\n]+?)\*{2,}", r"*\1*", cleaned)
    # Convert markdown bullets (- item or * item) to clean unicode bullets
    cleaned = re.sub(r"(?m)^\s*[\*\-]\s+", "• ", cleaned)
    # Clean redundant whitespaces
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


COURSE_CATALOG_DATA = {
    "Data Analytics & BI Accelerator": {
        "title": "Data Analytics & BI Accelerator",
        "short_tools": "Excel, SQL, Power BI & Python",
        "topic_highlight": "Data cleaning, Advanced Excel, SQL queries, Power BI dashboards, and storytelling",
        "capstone_sample": "End-to-End Business Performance & Customer Insights Capstone",
        "duration": "10 Weeks (2.5 Months)",
        "career_outcomes": "Data Analyst, Business Intelligence Specialist, Insights Reporter"
    },
    "Applied Python for Data Analysis & AI": {
        "title": "Applied Python for Data Analysis & AI",
        "short_tools": "Python, Pandas, NumPy & Jupyter",
        "topic_highlight": "Python programming syntax, Pandas dataframes, NumPy, and real data workflows",
        "capstone_sample": "Automated Customer Churn Pipeline & Financial Analytics Model",
        "duration": "6-8 Weeks (1.5-2 Months)",
        "career_outcomes": "Python Data Analyst, Junior Data Scientist, Analytics Automation Specialist"
    },
    "SQL & Enterprise Database Analytics": {
        "title": "SQL & Enterprise Database Analytics",
        "short_tools": "PostgreSQL & Database Queries",
        "topic_highlight": "Relational databases, complex joins, subqueries, CTEs, window functions, and query optimization",
        "capstone_sample": "FinTech Database Query Engine & Financial Metrics Reporting System",
        "duration": "6-8 Weeks (1.5-2 Months)",
        "career_outcomes": "Database Analyst, SQL Developer, BI Data Engineer"
    },
    "Power BI & Business Intelligence": {
        "title": "Power BI & Business Intelligence",
        "short_tools": "Power BI Desktop, Power Query & DAX",
        "topic_highlight": "Power Query ETL, star schema data modeling, advanced DAX calculations, and interactive storytelling",
        "capstone_sample": "Enterprise Executive KPI Dashboard & Real-Time Performance Matrix",
        "duration": "6-8 Weeks (1.5-2 Months)",
        "career_outcomes": "Power BI Developer, BI Consultant, Dashboard Designer"
    },
    "Excel for Data Analysis & Business Modeling": {
        "title": "Excel for Data Analysis & Business Modeling",
        "short_tools": "Advanced Excel, Power Query & PivotTables",
        "topic_highlight": "Advanced functions (XLOOKUP), dynamic arrays, Power Query transformations, and executive dashboards",
        "capstone_sample": "Executive Sales & Operations Multi-Department KPI Dashboard",
        "duration": "6-8 Weeks (1.5-2 Months)",
        "career_outcomes": "Financial Analyst, Operations Specialist, Excel Reporting Lead"
    },
    "Machine Learning with Python": {
        "title": "Machine Learning with Python",
        "short_tools": "Python, Scikit-Learn, Pandas & XGBoost",
        "topic_highlight": "Feature engineering, supervised & unsupervised machine learning, model tuning, and deployment with FastAPI",
        "capstone_sample": "Production Customer Lifetime Value & Churn Prediction System",
        "duration": "16 Weeks (3-5 Months)",
        "career_outcomes": "Machine Learning Engineer, Junior AI Engineer, Predictive Analyst"
    },
    "Data Science with Python": {
        "title": "Data Science with Python",
        "short_tools": "Python, Statistics, Pandas & Scikit-Learn",
        "topic_highlight": "Exploratory data analysis, hypothesis testing, predictive modeling, and model evaluation",
        "capstone_sample": "End-to-End Predictive Analytics Pipeline & Production API",
        "duration": "16-20 Weeks (4-6 Months)",
        "career_outcomes": "Data Scientist, Quantitative Analyst, Research Data Specialist"
    },
    "Business Analysis": {
        "title": "Business Analysis",
        "short_tools": "Agile/Scrum, User Stories, BPMN & JIRA",
        "topic_highlight": "Stakeholder elicitation, user stories, process mapping, gap analysis, and BRD documentation",
        "capstone_sample": "Comprehensive Enterprise Business Requirements & Process Re-engineering Portfolio",
        "duration": "10 Weeks (2.5 Months)",
        "career_outcomes": "Business Analyst, Product Owner, Agile Requirements Specialist"
    },
    "Financial Analytics": {
        "title": "Financial Analytics",
        "short_tools": "Financial Modeling, Excel & Power BI",
        "topic_highlight": "3-statement modeling, cash flow forecasting, variance analysis, and executive financial dashboards",
        "capstone_sample": "Corporate Financial Valuation & Rolling Forecast Dashboard",
        "duration": "6-8 Weeks (1.5-2 Months)",
        "career_outcomes": "Financial Analyst, FP&A Specialist, Corporate Finance Associate"
    },
    "HR Analytics": {
        "title": "HR Analytics",
        "short_tools": "People Analytics, Excel & Power BI",
        "topic_highlight": "Headcount modeling, employee turnover analytics, talent acquisition funnels, and workforce planning",
        "capstone_sample": "Corporate Workforce Attrition & Talent Retention Matrix",
        "duration": "6-8 Weeks (1.5-2 Months)",
        "career_outcomes": "People Analytics Specialist, HR Data Analyst, Workforce Planning Consultant"
    },
    "Marketing Analytics": {
        "title": "Marketing Analytics",
        "short_tools": "Funnel Analytics, Power BI & Google Analytics",
        "topic_highlight": "CAC/LTV modeling, multi-touch attribution, customer segmentation, and campaign ROI dashboards",
        "capstone_sample": "Full-Funnel Digital Marketing Optimization & ROI Dashboard",
        "duration": "6-8 Weeks (1.5-2 Months)",
        "career_outcomes": "Marketing Data Analyst, Growth Analytics Lead, Performance Marketing Specialist"
    },
    "Predictive Analytics": {
        "title": "Predictive Analytics",
        "short_tools": "Python, Forecasting Models & Statistical Modeling",
        "topic_highlight": "Business forecasting, predictive modeling, risk scoring, and scenario simulation",
        "capstone_sample": "Enterprise Revenue Forecasting & Customer Risk Prediction Engine",
        "duration": "12 Weeks (3 Months)",
        "career_outcomes": "Predictive Analyst, Forecasting Specialist, Decision Scientist"
    },
    "R for Data Analysis": {
        "title": "R for Data Analysis",
        "short_tools": "RStudio, Tidyverse, ggplot2 & Statistical Reporting",
        "topic_highlight": "Data wrangling in R, statistical modeling, hypothesis testing, and publication-grade visualizations",
        "capstone_sample": "End-to-End Statistical Research & Automated R Markdown Analytics Suite",
        "duration": "6-8 Weeks (1.5-2 Months)",
        "career_outcomes": "Statistical Data Analyst, R Programmer, Quantitative Researcher"
    },
    "Time Series Analysis": {
        "title": "Time Series Analysis",
        "short_tools": "Python, ARIMA, Prophet & Forecasting Pipelines",
        "topic_highlight": "Trend decomposition, seasonality modeling, econometrics, and demand forecasting",
        "capstone_sample": "Multi-Horizon Demand & Financial Time-Series Forecasting System",
        "duration": "10 Weeks (2.5 Months)",
        "career_outcomes": "Forecasting Analyst, Quantitative Modeler, Demand Planner"
    },
    "Operations Analytics": {
        "title": "Operations Analytics",
        "short_tools": "Excel, SQL, Power BI & Supply Chain Metrics",
        "topic_highlight": "Operational KPIs, supply chain optimization, SLA tracking, and process bottleneck analysis",
        "capstone_sample": "End-to-End Supply Chain & Logistics Efficiency Command Dashboard",
        "duration": "8 Weeks (2 Months)",
        "career_outcomes": "Operations Data Analyst, Supply Chain Analyst, Process Improvement Lead"
    },
    "Data Governance & Quality": {
        "title": "Data Governance & Quality",
        "short_tools": "Data Standards, Metadata Management & Compliance",
        "topic_highlight": "Data quality frameworks, lineage, master data management, privacy compliance, and validation",
        "capstone_sample": "Enterprise Data Governance Charter & Automated Quality Audit Framework",
        "duration": "10 Weeks (2.5 Months)",
        "career_outcomes": "Data Governance Specialist, Data Quality Analyst, Data Steward"
    }
}

TRACK_NUMBER_TO_COURSE = {
    "1": "Data Analytics & BI Accelerator",
    "2": "Excel for Data Analysis & Business Modeling",
    "3": "SQL & Enterprise Database Analytics",
    "4": "Power BI & Business Intelligence",
    "5": "Applied Python for Data Analysis & AI",
}


def _match_explicit_course_in_text(text: Optional[str]) -> Optional[str]:
    """
    Return the specific canonical course name ONLY if explicitly mentioned in `text`.
    Ignores multi-track catalog menu dumps so Tara's greeting menu never pollutes detection.
    """
    if not text or not isinstance(text, str):
        return None
    clean = text.strip()
    lower = clean.lower()

    # Ignore full 6-track catalog menu responses from assistant
    if "1️⃣" in clean and "5️⃣" in clean:
        return None
    if "other available courses & specialized tracks" in lower and "advanced ai & data science" in lower:
        return None

    # Check direct numeric track selection by user (e.g. "1", "track 2", "option 4")
    num_m = re.match(r"^\s*(?:track|option|course|number|#)?\s*([1-5])\s*[\.\)]?\s*$", lower)
    if num_m:
        return TRACK_NUMBER_TO_COURSE.get(num_m.group(1))

    if "machine learning" in lower or "machine-learning" in lower or re.search(r"\bml\b", lower):
        return "Machine Learning with Python"
    if "data science" in lower or re.search(r"\bds\b", lower):
        return "Data Science with Python"
    if "predictive analytic" in lower:
        return "Predictive Analytics"
    if "time series" in lower:
        return "Time Series Analysis"
    if "r for data" in lower or re.search(r"\brstudio\b|\btidyverse\b", lower):
        return "R for Data Analysis"
    if "operations analytic" in lower or "supply chain" in lower:
        return "Operations Analytics"
    if "data governance" in lower or "data quality" in lower:
        return "Data Governance & Quality"
    if "power bi" in lower or "powerbi" in lower or re.search(r"\bdax\b", lower):
        return "Power BI & Business Intelligence"
    if "sql" in lower or "postgres" in lower or "database" in lower or "queries" in lower:
        return "SQL & Enterprise Database Analytics"
    if "excel" in lower or "spreadsheet" in lower or "vlookup" in lower or "xlookup" in lower or "pivot" in lower:
        return "Excel for Data Analysis & Business Modeling"
    if "python" in lower or "pandas" in lower or "numpy" in lower or "jupyter" in lower:
        return "Applied Python for Data Analysis & AI"
    if "business analysis" in lower or "business analyst" in lower or "business analytic" in lower or re.search(r"\bba\b", lower):
        return "Business Analysis"
    if "financial" in lower or "finance" in lower or "valuation" in lower:
        return "Financial Analytics"
    if "hr analytic" in lower or "people analytic" in lower or "human resource" in lower:
        return "HR Analytics"
    if "marketing analytic" in lower or "digital marketing" in lower:
        return "Marketing Analytics"
    if "data analytic" in lower or "data analysis" in lower or "business intelligence" in lower or re.search(r"\bbi\b", lower):
        return "Data Analytics & BI Accelerator"
    return None


def detect_course_interest(chat_text: Optional[str] = None, default_course: Optional[str] = None) -> str:
    """
    Intelligently identify the specific course of interest from the chat conversation.
    Recognizes Python, SQL, Power BI, Excel, Machine Learning, Data Science,
    Business Analysis, Financial Analytics, HR Analytics, Marketing Analytics, and Data Analytics.
    """
    matched = _match_explicit_course_in_text(chat_text)
    if matched:
        return matched

    # If not found in text, try default_course
    if default_course and default_course.strip():
        dc_lower = default_course.lower().strip()
        if dc_lower not in ("none", "null", "not specified", "general", "student", "other specialized tracks"):
            explicit_default = _match_explicit_course_in_text(default_course)
            if explicit_default:
                return explicit_default
            for key in COURSE_CATALOG_DATA:
                if key.lower() == dc_lower or key.lower() in dc_lower or dc_lower in key.lower():
                    return key

    return "Data Analytics & BI Accelerator"


def detect_discussion_line(chat_text: Optional[str] = None) -> Dict[str, Any]:
    """
    Intelligently detect the core discussion line initiated by the prospect.
    Categories:
    - pricing_tuition: Tuition fee, ₦100,000 installments, discounts, payment options.
    - beginner_nontech: Zero coding background, non-technical background, difficulty level, prerequisites.
    - career_job_switch: Job transition, career outcomes, CV review, certification, interview prep.
    - schedule_flexibility: Weekend schedule, Saturday/Sunday timings, working full-time, class recordings.
    - curriculum_syllabus: Modules, syllabus download, tools, course breakdown.
    - projects_capstone: Hands-on capstones, portfolio, real-world case studies, GitHub.
    - duration_registration: Duration, weeks/months, next cohort start date, registration process.
    - general_discovery: General course discovery and learning roadmap.
    """
    if not chat_text:
        return {
            "topic_key": "general_discovery",
            "topic_label": "Course Roadmap & Curriculum",
            "recap_phrase": "our conversation earlier about your learning goals"
        }

    lower = chat_text.lower()

    # 1. Pricing / Tuition / Installments
    if any(k in lower for k in [
        "price", "fee", "cost", "how much", "tuition", "installment", "pay", "payment",
        "discount", "affordable", "budget", "100k", "100,000", "month to month", "monthly", "expensive"
    ]):
        return {
            "topic_key": "pricing_tuition",
            "topic_label": "Tuition & Flexible Monthly Installments",
            "recap_phrase": "your question regarding our tuition options and flexible installment plans"
        }

    # 2. Beginner / Non-tech background / Zero coding
    if any(k in lower for k in [
        "beginner", "zero code", "zero coding", "no coding", "never coded", "no tech",
        "non-tech", "non tech", "background", "difficult", "hard", "prerequisite",
        "scratch", "banking", "humanities", "arts", "accounting", "starter", "zero background"
    ]):
        return {
            "topic_key": "beginner_nontech",
            "topic_label": "Starting with Zero Coding / Non-Tech Background",
            "recap_phrase": "your question about starting from scratch with a non-technical background"
        }

    # 3. Career Transition / Job Support / Certification (Checked before schedule to avoid 'job' collisions)
    if any(k in lower for k in [
        "career", "switch", "transition", "placement", "internship",
        "employ", "cv", "resume", "interview", "salary", "certificate", "certif",
        "get a job", "new job", "hire", "hiring"
    ]):
        return {
            "topic_key": "career_job_switch",
            "topic_label": "Career Transition, CV & Certification",
            "recap_phrase": "your career goals and transitioning into tech"
        }

    # 4. Schedule / Timing / Working Professional
    if any(k in lower for k in [
        "schedule", "timing", "time", "weekend", "saturday", "sunday", "weekday",
        "busy", "recording", "recorded", "replay", "classes held", "evening",
        "working full", "my job", "day job"
    ]):
        return {
            "topic_key": "schedule_flexibility",
            "topic_label": "Weekend Class Schedule & Flexibility",
            "recap_phrase": "your question about class schedules and balancing the program with work"
        }

    # 5. Curriculum / Syllabus / Tools Covered
    if any(k in lower for k in [
        "curriculum", "syllabus", "module", "outline", "what will i learn",
        "topics", "content", "send syllabus", "download syllabus"
    ]):
        return {
            "topic_key": "curriculum_syllabus",
            "topic_label": "Curriculum Modules & Practical Tools",
            "recap_phrase": "your inquiry about the week-by-week curriculum and syllabus"
        }

    # 6. Practical Projects / Capstone / Portfolio
    if any(k in lower for k in [
        "project", "capstone", "portfolio", "real-world", "real world",
        "hands on", "hands-on", "practical", "build", "github", "case study"
    ]):
        return {
            "topic_key": "projects_capstone",
            "topic_label": "Hands-on Capstone Projects & Portfolio",
            "recap_phrase": "your question about hands-on practical projects and portfolio building"
        }

    # 6. Career Transition / Job Support / Certification
    if any(k in lower for k in [
        "career", "job", "switch", "transition", "placement", "internship",
        "employ", "cv", "resume", "interview", "salary", "certificate", "certif"
    ]):
        return {
            "topic_key": "career_job_switch",
            "topic_label": "Career Transition, CV & Certification",
            "recap_phrase": "your career goals and transitioning into tech"
        }

    # 7. Duration / Cohort Start / Registration
    if any(k in lower for k in [
        "duration", "how long", "cohort", "batch", "start date", "when start",
        "register", "registration", "enroll", "admission", "deadline", "seat"
    ]):
        return {
            "topic_key": "duration_registration",
            "topic_label": "Program Duration & Upcoming Cohort Dates",
            "recap_phrase": "the program duration and upcoming cohort enrollment"
        }

    # 8. Location / Physical Office / Online Format
    if any(k in lower for k in [
        "address", "office", "location", "located", "where are you", "physical",
        "walk-in", "walk in", "in-person", "in person", "branch", "lagos", "abuja"
    ]):
        return {
            "topic_key": "location_format",
            "topic_label": "100% Live 1-on-1 Online Mentorship Format",
            "recap_phrase": "your inquiry about our training location and live 1-on-1 online mentorship format"
        }

    return {
        "topic_key": "general_discovery",
        "topic_label": "Course Roadmap & Curriculum",
        "recap_phrase": "our conversation earlier about your learning journey"
    }


def _resolve_explicit_course_from_history(
    chat_history: Optional[List[Dict[str, str]]] = None,
    fallback_text: Optional[str] = None,
    default_course: Optional[str] = None
) -> Optional[str]:
    """
    Scan user messages (newest first) for an explicit course selection or keyword,
    then non-menu assistant confirmations, then default_course.
    Returns None if no specific course was explicitly chosen yet.
    """
    if chat_history:
        user_msgs = [m.get("body", "") for m in chat_history if isinstance(m, dict) and m.get("sender") == "user"]
        for u_msg in reversed(user_msgs):
            matched = _match_explicit_course_in_text(u_msg)
            if matched:
                return matched

        asst_msgs = [m.get("body", "") for m in chat_history if isinstance(m, dict) and m.get("sender") == "assistant"]
        for a_msg in reversed(asst_msgs):
            matched = _match_explicit_course_in_text(a_msg)
            if matched:
                return matched

    if fallback_text:
        matched = _match_explicit_course_in_text(fallback_text)
        if matched:
            return matched

    if default_course and default_course.strip():
        dc_lower = default_course.lower().strip()
        if dc_lower not in ("none", "null", "not specified", "general", "student", "other specialized tracks"):
            matched = _match_explicit_course_in_text(default_course)
            if matched:
                return matched
            for key in COURSE_CATALOG_DATA:
                if key.lower() == dc_lower or key.lower() in dc_lower or dc_lower in key.lower():
                    return key

    return None


def generate_personalized_3_step_sequence(
    lead_name: str,
    course_name: Optional[str] = None,
    skill_level: Optional[str] = None,
    notes: Optional[str] = None,
    chat_summary: Optional[str] = None,
    chat_history: Optional[List[Dict[str, str]]] = None,
    discussion_topic: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Intelligently craft 3 sequential WhatsApp messages tailored to an individual user's
    learning goals, background, initiated discussion line, and specific course of interest.
    Strictly compliant with Meta WhatsApp Cloud API standards (character limits, clean bolding,
    interactive buttons, and user opt-out disclosures).
    """
    first_name = (lead_name or "there").strip().split()[0]

    # Combine available text for intelligent topic and course detection (prioritizing user messages)
    combined_chat_text = ""
    latest_user_text_slice = ""
    if chat_history:
        user_msgs = [m.get("body", "") for m in chat_history if isinstance(m, dict) and m.get("sender") == "user"]
        combined_chat_text = " ".join(user_msgs) if user_msgs else " ".join([m.get("body", "") for m in chat_history if isinstance(m, dict)])
        latest_user_text_slice = " ".join(user_msgs[-2:]) if user_msgs else combined_chat_text
    elif chat_summary:
        combined_chat_text = chat_summary
        latest_user_text_slice = chat_summary
    elif notes:
        combined_chat_text = notes
        latest_user_text_slice = notes

    # Resolve course of interest strictly from user messages first so assistant menus never pollute
    explicit_course = _resolve_explicit_course_from_history(
        chat_history=chat_history,
        fallback_text=latest_user_text_slice or combined_chat_text,
        default_course=course_name
    )
    resolved_course = explicit_course or detect_course_interest(latest_user_text_slice or combined_chat_text, default_course=course_name)

    # Detect discussion line if not explicitly provided
    TOPIC_META_MAP = {
        "pricing_tuition": {
            "topic_label": "Tuition & Flexible Monthly Installments",
            "recap_phrase": "your question regarding our tuition options and flexible installment plans"
        },
        "beginner_nontech": {
            "topic_label": "Starting with Zero Coding / Non-Tech Background",
            "recap_phrase": "your question about starting from scratch with a non-technical background"
        },
        "career_job_switch": {
            "topic_label": "Career Transition, CV & Certification",
            "recap_phrase": "your career goals and transitioning into tech"
        },
        "schedule_flexibility": {
            "topic_label": "Weekend Class Schedule & Flexibility",
            "recap_phrase": "your question about class schedules and balancing the program with work"
        },
        "curriculum_syllabus": {
            "topic_label": "Curriculum Modules & Practical Tools",
            "recap_phrase": "your inquiry about the week-by-week curriculum and syllabus"
        },
        "projects_capstone": {
            "topic_label": "Hands-on Capstone Projects & Portfolio",
            "recap_phrase": "your question about hands-on practical projects and portfolio building"
        },
        "duration_registration": {
            "topic_label": "Program Duration & Upcoming Cohort Dates",
            "recap_phrase": "the program duration and upcoming cohort enrollment"
        },
        "location_format": {
            "topic_label": "100% Live 1-on-1 Online Mentorship Format",
            "recap_phrase": "your inquiry about our training location and live 1-on-1 online mentorship format"
        },
        "general_discovery": {
            "topic_label": "Course Roadmap & Curriculum",
            "recap_phrase": "our conversation earlier about your learning journey"
        }
    }

    if discussion_topic:
        meta = TOPIC_META_MAP.get(discussion_topic, {})
        disc = {
            "topic_key": discussion_topic,
            "topic_label": meta.get("topic_label", discussion_topic),
            "recap_phrase": meta.get("recap_phrase", f"your discussion regarding {discussion_topic}")
        }
    else:
        # Scan user messages in reverse chronological order to capture the most recent topic discussed
        disc = None
        if chat_history:
            u_msgs = [m.get("body", "") for m in chat_history if isinstance(m, dict) and m.get("sender") == "user"]
            for u in reversed(u_msgs):
                cand = detect_discussion_line(u)
                if cand.get("topic_key") != "general_discovery":
                    disc = cand
                    break
        if not disc:
            disc = detect_discussion_line(latest_user_text_slice)
            if disc.get("topic_key") == "general_discovery" and combined_chat_text:
                disc = detect_discussion_line(combined_chat_text)

    course_info = COURSE_CATALOG_DATA.get(resolved_course, COURSE_CATALOG_DATA["Data Analytics & BI Accelerator"])
    course_title = course_info["title"]
    tools_short = course_info["short_tools"]
    topic_highlight = course_info["topic_highlight"]
    capstone_sample = course_info["capstone_sample"]
    duration_str = course_info["duration"]
    career_outcomes = course_info["career_outcomes"]
    level = skill_level or "Beginner"

    topic_key = disc.get("topic_key", "general_discovery")
    recap_phrase = disc.get("recap_phrase", "our conversation earlier about your learning journey")

    # =========================================================================
    # MESSAGE 1: 2-Hour Follow-up Tailored to Initiated Discussion & Course
    # =========================================================================
    if topic_key == "pricing_tuition":
        msg1_raw = f"""Hello *{first_name}*! 👋 It's *Tara* from *TekTutors Academy*.

Following up on our conversation earlier regarding {recap_phrase} for *{course_title}*! 💳

Here is a quick breakdown of our flexible tuition options:

• *Flexible Month-to-Month:* Just *₦100,000 / month* as you progress. Zero long-term lock-in—you can pause or continue at your own pace!
• *10% Upfront Discount:* Pay full tuition upfront and save ₦10,000 immediately (*₦90,000*).
• *What's Included:* Live weekend mentor classes in *{tools_short}*, 1-on-1 code reviews, and lifetime access to recordings.
• *Practical Capstone:* You will build an employer-ready *{capstone_sample}*.

We structured this so you can invest in high-demand skills without financial pressure. Would you like to review the payment details or ask me anything else?

_(Reply 1 to chat with Tara, or STOP to opt out)_"""
        msg1_buttons = [
            {"id": "seq_tuition_breakdown", "title": "View Payment Plan"},
            {"id": "seq_ask_tara", "title": "Ask Tara Question"}
        ]

    elif topic_key == "beginner_nontech":
        msg1_raw = f"""Hello *{first_name}*! 👋 It's *Tara* from *TekTutors Academy*.

Following up on our conversation earlier regarding {recap_phrase} in *{course_title}*! 🚀

I want to reassure you: over 70% of our students started with zero coding experience (coming from banking, administration, healthcare, accounting) and successfully built career confidence:

• *Starting Level:* Beginner friendly with zero prerequisites.
• *1-on-1 Weekend Mentorship:* A dedicated industry practitioner guides you step-by-step through *{tools_short}*.
• *Hands-on Practice:* You will build your own *{capstone_sample}* from scratch.
• *Tuition:* Flexible month-to-month installment at *₦100,000/month*.

Would you like to review the beginner week-by-week syllabus or book a quick 1-on-1 call with a mentor?

_(Reply 1 to chat with Tara, or STOP to opt out)_"""
        msg1_buttons = [
            {"id": "seq_dl_syllabus", "title": "Download Syllabus"},
            {"id": "seq_book_call", "title": "Book 1-on-1 Call"}
        ]

    elif topic_key == "schedule_flexibility":
        msg1_raw = f"""Hello *{first_name}*! 👋 It's *Tara* from *TekTutors Academy*.

Following up on our conversation earlier regarding {recap_phrase} for *{course_title}*! ⏰

Our learning format is built specifically for busy working professionals:

• *Live Weekend Sessions:* Interactive classes held on *Saturdays & Sundays* so your weekdays remain completely open.
• *Full Session Recordings:* Every live class is recorded and uploaded within hours for lifetime replay anytime.
• *Continuous Mentor Support:* Private weekday Slack community to debug exercises in *{tools_short}*.
• *Tuition:* Flexible month-to-month installment at *₦100,000/month*.

You can comfortably master the curriculum without disrupting your current job. Would you like to check the upcoming cohort schedule or ask me a question?

_(Reply 1 to chat with Tara, or STOP to opt out)_"""
        msg1_buttons = [
            {"id": "seq_view_schedule", "title": "View Class Schedule"},
            {"id": "seq_ask_tara", "title": "Ask Tara Question"}
        ]

    elif topic_key == "curriculum_syllabus":
        msg1_raw = f"""Hello *{first_name}*! 👋 It's *Tara* from *TekTutors Academy*.

Following up on our conversation earlier regarding {recap_phrase} for *{course_title}*! 📚

Here is a summary of the key skills and curriculum milestones you will master:

• *Core Tools & Skills:* {topic_highlight}
• *Program Duration:* {duration_str} of hands-on guided implementation
• *Practical Capstone:* You will build an end-to-end *{capstone_sample}*.
• *Tuition:* Flexible month-to-month installment at *₦100,000/month*.

Would you like the complete week-by-week syllabus or would you like to speak with our lead instructor?

_(Reply 1 to chat with Tara, or STOP to opt out)_"""
        msg1_buttons = [
            {"id": "seq_dl_syllabus", "title": "Download Syllabus"},
            {"id": "seq_ask_tara", "title": "Ask Tara Question"}
        ]

    elif topic_key == "projects_capstone":
        msg1_raw = f"""Hello *{first_name}*! 👋 It's *Tara* from *TekTutors Academy*.

Following up on our conversation earlier regarding {recap_phrase} in *{course_title}*! 🛠️

At TekTutors, we focus 100% on practical portfolio building so you have tangible proof of your skills:

• *Major Capstone Project:* You will build an enterprise-grade *{capstone_sample}*.
• *Practical Stack:* Real messy industry datasets using *{tools_short}*.
• *GitHub & Portfolio Reviews:* Mentors review your code and dashboards so you stand out to hiring managers.
• *Tuition:* Flexible month-to-month installment at *₦100,000/month*.

Would you like to view sample past student capstones or chat with our mentor?

_(Reply 1 to chat with Tara, or STOP to opt out)_"""
        msg1_buttons = [
            {"id": "seq_view_capstones", "title": "View Capstones"},
            {"id": "seq_ask_tara", "title": "Ask Tara Question"}
        ]

    elif topic_key == "career_job_switch":
        msg1_raw = f"""Hello *{first_name}*! 👋 It's *Tara* from *TekTutors Academy*.

Following up on our conversation earlier regarding {recap_phrase} with *{course_title}*! 🎯

Our entire program is geared towards preparing you for high-impact roles:

• *Target Roles:* {career_outcomes}
• *Practical Portfolio:* 3 employer-ready projects including *{capstone_sample}*.
• *Career Acceleration:* 1-on-1 CV review, LinkedIn profile optimization, and mock interview coaching.
• *Verified Credential:* Industry-recognized TekTutors Certificate of Completion.

Would you like to book a free 15-minute admissions discovery call with our Senior Lead Mentor to map out your career path?

_(Reply 1 to chat with Tara, or STOP to opt out)_"""
        msg1_buttons = [
            {"id": "seq_book_call", "title": "Book 1-on-1 Call"},
            {"id": "seq_reserve_seat", "title": "Reserve Seat"}
        ]

    elif topic_key == "duration_registration":
        msg1_raw = f"""Hello *{first_name}*! 👋 It's *Tara* from *TekTutors Academy*.

Following up on our conversation earlier regarding {recap_phrase} for *{course_title}*! 🚀

Here are the key cohort enrollment details:

• *Program Duration:* {duration_str} of live weekend mentor-led sessions.
• *Cohort Cap:* Strictly limited to *15 students* per batch to guarantee personal 1-on-1 mentor debugging.
• *Next Batch:* Enrolling now for next weekend's kickoff.
• *Tuition:* Flexible month-to-month at *₦100,000/month* (or ₦90,000 upfront with 10% discount).

Seats fill up fast once onboarding begins. Would you like to reserve your seat or ask me a question?

_(Reply 1 to chat with Tara, or STOP to opt out)_"""
        msg1_buttons = [
            {"id": "seq_reserve_seat", "title": "Reserve Seat"},
            {"id": "seq_ask_tara", "title": "Ask Tara Question"}
        ]

    elif topic_key == "location_format":
        msg1_raw = f"""Hello *{first_name}*! 👋 It's *Tara* from *TekTutors Academy*.

Following up on our conversation earlier regarding {recap_phrase} for *{course_title}*! 🌍

Here is how our 100% live 1-on-1 online mentorship works without any commute:

• *Live 1-on-1 Interactive Video:* You meet directly with your private industry mentor over screen-sharing to build real projects in *{tools_short}*.
• *Learn From Anywhere:* Zero traffic commute or crowded classrooms—attend from home or office on weekends or weekday evenings.
• *Corporate HQ:* Our administrative hub is in Lagos, Nigeria, serving learners across Nigeria and globally.
• *Tuition:* Flexible month-to-month at *₦100,000/month* (or ₦90,000 upfront with 10% discount).

Would you like to book a free 15-minute 1-on-1 discovery call or review the syllabus?

_(Reply 1 to chat with Tara, or STOP to opt out)_"""
        msg1_buttons = [
            {"id": "seq_book_call", "title": "Book 1-on-1 Call"},
            {"id": "seq_dl_syllabus", "title": "Download Syllabus"}
        ]

    else:
        # general_discovery
        msg1_raw = f"""Hello *{first_name}*! 👋 It's *Tara* from *TekTutors Academy*.

Thank you for chatting with me earlier about our *{course_title}* program! Here is your personalized learning roadmap based on our discussion:

• *Starting Level:* {level}
• *Key Skills:* {topic_highlight}
• *Format:* Live Weekend Mentorship + 1-on-1 Code & Project Reviews
• *Tuition:* Month-to-month installment at *₦100,000/month* (pay as you learn)

Would you like to review the week-by-week curriculum syllabus or ask me any question?

_(Reply 1 to chat with Tara, or STOP to opt out)_"""
        msg1_buttons = [
            {"id": "seq_dl_syllabus", "title": "Download Syllabus"},
            {"id": "seq_ask_tara", "title": "Ask Tara Question"}
        ]

    msg1_text = format_whatsapp_cloud_text(msg1_raw)

    # =========================================================================
    # MESSAGE 2: Social Proof, Career ROI & Practical Projects (Value Nurture)
    # =========================================================================
    msg2_raw = f"""Hi *{first_name}*! 👋 Checking back in regarding your goals in *{course_title}*.

Over 70% of TekTutors students started with non-tech backgrounds (banking, marketing, healthcare, administration) and built career-ready confidence through hands-on capstone mentorship:

• *Executive Portfolio:* You will build your own *{capstone_sample}*
• *Live Mentor Debugging:* Dedicated 1-on-1 mentor guidance every weekend using *{tools_short}*
• *Zero Lock-in:* Billed month-to-month at *₦100,000/month* so you stay in total control of your budget

Are you planning to transition into tech or upskill in your current workplace?

_(Reply 1 to chat with Tara, or STOP to opt out)_"""

    msg2_text = format_whatsapp_cloud_text(msg2_raw)
    msg2_buttons = [
        {"id": "seq_view_capstones", "title": "View Capstones"},
        {"id": "seq_tuition_breakdown", "title": "Tuition Details"}
    ]

    # =========================================================================
    # MESSAGE 3: Admissions Urgency, Seat Reservation & Free 1-on-1 Call
    # =========================================================================
    msg3_raw = f"""Hello *{first_name}*! 🚀 Our upcoming *{course_title}* cohort is currently finalizing its mentor pairings!

Because we cap each cohort at *15 students* to guarantee personal 1-on-1 mentor attention, seats fill up quickly:

• *Program:* {course_title} ({duration_str})
• *Next Batch:* Kicking off next Saturday
• *Special Benefit:* Free 15-Minute Admissions Discovery Call with our Senior Lead Mentor
• *Action:* Confirm your reservation today before the waitlist opens

Would you like to claim your free 15-minute mentor discovery call or reserve your seat?

_(Reply 1 to chat with Tara, or STOP to opt out)_"""

    msg3_text = format_whatsapp_cloud_text(msg3_raw)
    msg3_buttons = [
        {"id": "seq_book_call", "title": "Book 1-on-1 Call"},
        {"id": "seq_reserve_seat", "title": "Reserve Seat"}
    ]

    topic_title_suffix = f" ({disc.get('topic_label', 'Roadmap')})" if topic_key != "general_discovery" else ""

    return [
        {
            "step": 1,
            "title": f"Step 1: Follow-up on {resolved_course}{topic_title_suffix}",
            "body": msg1_text,
            "buttons": msg1_buttons,
            "delay_hours": 2  # Follow-up 2 hours later (T+2h)
        },
        {
            "step": 2,
            "title": f"Step 2: Social Proof & Projects - {resolved_course} (+10 Hours)",
            "body": msg2_text,
            "buttons": msg2_buttons,
            "delay_hours": 10  # 10 hours later (T+10h, 10-hour interval)
        },
        {
            "step": 3,
            "title": f"Step 3: Admissions & Mentor Call - {resolved_course} (+20 Hours)",
            "body": msg3_text,
            "buttons": msg3_buttons,
            "delay_hours": 20  # 20 hours later (T+20h, 10 hours after Step 2, safely within Meta 24h window)
        }
    ]


async def dispatch_whatsapp_message_direct(
    recipient_phone: str,
    recipient_name: str,
    body_text: str,
    buttons: Optional[List[Dict[str, str]]] = None,
    campaign_name: str = "WhatsApp 3-Touch AI Sequence",
    lead_id: Optional[int] = None,
    db: Optional[AsyncSession] = None,
    fast_fail_error: Optional[Dict[str, Any]] = None,
    auto_commit: bool = True
) -> Dict[str, Any]:
    """
    Dispatch a single WhatsApp Cloud API message with interactive buttons (or text fallback),
    track response, and record into WhatsAppLog.
    """
    clean_phone = clean_phone_number(recipient_phone)
    if not clean_phone:
        return {"status": "failed", "error": "Invalid recipient phone number format"}

    delivery_status = "delivered"
    delivery_error = None
    api_response = None

    # Enforce WhatsApp Cloud API button constraints: max 3 buttons, title <= 20 chars
    valid_buttons = []
    if buttons:
        for b in buttons[:3]:
            title = b.get("title", "")[:20].strip()
            if title:
                valid_buttons.append({"id": b.get("id", f"btn_{title}"), "title": title})

    try:
        if fast_fail_error:
            api_response = {"error": fast_fail_error}
        elif whatsapp_client.is_configured():
            if valid_buttons:
                api_response = await whatsapp_client.send_interactive_buttons(clean_phone, body_text, valid_buttons)
                # Only fallback to plain text if error is NOT an OAuth/token, 24h-window, sandbox, or undeliverable error
                if api_response and api_response.get("error"):
                    err_obj = api_response.get("error", {})
                    err_code = err_obj.get("code") if isinstance(err_obj, dict) else None
                    if err_code not in (190, 131047, 131030, 131026, 10, 200, 100):
                        button_fallback_text = body_text + "\n\n" + "\n".join([f"🔘 [{b['title']}]" for b in valid_buttons])
                        api_response = await whatsapp_client.send_text_message(clean_phone, button_fallback_text)
            else:
                api_response = await whatsapp_client.send_text_message(clean_phone, body_text)

        if api_response and api_response.get("error"):
            delivery_status = "failed"
            err_obj = api_response.get("error", {})
            err_code = err_obj.get("code") if isinstance(err_obj, dict) else None
            err_msg = err_obj.get("message", "") if isinstance(err_obj, dict) else str(err_obj)

            if err_code == 190:
                delivery_error = "Meta OAuth Token Expired/Invalid (Code 190): Please update WHATSAPP_TOKEN in your .env / variables with a valid Meta Access Token."
            elif err_code == 131047:
                delivery_error = "Meta 24-hour service window expired (contact has not messaged your WhatsApp bot in the last 24h). Requires pre-approved Meta Template."
            elif err_code == 131030:
                delivery_error = "Meta Sandbox restriction: phone number not in verified test numbers list (Manage phone number list in Meta Developer Portal)."
            elif err_code == 131026:
                delivery_error = "Undeliverable by WhatsApp (number may not have an active WhatsApp account or invalid format)."
            else:
                delivery_error = f"Meta API Error ({err_code or 'N/A'}): {err_msg}"
        elif not whatsapp_client.is_configured():
            # Simulated environment: successfully delivered to mock client
            delivery_status = "delivered"
            delivery_error = None

    except Exception as e:
        delivery_status = "failed"
        delivery_error = str(e)
        logger.error(f"Error dispatching WhatsApp message to {clean_phone}: {e}")

    # Log into WhatsAppLog
    if db:
        try:
            # Also record in conversation if conversation exists
            conv_stmt = select(Conversation).where(Conversation.phone == clean_phone)
            conv_res = await db.execute(conv_stmt)
            conv = conv_res.scalar_one_or_none()
            if not conv:
                conv = Conversation(phone=clean_phone, customer_name=recipient_name, ai_active=True)
                db.add(conv)
                await db.flush()

            chat_msg = Message(
                conversation_id=conv.id,
                sender="assistant",
                body=body_text + ("\n\n" + "\n".join([f"🔘 [{b['title']}]" for b in valid_buttons]) if valid_buttons else ""),
                media_type="interactive" if valid_buttons else "text"
            )
            if delivery_status == "failed":
                chat_msg.media_type = "failed"
                chat_msg.body = f"[⚠️ WhatsApp Delivery Failed: {delivery_error}]\n\n" + chat_msg.body
            db.add(chat_msg)
            conv.last_message_at = datetime.datetime.now()

            log_entry = WhatsAppLog(
                lead_id=lead_id,
                recipient_phone=clean_phone,
                recipient_name=recipient_name or "Student",
                message_type="sequence",
                campaign_name=campaign_name,
                body=body_text,
                status=delivery_status,
                error_message=delivery_error
            )
            db.add(log_entry)
            if auto_commit:
                await db.commit()
            else:
                await db.flush()
        except Exception as e:
            logger.error(f"Error persisting WhatsAppLog: {e}")

    return {
        "status": delivery_status,
        "phone": clean_phone,
        "name": recipient_name,
        "error": delivery_error,
        "api_response": api_response
    }


async def enroll_lead_in_3_step_sequence(
    db: AsyncSession,
    lead: Lead,
    dispatch_all_now: bool = False,
    chat_history: Optional[List[Dict[str, str]]] = None,
    latest_user_text: Optional[str] = None,
    custom_bodies: Optional[Dict[int, str]] = None,
    shared_auth_error: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Enroll a user who chatted with Tara into the 3-step intelligently crafted sequence.
    Detects their course of interest and initiated discussion line from recent chat interactions.
    Ensures that Step 1 is scheduled for 2 hours later, dynamically relevant to what was discussed,
    and updates any existing pending message so the follow-up reflects their latest conversation.
    """
    clean_phone = clean_phone_number(lead.phone)
    if not clean_phone:
        return {"status": "error", "message": f"Lead {lead.name} has no valid phone number."}

    # Fetch recent chat messages from DB if not passed
    history_msgs: List[Dict[str, str]] = []
    if chat_history:
        history_msgs = [dict(m) for m in chat_history if isinstance(m, dict)]
    else:
        try:
            conv_stmt = select(Conversation).where(Conversation.phone == clean_phone)
            conv_res = await db.execute(conv_stmt)
            conv = conv_res.scalar_one_or_none()
            if conv:
                msgs_stmt = select(Message).where(Message.conversation_id == conv.id).order_by(Message.id.desc()).limit(15)
                msgs_res = await db.execute(msgs_stmt)
                db_msgs = list(reversed(msgs_res.scalars().all()))
                history_msgs = [{"sender": m.sender, "body": m.body} for m in db_msgs]
        except Exception as e:
            logger.warning(f"Could not load conversation history for {clean_phone}: {e}")

    if latest_user_text:
        if not history_msgs or history_msgs[-1].get("body") != latest_user_text or history_msgs[-1].get("sender") != "user":
            history_msgs.append({"sender": "user", "body": latest_user_text})

    # Combine text corpus across conversation (prioritizing user messages so assistant menus never pollute detection)
    user_msgs = [m.get("body", "") for m in history_msgs if isinstance(m, dict) and m.get("sender") == "user"]
    all_user_text = " ".join(user_msgs)
    all_chat_text = " ".join([m.get("body", "") for m in history_msgs if isinstance(m, dict)])
    latest_user_text_combined = " ".join(user_msgs[-2:]) if user_msgs else all_chat_text

    # Detect discussion line: check latest user inquiries in reverse order to capture active discussion line
    disc_info = None
    if user_msgs:
        for u_text in reversed(user_msgs):
            cand_disc = detect_discussion_line(u_text)
            if cand_disc.get("topic_key") != "general_discovery":
                disc_info = cand_disc
                break
    if not disc_info:
        disc_info = detect_discussion_line(all_user_text or all_chat_text)

    topic_label = disc_info["topic_label"]
    topic_key = disc_info["topic_key"]

    # Detect course of interest strictly from explicit mentions first so Tara's 6-track greeting never pollutes
    explicit_course = _resolve_explicit_course_from_history(
        chat_history=history_msgs,
        fallback_text=latest_user_text_combined,
        default_course=lead.course_interest
    )
    detected_course = explicit_course or detect_course_interest(all_user_text, default_course=lead.course_interest)

    # Only overwrite lead.course_interest when an explicit course was actually selected/discussed by the customer
    if explicit_course and lead.course_interest != explicit_course:
        lead.course_interest = explicit_course

    # Update lead notes with discussion topic if relevant
    if topic_key != "general_discovery":
        topic_note = f"Discussion: {topic_label}"
        if not lead.notes:
            lead.notes = topic_note
        elif topic_note not in lead.notes:
            lead.notes = f"{lead.notes} | {topic_note}"

    steps = generate_personalized_3_step_sequence(
        lead_name=lead.name or "Student",
        course_name=detected_course,
        skill_level=lead.skill_level,
        notes=lead.notes,
        chat_history=history_msgs,
        discussion_topic=topic_key
    )

    now = datetime.datetime.now()
    dispatched_results = []
    detected_auth_error = shared_auth_error

    for step_data in steps:
        step_num = step_data["step"]
        step_title = step_data["title"]
        body = (custom_bodies.get(step_num) if custom_bodies and custom_bodies.get(step_num) else None) or step_data["body"]
        buttons = step_data["buttons"]
        delay_hrs = step_data["delay_hours"]

        scheduled_time = now + datetime.timedelta(hours=delay_hrs)

        # Check if already scheduled or sent (safe against multiple rows for the same phone + step)
        existing_stmt = (
            select(ScheduledWhatsAppMessage)
            .where(
                ScheduledWhatsAppMessage.recipient_phone == clean_phone,
                ScheduledWhatsAppMessage.sequence_step == step_num,
                ScheduledWhatsAppMessage.status.in_(["pending", "delivered", "sent"])
            )
            .order_by(ScheduledWhatsAppMessage.id.desc())
        )
        existing_res = await db.execute(existing_stmt)
        existing_records = existing_res.scalars().all()
        pending_records = [r for r in existing_records if r.status == "pending"]
        scheduled_rec = pending_records[0] if pending_records else (existing_records[0] if existing_records else None)

        if not scheduled_rec:
            scheduled_rec = ScheduledWhatsAppMessage(
                lead_id=lead.id,
                recipient_phone=clean_phone,
                recipient_name=lead.name or "Student",
                sequence_step=step_num,
                step_title=step_title,
                body=body,
                buttons_json=json.dumps(buttons),
                scheduled_for=scheduled_time,
                status="pending"
            )
            db.add(scheduled_rec)
            await db.flush()
        elif pending_records:
            # Update all pending records for this step with the latest conversation context and refresh timer!
            for idx, p_rec in enumerate(pending_records):
                if idx == 0:
                    p_rec.step_title = step_title
                    p_rec.body = body
                    p_rec.buttons_json = json.dumps(buttons)
                    p_rec.scheduled_for = scheduled_time
                else:
                    p_rec.status = "cancelled"
            await db.flush()

        # Decide whether to dispatch immediately (ONLY when explicitly requested via dispatch_all_now)
        should_send = bool(dispatch_all_now)

        if should_send:
            res = await dispatch_whatsapp_message_direct(
                recipient_phone=clean_phone,
                recipient_name=lead.name or "Student",
                body_text=body,
                buttons=buttons,
                campaign_name=f"WhatsApp 3-Touch AI: {step_title}",
                lead_id=lead.id,
                db=db,
                fast_fail_error=detected_auth_error,
                auto_commit=False
            )
            # If Meta returned an OAuth token error (Code 190), remember it so remaining steps don't hang waiting on network timeouts
            api_err = (res.get("api_response") or {}).get("error") if isinstance(res.get("api_response"), dict) else None
            if isinstance(api_err, dict) and api_err.get("code") == 190 and not detected_auth_error:
                detected_auth_error = api_err

            scheduled_rec.status = res["status"]
            scheduled_rec.error_message = res.get("error")
            scheduled_rec.sent_at = datetime.datetime.now()
            dispatched_results.append({
                "step": step_num,
                "title": step_title,
                "status": res["status"],
                "error": res.get("error")
            })
        else:
            dispatched_results.append({
                "step": step_num,
                "title": step_title,
                "status": scheduled_rec.status,
                "scheduled_for": scheduled_rec.scheduled_for.strftime("%Y-%m-%d %H:%M:%S") if scheduled_rec.scheduled_for else None
            })

    await db.commit()

    return {
        "status": "success",
        "lead_id": lead.id,
        "lead_name": lead.name,
        "phone": clean_phone,
        "course": detected_course,
        "discussion_topic": topic_label,
        "steps": dispatched_results,
        "auth_error": detected_auth_error
    }


async def auto_trigger_sequence_for_all_chat_users(
    db: AsyncSession,
    target_audience: str = "all_chat_users",
    dispatch_all_now: bool = True,
    custom_bodies: Optional[Dict[int, str]] = None
) -> Dict[str, Any]:
    """
    Automatically identify all users who chatted with Tara and dispatch the 3-step WhatsApp sequence.
    Short-circuits repeated OAuth failures so batch dispatch finishes in ~1 second instead of hanging.
    """
    stmt = select(Lead).order_by(desc(Lead.id))
    if target_audience == "hot":
        stmt = stmt.where(Lead.status == "hot")
    elif target_audience == "qualified":
        stmt = stmt.where(Lead.status.in_(["hot", "qualified"]))
    elif target_audience == "new":
        stmt = stmt.where(Lead.status == "new")

    res = await db.execute(stmt)
    leads = res.scalars().all()

    if not leads:
        all_res = await db.execute(select(Lead).order_by(desc(Lead.id)))
        leads = all_res.scalars().all()

    # Deduplicate by phone
    seen_phones = set()
    unique_leads = []
    for l in leads:
        clean = clean_phone_number(l.phone)
        if clean and clean not in seen_phones:
            seen_phones.add(clean)
            unique_leads.append(l)

    results = []
    total_messages_dispatched = 0
    total_delivered = 0
    total_failed = 0
    shared_auth_error = None
    first_error_message = None

    for lead in unique_leads:
        enroll_res = await enroll_lead_in_3_step_sequence(
            db,
            lead,
            dispatch_all_now=dispatch_all_now,
            custom_bodies=custom_bodies,
            shared_auth_error=shared_auth_error
        )
        if enroll_res.get("auth_error") and not shared_auth_error:
            shared_auth_error = enroll_res["auth_error"]

        for s in enroll_res.get("steps", []):
            if s["status"] in ("delivered", "sent"):
                total_messages_dispatched += 1
                if s["status"] == "delivered":
                    total_delivered += 1
            elif s["status"] == "failed":
                total_messages_dispatched += 1
                total_failed += 1
                if s.get("error") and not first_error_message:
                    first_error_message = s["error"]
            elif s["status"] == "pending":
                total_messages_dispatched += 1
        results.append(enroll_res)

    return {
        "status": "success",
        "total_leads_targeted": len(unique_leads),
        "total_messages_processed": total_messages_dispatched,
        "delivered_count": total_delivered,
        "failed_count": total_failed,
        "first_error": first_error_message,
        "dispatch_all_now": dispatch_all_now,
        "lead_details": results
    }


async def process_due_scheduled_whatsapp_messages(db: AsyncSession) -> Dict[str, Any]:
    """
    Find all scheduled WhatsApp messages whose scheduled_for time has arrived (<= now)
    and status is 'pending', then dispatch them via Meta WhatsApp Cloud API.
    Enforces the 10-hour sequence interval progression automatically.
    """
    now = datetime.datetime.now()
    stmt = select(ScheduledWhatsAppMessage).where(
        ScheduledWhatsAppMessage.status == "pending",
        ScheduledWhatsAppMessage.scheduled_for <= now
    ).order_by(ScheduledWhatsAppMessage.scheduled_for.asc()).limit(50)

    res = await db.execute(stmt)
    due_items = res.scalars().all()

    processed_count = 0
    delivered_count = 0
    failed_count = 0
    dispatched_items = []

    for item in due_items:
        buttons = []
        if item.buttons_json:
            try:
                buttons = json.loads(item.buttons_json)
            except Exception:
                buttons = []

        dispatch_res = await dispatch_whatsapp_message_direct(
            recipient_phone=item.recipient_phone,
            recipient_name=item.recipient_name,
            body_text=item.body,
            buttons=buttons,
            campaign_name=f"WhatsApp 10h Sequence: Step {item.sequence_step}",
            lead_id=item.lead_id,
            db=db
        )

        item.status = dispatch_res["status"]
        item.error_message = dispatch_res.get("error")
        item.sent_at = datetime.datetime.now()

        processed_count += 1
        if dispatch_res["status"] in ("delivered", "sent"):
            delivered_count += 1
        elif dispatch_res["status"] == "failed":
            failed_count += 1

        dispatched_items.append({
            "id": item.id,
            "lead_id": item.lead_id,
            "phone": item.recipient_phone,
            "step": item.sequence_step,
            "status": item.status,
            "error": item.error_message
        })

    if processed_count > 0:
        await db.commit()

    return {
        "status": "success",
        "processed_count": processed_count,
        "delivered_count": delivered_count,
        "failed_count": failed_count,
        "items": dispatched_items
    }


async def process_due_scheduled_whatsapp_messages_standalone() -> Dict[str, Any]:
    """Process due scheduled WhatsApp messages using an isolated database session."""
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        return await process_due_scheduled_whatsapp_messages(db)


_whatsapp_worker_task: Optional[asyncio.Task] = None
_whatsapp_worker_running: bool = False


async def _scheduled_whatsapp_worker_loop():
    logger.info("📱 Scheduled WhatsApp Background Dispatcher started (Polling every 60s)...")
    while _whatsapp_worker_running:
        try:
            await process_due_scheduled_whatsapp_messages_standalone()
        except Exception as e:
            logger.error(f"Error in scheduled WhatsApp worker loop: {e}")
        try:
            await asyncio.sleep(60)
        except (asyncio.CancelledError, GeneratorExit):
            break


def start_scheduled_whatsapp_worker():
    """Start background dispatcher loop for scheduled WhatsApp follow-up messages."""
    global _whatsapp_worker_task, _whatsapp_worker_running
    if os.getenv("PYTEST_CURRENT_TEST") or "pytest" in sys.modules:
        return
    if not _whatsapp_worker_running:
        _whatsapp_worker_running = True
        _whatsapp_worker_task = asyncio.create_task(_scheduled_whatsapp_worker_loop())


def stop_scheduled_whatsapp_worker():
    """Stop background dispatcher loop for scheduled WhatsApp follow-up messages."""
    global _whatsapp_worker_task, _whatsapp_worker_running
    _whatsapp_worker_running = False
    if _whatsapp_worker_task and not _whatsapp_worker_task.done():
        _whatsapp_worker_task.cancel()


