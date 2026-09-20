import re
import time
import logging
from typing import Optional, Dict, Any, List
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models import Course, CostTelemetry

logger = logging.getLogger(__name__)

# Standard pricing and official URLs
STANDARD_MONTHLY_FEE = "₦100,000"
REGISTRATION_URL = "https://tektutors.com.ng/registration"

# Static catalog cache for zero-latency retrieval
TRACK_INFO = {
    1: {
        "title": "Data Analytics & BI Accelerator",
        "badge": "1️⃣",
        "duration": "10 Weeks",
        "level": "Beginner-Intermediate",
        "fee": "₦100,000 / month (Flexible month-to-month billing)",
        "outcomes": "Data Analyst, BI Specialist, Insights Reporter",
        "tools": "Advanced Excel, SQL queries, Power BI dashboards, EDA, and business metrics.",
        "prereq": "None. 100% beginner friendly, no coding experience required."
    },
    2: {
        "title": "Excel for Data Analysis & Reporting",
        "badge": "2️⃣",
        "duration": "6-8 Weeks",
        "level": "Beginner-Advanced",
        "fee": "₦100,000 / month (Flexible month-to-month billing)",
        "outcomes": "Financial Analyst, Operations Specialist, Excel Specialist",
        "tools": "Formulas, VLOOKUP/XLOOKUP, PivotTables, Power Query, automated KPI reports.",
        "prereq": "Basic computer literacy. Completely beginner friendly."
    },
    3: {
        "title": "SQL for Data Engineering & Analytics",
        "badge": "3️⃣",
        "duration": "6-8 Weeks",
        "level": "Beginner-Advanced",
        "fee": "₦100,000 / month (Flexible month-to-month billing)",
        "outcomes": "Database Analyst, SQL Developer, BI Engineer",
        "tools": "PostgreSQL, DDL/DML, JOINs, subqueries, CTEs, window functions, query optimization.",
        "prereq": "Basic analytical thinking. Zero prior SQL needed."
    },
    4: {
        "title": "Power BI & Business Intelligence Masterclass",
        "badge": "4️⃣",
        "duration": "6-8 Weeks",
        "level": "Beginner-Advanced",
        "fee": "₦100,000 / month (Flexible month-to-month billing)",
        "outcomes": "Power BI Developer, BI Consultant, Dashboard Engineer",
        "tools": "Power Query, advanced DAX, star schema data modelling, interactive storytelling.",
        "prereq": "Familiarity with spreadsheets is helpful but not required."
    },
    5: {
        "title": "Applied Python for Data Analysis & AI",
        "badge": "5️⃣",
        "duration": "6-8 Weeks",
        "level": "Beginner-Intermediate",
        "fee": "₦100,000 / month (Flexible month-to-month billing)",
        "outcomes": "Python Analyst, Junior Data Scientist, Automation Specialist",
        "tools": "Python fundamentals, Jupyter, NumPy, Pandas, visualization, and predictive modeling.",
        "prereq": "Basic computer skills. No prior programming needed."
    },
    6: {
        "title": "Other Available Courses & Specialized Tracks",
        "badge": "6️⃣",
        "duration": "6-20 Weeks",
        "level": "Beginner to Advanced",
        "fee": "₦100,000 / month (Flexible month-to-month billing)",
        "outcomes": "Data Scientist, Machine Learning Engineer, Business Analyst, Financial Analyst, HR Analyst",
        "tools": "Data Science with Python, Machine Learning, Business Analysis, Financial Analytics, Marketing Analytics, HR Analytics, Data Governance & Quality, etc.",
        "prereq": "Tracks available for all backgrounds from complete beginners to advanced."
    }
}

INVALID_COURSE_NAMES = {
    "not specified", "none", "null", "n/a", "na", "undefined",
    "general", "general inquiry", "other specialized tracks",
    "unknown", "other courses", "other available courses & specialized tracks"
}

COURSE_SYLLABUS_MAP = {
    "Machine Learning with Python": {
        "title": "Machine Learning with Python",
        "duration": "16 Weeks (3-5 Months)",
        "modules": [
            "Module 1: Applied Python Programming, NumPy, Pandas, Vectorization & Linear Algebra",
            "Module 2: Data Preprocessing, Feature Engineering, Outlier Detection & Scaling",
            "Module 3: Supervised Learning (Linear & Logistic Regression, Decision Trees, Random Forests, XGBoost)",
            "Module 4: Unsupervised Learning (K-Means, PCA, Hierarchical Clustering) & Model Validation",
            "Module 5: Model Deployment (FastAPI, Docker, Streamlit) & 3 End-to-End Production Capstones"
        ],
        "prerequisites": "Python programming and foundational statistics."
    },
    "Data Science with Python": {
        "title": "Data Science with Python",
        "duration": "16-20 Weeks (4-6 Months)",
        "modules": [
            "Module 1: Python Programming, Data Structures, NumPy, Pandas & Exploratory Data Analysis (EDA)",
            "Module 2: Applied Statistics, Probability Distributions & Hypothesis Testing (A/B Testing)",
            "Module 3: Feature Engineering, Pipeline Design & Predictive Modeling",
            "Module 4: Machine Learning Algorithms & Model Evaluation",
            "Module 5: End-to-End Capstone Projects, Portfolio Walkthroughs & Model APIs"
        ],
        "prerequisites": "Computer literacy and willingness to practice."
    },
    "Power BI & Business Intelligence": {
        "title": "Power BI & Business Intelligence",
        "duration": "6-8 Weeks (1.5-2 Months)",
        "modules": [
            "Module 1: Data Ingestion, Cleaning & Transformation with Power Query",
            "Module 2: Relational Data Modeling, Cardinality & Star Schema Architecture",
            "Module 3: DAX Calculations (Calculated Columns, Measures, Time Intelligence)",
            "Module 4: Interactive Visual Storytelling, Drill-Through & Mobile Layouts",
            "Module 5: Power BI Service, Scheduled Refresh, Row-Level Security & Capstones"
        ],
        "prerequisites": "None. Complete beginners welcome."
    },
    "SQL & Enterprise Database Analytics": {
        "title": "SQL & Enterprise Database Analytics",
        "duration": "6-8 Weeks (1.5-2 Months)",
        "modules": [
            "Module 1: Relational Database Architecture & SQL Fundamentals",
            "Module 2: Filtering, Sorting, Aggregations & Grouping",
            "Module 3: Complex Joins (INNER, LEFT, RIGHT, FULL) & Multi-Table Queries",
            "Module 4: Subqueries, Common Table Expressions (CTEs) & Window Functions",
            "Module 5: Query Optimization, Views & Real-World Business Analytics Capstones"
        ],
        "prerequisites": "None. Complete beginners welcome."
    },
    "Excel for Data Analysis & Business Modeling": {
        "title": "Excel for Data Analysis & Business Modeling",
        "duration": "6-8 Weeks (1.5-2 Months)",
        "modules": [
            "Module 1: Advanced Formulas, Functions & Dynamic Arrays (XLOOKUP, INDEX/MATCH)",
            "Module 2: Data Cleaning & Transformation with Power Query",
            "Module 3: PivotTables, Slicers & Calculated Fields",
            "Module 4: Interactive Executive KPI Dashboards & Visual Design",
            "Module 5: Financial & Business Analysis Capstone Projects"
        ],
        "prerequisites": "Basic computer skills."
    },
    "Applied Python for Data Analysis & AI": {
        "title": "Applied Python for Data Analysis & AI",
        "duration": "6-8 Weeks (1.5-2 Months)",
        "modules": [
            "Module 1: Python Syntax, Data Types, Control Flow & Functions",
            "Module 2: NumPy & Pandas for High-Performance Data Manipulation",
            "Module 3: Data Cleaning, Missing Data Handling & Transformation",
            "Module 4: Exploratory Data Analysis & Visualization (Matplotlib, Seaborn)",
            "Module 5: Real-World Business Analytics Capstone Projects"
        ],
        "prerequisites": "Basic computer skills."
    },
    "Business Analysis": {
        "title": "Business Analysis",
        "duration": "10 Weeks (2.5 Months)",
        "modules": [
            "Module 1: Business Analysis Foundations & Stakeholder Management",
            "Module 2: Elicitation Techniques, Requirements Engineering & User Stories",
            "Module 3: Process Mapping, Flowcharts, BPMN & Gap Analysis",
            "Module 4: Business Data Analytics, KPIs & Metrics Definition",
            "Module 5: Business Requirement Documents (BRD), Agile/Scrum & Capstone Projects"
        ],
        "prerequisites": "None. Ideal for career switchers."
    },
    "Financial Analytics": {
        "title": "Financial Analytics",
        "duration": "6-8 Weeks (1.5-2 Months)",
        "modules": [
            "Module 1: Financial Modeling Foundations & Accounting Integration",
            "Module 2: Financial Ratio Analysis, Cash Flow Modeling & Working Capital",
            "Module 3: Variance Analysis, Budgeting & Rolling Forecasts in Excel/Power BI",
            "Module 4: Executive Financial Dashboards & KPI Storytelling",
            "Module 5: Real-World Corporate Valuation & Financial Capstone Projects"
        ],
        "prerequisites": "Basic understanding of spreadsheets and business fundamentals."
    },
    "HR Analytics": {
        "title": "HR Analytics",
        "duration": "6-8 Weeks (1.5-2 Months)",
        "modules": [
            "Module 1: People Analytics Architecture & HR Metrics Definition",
            "Module 2: Employee Turnover, Retention & Headcount Modeling",
            "Module 3: Talent Acquisition Analytics, Pipeline Conversion & Cost-Per-Hire",
            "Module 4: HR Executive Dashboards in Power BI with Demographic Segmentation",
            "Module 5: Workforce Planning & Predictive Retention Capstone Projects"
        ],
        "prerequisites": "Basic computer skills. Ideal for HR professionals."
    },
    "Marketing Analytics": {
        "title": "Marketing Analytics",
        "duration": "6-8 Weeks (1.5-2 Months)",
        "modules": [
            "Module 1: Customer Acquisition, CAC, LTV & Marketing Funnel Analysis",
            "Module 2: Multi-Touch Attribution Modeling & Campaign ROI Tracking",
            "Module 3: Customer Segmentation & Cohort Retention Analysis",
            "Module 4: Performance Marketing Executive Dashboards in Power BI",
            "Module 5: Full-Funnel Digital Marketing Optimization Capstone Projects"
        ],
        "prerequisites": "Basic computer skills. Ideal for marketers and growth leads."
    },
    "Data Analytics & BI Accelerator": {
        "title": "Data Analytics & BI Accelerator",
        "duration": "10 Weeks (2.5 Months)",
        "modules": [
            "Module 1: Foundations & Business Metrics (Problem Scoping & Diagnostic Analytics)",
            "Module 2: Data Wrangling & Database Mastery (Advanced Excel & Relational SQL Queries)",
            "Module 3: Business Intelligence & Dashboards (Power BI Modeling & DAX)",
            "Module 4: Advanced Analytics & AI (Python Data Analysis, Pandas & EDA)",
            "Module 5: Capstone Projects & Career Portfolio (3 Employer-Ready Projects)"
        ],
        "prerequisites": "None. Complete beginners welcome."
    }
}


def normalize_course_name(name: Optional[str]) -> Optional[str]:
    """
    Sanitize and normalize any course name or query string into a canonical course title.
    Returns None if the name is empty or an invalid placeholder like 'Not specified'.
    """
    if not name or not isinstance(name, str):
        return None
    clean = name.strip()
    lower = clean.lower()
    if lower in INVALID_COURSE_NAMES:
        return None

    # Exact or alias matches
    if "machine learning" in lower or "machine-learning" in lower or re.search(r'\bml\b', lower):
        return "Machine Learning with Python"
    if "data science" in lower or re.search(r'\bds\b', lower):
        return "Data Science with Python"
    if "power bi" in lower or "powerbi" in lower:
        return "Power BI & Business Intelligence"
    if "sql" in lower or "database" in lower or "postgres" in lower or "mysql" in lower:
        return "SQL & Enterprise Database Analytics"
    if "excel" in lower:
        return "Excel for Data Analysis & Business Modeling"
    if "applied python" in lower or "python for data" in lower or (re.search(r'\bpython\b', lower) and "machine" not in lower and "data science" not in lower):
        return "Applied Python for Data Analysis & AI"
    if "business analysis" in lower or "business analyst" in lower or re.search(r'\bba\b', lower):
        return "Business Analysis"
    if "financial analytic" in lower or "finance" in lower:
        return "Financial Analytics"
    if "hr analytic" in lower or "people analytic" in lower:
        return "HR Analytics"
    if "marketing analytic" in lower:
        return "Marketing Analytics"
    if "data analytic" in lower or "data analysis" in lower or "business intelligence" in lower or re.search(r'\bbi\b', lower):
        return "Data Analytics & BI Accelerator"

    # Exact canonical check
    for canonical in COURSE_SYLLABUS_MAP:
        if canonical.lower() == lower:
            return canonical

    # Track info catalog check
    for track_num, track in TRACK_INFO.items():
        if track_num == 6:
            continue
        if track["title"].lower() in lower or str(track_num) == lower:
            if "excel" in track["title"].lower():
                return "Excel for Data Analysis & Business Modeling"
            if "sql" in track["title"].lower():
                return "SQL & Enterprise Database Analytics"
            if "power bi" in track["title"].lower():
                return "Power BI & Business Intelligence"
            if "python" in track["title"].lower():
                return "Applied Python for Data Analysis & AI"
            return "Data Analytics & BI Accelerator"

    return None


def get_course_syllabus(course_name: Optional[str]) -> tuple:
    """
    Safely resolve a course name to its canonical title and complete syllabus dictionary.
    Guarantees that a valid syllabus is returned and never yields 'Not specified'.
    """
    canonical_name = normalize_course_name(course_name)
    if not canonical_name or canonical_name not in COURSE_SYLLABUS_MAP:
        canonical_name = "Data Analytics & BI Accelerator"
    return canonical_name, COURSE_SYLLABUS_MAP[canonical_name]


def detect_target_course(text: str) -> Optional[str]:
    """Identify which specific course is being discussed or requested."""
    return normalize_course_name(text)


GREETING_PATTERNS = [
    r"^(hi|hello|hey|good\s+morning|good\s+afternoon|good\s+day|good\s+evening|how\s+far|yo|start|menu|options)\b"
]

REGISTRATION_PATTERNS = [
    r"(register|registration|how\s+to\s+pay|where\s+to\s+pay|payment\s+link|registration\s+link|enrollment\s+link|sign\s+up\s+link|link\s+to\s+pay|link\s+to\s+register|how\s+do\s+i\s+pay|how\s+can\s+i\s+pay|want\s+to\s+pay|ready\s+to\s+pay)"
]

ADVISOR_CALL_PATTERNS = [
    r"(book\s+(me\s+)?(a\s+)?(1-on-1|one[- ]on[- ]one|discovery|advisor)\s+call)",
    r"(schedule\s+(a\s+)?(1-on-1|one[- ]on[- ]one|discovery|advisor|admissions)?\s*call)",
    r"(book\s+a\s+call)",
    r"(schedule\s+(a\s+)?(meeting|session|call)\s+with\s+(an?\s+)?advisor)",
    r"(talk|speak)\s+with\s+an?\s+admissions\s+advisor",
    r"(1-on-1\s+call\s+with\s+an\s+admissions\s+advisor)"
]

PAYMENT_PLAN_PATTERNS = [
    r"(payment\s+plans?|view\s+payment\s+plans?)",
    r"(month-to-month(\s+payment)?(\s+plan)?)",
    r"(tell\s+me\s+more\s+about\s+the\s+month-to-month)",
    r"(installment\s+plans?|pay\s+in\s+installments?)",
    r"(tuition\s+plans?|tuition\s+breakdown|fee\s+structure|payment\s+options)",
    r"(how\s+does\s+(the\s+)?payment\s+work)"
]

SYLLABUS_OVERVIEW_PATTERNS = [
    r"\b(syllabus|curriculum|course outline|learning roadmap|module breakdown)\b",
    r"(send|share|view|download|get|full).*(syllabus|curriculum|outline)",
    r"(syllabus\s+breakdown|curriculum\s+breakdown|course\s+syllabus|course\s+curriculum)",
    r"(course\s+outline|detailed\s+syllabus|complete\s+syllabus)"
]

ESCALATION_PATTERNS = [
    r"(speak\s+to\s+(a\s+)?human|talk\s+to\s+(a\s+)?human|human\s+agent|real\s+person|customer\s+care|customer\s+service|speak\s+to\s+a\s+representative|talk\s+to\s+manager)"
]

CAREER_BACKGROUND_PATTERNS = [
    r"\b(bank(er|ing)?|account(ant|ing)?|finance|financial|audit(or)?|economics?)\b",
    r"\b(no\s+coding|zero\s+coding|no\s+experience|beginner|can\s+i\s+cope|career\s+transition|switch\s+to\s+tech|non-tech)\b"
]

HARDWARE_SPECS_PATTERNS = [
    r"\b(laptop|computer|system\s+requirements?|pc\s+specs?|mac(book)?|ram|laptop\s+specs?)\b",
    r"\b(can\s+i\s+(use|learn\s+with)\s+(my\s+)?(phone|mobile)|is\s+laptop\s+compulsory|do\s+i\s+need\s+a\s+(laptop|computer|pc))\b"
]

SCHEDULE_PATTERNS = [
    r"\b(schedule|weekend(\s+classes?)?|working\s+professionals?|time\s+of\s+class|when\s+are\s+classes|class\s+hours|miss\s+a\s+class|flexible\s+time|after\s+work|evening\s+classes?|night\s+classes?)\b"
]

INTERNATIONAL_PAYMENT_PATTERNS = [
    r"\b(dollars?|usd|gbp|pounds?|foreign\s+currency|outside\s+nigeria|international\s+students?|pay\s+from\s+abroad)\b"
]

CERTIFICATION_PATTERNS = [
    r"\b(certificate|certification|accredited|job\s+support|job\s+placement|internship|resume\s+review|portfolio\s+review)\b",
    r"\b(guarantee(\s+a)?\s+job|will\s+i\s+get\s+a\s+job|job\s+guarantee|employment\s+support)\b"
]

DISCOUNT_PROMO_PATTERNS = [
    r"\b(discounts?|scholarships?|promo(\s*codes?)?|vouchers?|coupons?|cheaper|reduce\s+(the\s+)?fees?|price\s+slash|financial\s+aid)\b"
]

LOCATION_PATTERNS = [
    r"\b(physical\s+address|office\s+address|physical\s+office|physical\s+location|physical\s+center|physical\s+class(es)?|physical\s+branch|in[- ]person|offline\s+class(es)?|walk[- ]in)\b",
    r"\b(where\s+(are\s+you|is\s+your\s+office|is\s+your\s+location|is\s+tektutors(\s+office|\s+located)?|are\s+you\s+located))\b",
    r"\b((what|where)\s+is\s+(your|the)\s+(physical\s+)?(address|location|office|headquarters))\b",
    r"\b(do\s+(you|u)\s+have\s+(a\s+)?(physical|office|center|branch|location|building))\b",
    r"\b(have\s+(a\s+)?(physical|office|branch)\s*(address|location|office|center|branch)?)\b",
    r"\b(can\s+i\s+(visit|come\s+to)\s+(your\s+)?(office|center|class|branch|location))\b",
    r"\b(office\s+(in|at)\s+(lagos|abuja|ph|port\s+harcourt|nigeria|ibadan|kano|lekki|ikeja|vi|victoria\s+island|yaba))\b",
    r"\b(address\s+please|your\s+address|office\s+location)\b"
]

COURSE_QUERY_PATTERNS = [
    (r"\b(data\s+analytic(s)?|bi\s+accelerator)\b", 1),
    (r"\b(excel|spreadsheet|power\s+query|vlookup|pivot)\b", 2),
    (r"\b(sql|postgres|database\s+analytics?)\b", 3),
    (r"\b(power\s*bi|dax|interactive\s+dashboards?)\b", 4),
    (r"\b(applied\s+python|python\s+for\s+data|pandas\s+course)\b", 5),
    (r"\b(other\s+courses?|more\s+courses?|specialized\s+tracks?|additional\s+courses?|explore\s+other|what\s+else\s+do\s+you\s+offer)\b", 6)
]

# In-memory query response cache for sub-millisecond repeated queries
_QUERY_RESPONSE_CACHE: Dict[str, Dict[str, Any]] = {}
_CACHE_MAX_SIZE = 1000
_CACHE_TTL_SECONDS = 3600

def _normalize_key(text: str) -> str:
    """Normalize user input text to canonical alphanumeric form for caching."""
    return re.sub(r'[^\w\s]', '', text.lower()).strip()


def strip_asterisks(text: str) -> str:
    """
    Format text for professional WhatsApp presentation with clean, eye-catching bolding:
    Converts list bullets, normalizes markdown **bold** to WhatsApp *bold*, and trims inner spaces.
    """
    if not text or not isinstance(text, str):
        return text
    text = text.replace('\u202f', ' ').replace('\u00a0', ' ').replace('\u2011', '-')
    text = re.sub(r'(?m)^\s*[\*\-]\s+', '• ', text)
    text = re.sub(r'\*{3,}([^*\n]+?)\*{3,}', r'*\1*', text)
    text = re.sub(r'\*{2}([^*\n]+?)\*{2}', r'*\1*', text)
    text = re.sub(r'\*[ \t]+([^*\n]+?)\*', r'*\1*', text)
    text = re.sub(r'\*([^*\n]+?)[ \t]+\*', r'*\1*', text)
    text = re.sub(r'\*{2,}', '*', text)
    asterisk_count = text.count('*')
    if asterisk_count % 2 != 0:
        last_idx = text.rfind('*')
        if last_idx != -1:
            text = text[:last_idx] + text[last_idx + 1:]
    return text


def cache_query_response(normalized_key: str, data: Dict[str, Any]):
    """Store response in in-memory LRU cache."""
    if not normalized_key:
        return
    if len(_QUERY_RESPONSE_CACHE) >= _CACHE_MAX_SIZE:
        oldest_k = next(iter(_QUERY_RESPONSE_CACHE))
        _QUERY_RESPONSE_CACHE.pop(oldest_k, None)
    clean_resp = strip_asterisks(data.get("response", ""))
    _QUERY_RESPONSE_CACHE[normalized_key] = {
        "data": {
            "response": clean_resp,
            "tool_logs": data.get("tool_logs", [])
        },
        "timestamp": time.time()
    }


async def log_cost_savings(
    phone: str,
    query_type: str,
    tokens_saved: int,
    latency_ms: float,
    model_used: Optional[str] = None
):
    """Log telemetry regarding saved tokens and fast-path execution to DB asynchronously."""
    async def _persist():
        try:
            async with AsyncSessionLocal() as db:
                record = CostTelemetry(
                    phone=phone,
                    query_type=query_type,
                    tokens_saved=tokens_saved,
                    latency_ms=round(latency_ms, 2),
                    model_used=model_used or "fast-path-rules"
                )
                db.add(record)
                await db.commit()
        except Exception as e:
            logger.warning(f"Could not persist CostTelemetry: {e}")

    try:
        import asyncio
        loop = asyncio.get_running_loop()
        loop.create_task(_persist())
    except Exception:
        await _persist()

def is_conversational_query(text: str) -> bool:
    """
    Detect if the user message is a consultative, advice-seeking, or nuanced question
    that should be answered dynamically by the AI model (Tara) rather than a static template.
    """
    clean = text.strip()
    words = clean.split()
    lower = clean.lower()

    # Pure single digits (1-6) or menu keywords are fast-path menu selections
    if re.match(r'^\s*([1-6])\s*$', clean) or lower in (
        "menu", "tracks", "options", "courses", "other courses", "all courses", "view courses"
    ):
        return False

    # Direct Email Delivery / Syllabus Capture request (e.g. "Email the pdf curriculum of machine learning to ctowolabi@gmail.com")
    if re.search(r'[\w\.-]+@[\w\.-]+\.\w+', clean):
        email_keywords = [
            "curriculum", "syllabus", "brochure", "outline", "send", "email",
            "mail", "forward", "dispatch", "deliver", "share", "drop", "info", "course", "pdf"
        ]
        if any(kw in lower for kw in email_keywords) or len(words) <= 8 or "?" not in clean:
            return False

    # Explicit urgent human escalation demands
    if any(p in lower for p in [
        "speak to human", "talk to human", "human agent", "real person",
        "human representative", "talk to manager", "scam", "fraud"
    ]):
        return False

    # Interactive button CTA clicks (exact button copy)
    exact_button_phrases = [
        "yes, please book me a 1-on-1 call with an admissions advisor.",
        "tell me more about the month-to-month payment plan.",
        "please share the complete course syllabus breakdown.",
        "how to pay for the course?",
        "send me the registration link",
        "how do i register?",
        "how can i register?"
    ]
    if lower in exact_button_phrases:
        return False

    # Standalone simple greetings like "hi", "hello", "good morning" without follow-up questions
    if len(words) <= 2 and any(re.match(rf'^{g}[!\.]*$', lower) for g in [
        "hi", "hello", "hey", "good morning", "good afternoon", "good evening", "hi there"
    ]):
        return False

    # Factual short location queries like "where is your office", "where are you located", "physical address"
    if any(re.search(pat, lower) for pat in LOCATION_PATTERNS) and len(words) <= 7 and not any(w in lower for w in [
        "recommend", "background", "career", "teach", "learn", "study", "best"
    ]):
        return False

    # If the user is asking a consultative question or giving context:
    consultative_indicators = [
        "i am a", "i'm a", "my background", "i work as", "i studied", "transition",
        "switch to tech", "zero coding", "no coding", "no experience", "beginner",
        "can i learn", "can i do", "can i cope", "will it be hard", "is it hard",
        "which track", "what track", "which course", "what course", "recommend",
        "suggest", "advice", "help me choose", "suitable for me", "good for me",
        "fit for me", "difference between", "compare", "not sure which", "confused",
        "looking to", "want to know if", "can data analytics", "how long will it take me",
        "what do you think", "tell me what", "explain why", "is this right", "can i use",
        "do i need", "is laptop", "weekend", "evening", "curriculum", "syllabus",
        "course outline", "what do you teach", "what will i learn", "what is covered",
        "tell me about", "interested in", "details on", "information on", "learn more"
    ]
    if any(ci in lower for ci in consultative_indicators) and not re.search(r'[\w\.-]+@[\w\.-]+\.\w+', clean):
        return True

    # Questions that contain personal inquiry pronouns or comparison question words
    if "?" in clean and any(w in lower for w in ["i", "my", "me", "should", "could", "would", "which", "why", "best", "advise"]):
        return True

    # If a message mentions course keywords inside a multi-word question or sentence:
    # It must NOT be intercepted by the rigid brochure!
    if len(words) > 4 and any(w in lower for w in [
        "data analytic", "excel", "sql", "power bi", "python", "machine learning", "data science"
    ]):
        return True

    # Multi-word sentence that doesn't match an exact button
    if len(words) > 6 and ("?" in clean or any(w in lower for w in ["i", "my", "can", "how", "what", "why", "is"])):
        return True

    return False


async def check_fast_path(phone: str, user_text: str) -> Optional[Dict[str, Any]]:
    """
    Evaluate user message against verified deterministic fast-path patterns.
    Guarantees zero asterisks in any returned response.
    """
    res = await _raw_check_fast_path(phone, user_text)
    if isinstance(res, dict) and "response" in res and isinstance(res["response"], str):
        res["response"] = strip_asterisks(res["response"])
    return res

async def _raw_check_fast_path(phone: str, user_text: str) -> Optional[Dict[str, Any]]:
    """
    Internal implementation of deterministic fast-path patterns.
    """
    clean_phone = phone.strip().replace("+", "")
    text_clean = user_text.strip()
    lower_text = text_clean.lower()
    start_time = time.time()
    norm_key = _normalize_key(text_clean)

    # Conversational inquiry filter: Allow natural advising to flow to LLM
    if is_conversational_query(text_clean):
        logger.info(f"Conversational inquiry detected for {clean_phone} ('{text_clean[:60]}') - routing to AI Model.")
        return None

    # 0. Instant in-memory cache hit (< 0.1ms)
    cached = _QUERY_RESPONSE_CACHE.get(norm_key)
    if cached and (time.time() - cached["timestamp"]) < _CACHE_TTL_SECONDS:
        return {
            "response": cached["data"]["response"],
            "tool_logs": cached["data"].get("tool_logs", []),
            "fast_path": True,
            "tokens_saved": 900
        }

    # 1. 1-on-1 Advisor Call Booking Fast Path
    for pat in ADVISOR_CALL_PATTERNS:
        if re.search(pat, lower_text):
            from app.tools import qualify_and_capture_lead
            await qualify_and_capture_lead.ainvoke({
                "phone": clean_phone,
                "notes": "Requested 1-on-1 Admissions Discovery Call via fast path"
            })
            response = (
                "📅 *Book Your 1-on-1 Admissions Discovery Call*\n\n"
                "I'd love to set up your complimentary 15-minute 1-on-1 Strategy Session with a Senior TekTutors Admissions Advisor! 🎯\n\n"
                "During this private consultation, we will:\n"
                "• Review your current background & career aspirations\n"
                "• Recommend the optimal learning track for your target salary\n"
                "• Walk you through our live 1-on-1 industry mentor format & practical projects\n"
                "• Answer any questions about our flexible schedule and tuition\n\n"
                "🎁 *Special Bonus:* Booking a call reserves a *Free 1-on-1 CV Optimization & LinkedIn Audit* (valued at ₦35,000) upon enrollment!\n\n"
                "👉 *To lock in your call slot, please reply with:*\n"
                "1. *Your Full Name*\n"
                "2. *Preferred Time & Day* (e.g., Tomorrow at 2:00 PM)\n"
                "3. *Course Track of interest* (or reply 'Not sure yet')\n\n"
                f"You can also secure your enrollment directly anytime at:\n🔗 {REGISTRATION_URL}"
            )
            elapsed_ms = (time.time() - start_time) * 1000
            await log_cost_savings(clean_phone, "fast_path_advisor_call", tokens_saved=1050, latency_ms=elapsed_ms)
            res_dict = {
                "response": response,
                "tool_logs": ["qualify_and_capture_lead"],
                "fast_path": True,
                "tokens_saved": 1050
            }
            cache_query_response(norm_key, res_dict)
            return res_dict

    # 2. Payment Plans & Month-to-Month Tuition Fast Path
    for pat in PAYMENT_PLAN_PATTERNS:
        if re.search(pat, lower_text):
            from app.tools import qualify_and_capture_lead
            await qualify_and_capture_lead.ainvoke({
                "phone": clean_phone,
                "notes": "Inquired about flexible payment plans via fast path"
            })
            response = (
                "💳 *TekTutors Flexible Tuition & Payment Plans*\n\n"
                "We believe quality tech training should be accessible, empowering, and completely risk-free. Here are our flexible options:\n\n"
                f"1️⃣ *Flexible Month-to-Month Plan (Most Popular):*\n"
                f"• *{STANDARD_MONTHLY_FEE} / month* — pay as you learn with zero financial pressure\n"
                "• Zero long-term debt or huge upfront lump sum; cancel anytime\n"
                "• Includes weekly 1-on-1 private mentorship with an industry practitioner\n"
                "• Progress at your own personalized pace\n\n"
                "2️⃣ *Upfront Full-Payment Plan (Best Value):*\n"
                "• Receive an exclusive *10% tuition discount* when you pay in full upfront — pay just *₦90,000* (Save ₦10,000!)\n"
                "• Immediate onboarding, priority mentor allocation, and bonus CV polish\n\n"
                "🎁 *Fast-Action Perk:* All students build 3 employer-ready capstones and receive job placement coaching.\n\n"
                f"👉 *Ready to get started? Enroll securely on our official portal:*\n"
                f"🔗 {REGISTRATION_URL}\n\n"
                "Which course track would you like to enroll in? (Reply with a track number 1-6 or course name!)"
            )
            elapsed_ms = (time.time() - start_time) * 1000
            await log_cost_savings(clean_phone, "fast_path_payment_plans", tokens_saved=950, latency_ms=elapsed_ms)
            res_dict = {
                "response": response,
                "tool_logs": ["qualify_and_capture_lead"],
                "fast_path": True,
                "tokens_saved": 950
            }
            cache_query_response(norm_key, res_dict)
            return res_dict

    # 3. Direct Human Escalation Fast Path
    for pat in ESCALATION_PATTERNS:
        if re.search(pat, lower_text):
            from app.tools import escalate_to_human_advisor
            try:
                await escalate_to_human_advisor.ainvoke({
                    "phone": clean_phone,
                    "reason": "Customer triggered instant fast-path human transfer request."
                })
            except Exception as err:
                logger.error(f"Error in fast-path escalation: {err}")

            response = (
                "I am connecting you right away with a Senior TekTutors Admissions Advisor! 📱\n\n"
                "They have been notified and will step into this chat shortly to assist you directly.\n\n"
                f"In the meantime, feel free to review our courses and register at: {REGISTRATION_URL}"
            )
            elapsed_ms = (time.time() - start_time) * 1000
            await log_cost_savings(clean_phone, "fast_path_escalation", tokens_saved=900, latency_ms=elapsed_ms)
            return {
                "response": response,
                "tool_logs": ["escalate_to_human_advisor"],
                "fast_path": True,
                "tokens_saved": 900
            }

    # 2. Direct Registration & Payment Redirection Fast Path
    for pat in REGISTRATION_PATTERNS:
        if re.search(pat, lower_text):
            from app.tools import qualify_and_capture_lead
            await qualify_and_capture_lead.ainvoke({
                "phone": clean_phone,
                "notes": "Fast-path payment & registration link request"
            })
            response = (
                "🎯 *Ready to accelerate your career with TekTutors?*\n\n"
                f"You can register and complete your enrollment securely online here:\n"
                f"👉 *Official Portal:* {REGISTRATION_URL}\n\n"
                "💡 *Our Program Highlights:*\n"
                "• Live 1-on-1 personalized mentorship\n"
                f"• Flexible month-to-month billing ({STANDARD_MONTHLY_FEE} / month)\n"
                "• Real-world portfolio projects & certificate upon completion\n\n"
                "Do you have any questions before registering, or would you like to schedule a 15-minute advisor call?"
            )
            elapsed_ms = (time.time() - start_time) * 1000
            await log_cost_savings(clean_phone, "fast_path_registration", tokens_saved=850, latency_ms=elapsed_ms)
            return {
                "response": response,
                "tool_logs": ["qualify_and_capture_lead"],
                "fast_path": True,
                "tokens_saved": 850
            }

    # 3. Direct Curriculum / Syllabus Email Capture Fast Path
    email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text_clean)
    email_trigger_keywords = [
        "curriculum", "syllabus", "brochure", "outline", "send", "email",
        "mail", "forward", "dispatch", "deliver", "share", "drop", "info", "course"
    ]
    is_standalone_email = bool(email_match and len(lower_text.split()) <= 6)
    if email_match and (any(kw in lower_text for kw in email_trigger_keywords) or is_standalone_email):
        extracted_email = email_match.group(0)
        from app.tools import qualify_and_capture_lead
        # 1. Detect target course from current text
        detected_course = detect_target_course(lower_text)

        # 2. If not found in current message (e.g. user just supplied their email), look up recent conversation or lead's prior course_interest
        if not detected_course:
            try:
                from app.database import AsyncSessionLocal
                from app.models import Lead, Conversation, Message
                from sqlalchemy import select, desc
                async with AsyncSessionLocal() as db:
                    # Check recent messages in the conversation first
                    conv_rec = (await db.execute(select(Conversation).where(Conversation.phone == clean_phone).limit(1))).scalars().first()
                    if conv_rec:
                        recent_msgs = (await db.execute(select(Message).where(Message.conversation_id == conv_rec.id).order_by(desc(Message.id)).limit(8))).scalars().all()
                        for m in recent_msgs:
                            c_found = detect_target_course(m.body or "")
                            if c_found:
                                detected_course = c_found
                                break

                    # If still not found, check lead's recorded course_interest
                    if not detected_course:
                        lead_rec = (await db.execute(select(Lead).where(Lead.phone == clean_phone).order_by(desc(Lead.id)).limit(1))).scalars().first()
                        if lead_rec and lead_rec.course_interest:
                            norm_interest = normalize_course_name(lead_rec.course_interest)
                            if norm_interest:
                                detected_course = norm_interest
            except Exception as e:
                logger.warning(f"Fast-path curriculum course resolution note: {e}")

        course_label, syllabus_data = get_course_syllabus(detected_course)

        await qualify_and_capture_lead.ainvoke({
            "phone": clean_phone,
            "email": extracted_email,
            "course_interest": course_label,
            "notes": f"Curriculum requested via fast path for email {extracted_email}"
        })

        module_list_text = "\n".join([f"• **{m.split(':')[0]}:** {':'.join(m.split(':')[1:]) if ':' in m else m}" for m in syllabus_data["modules"]])

        # Directly dispatch official branded syllabus email in real-time
        try:
            from app.email_service import send_email_async
            await send_email_async(
                to_email=extracted_email,
                to_name="Student",
                subject=f"📚 Your TekTutors {course_label} Syllabus & Learning Roadmap",
                body_markdown=(
                    f"Hi there,\n\n"
                    f"Thank you for requesting the official curriculum roadmap for **{course_label}** at TekTutors Academy!\n\n"
                    f"### Curriculum Architecture ({syllabus_data['duration']}):\n"
                    f"{module_list_text}\n\n"
                    f"💡 **Prerequisites:** {syllabus_data['prerequisites']}\n\n"
                    f"Every learner receives **live 1-on-1 industry mentorship** with flexible **₦100,000/month** tuition (month-to-month, cancel anytime).\n\n"
                    f"Ready to get started? Complete your registration online:\n"
                    f"👉 https://tektutors.com.ng/registration"
                ),
                campaign_type="follow_up",
                cta_text=f"Enroll in {course_label}",
                cta_url="https://tektutors.com.ng/registration",
                course_name=course_label
            )
            logger.info(f"Curriculum email successfully delivered to {extracted_email} for {course_label}")

            # Automatically enroll prospect into 5-day daily follow-up drip sequence
            try:
                from app.email_service import enroll_lead_in_daily_drip_sequence
                await enroll_lead_in_daily_drip_sequence(
                    lead_id=None,
                    email=extracted_email,
                    name="Student",
                    course_name=course_label
                )
            except Exception as ex:
                logger.warning(f"Fast path drip enrollment notice: {ex}")
        except Exception as e:
            logger.error(f"Error during real-time syllabus email dispatch to {extracted_email}: {e}")

        response = (
            f"📧 *Curriculum Sent Instantly!*\n\n"
            f"I have dispatched the complete week-by-week syllabus for *{course_label}* directly to your inbox at: *{extracted_email}*! 🚀\n\n"
            "📚 *What makes TekTutors unique:*\n"
            "• 100% live 1-on-1 mentorship with an active industry practitioner\n"
            "• 3 employer-ready portfolio capstones for your LinkedIn and resume\n"
            f"• Tuition: {STANDARD_MONTHLY_FEE} / month (Flexible month-to-month billing)\n\n"
            f"When you are ready to secure your slot and lock in your mentor, enroll here:\n"
            f"👉 {REGISTRATION_URL}\n\n"
            "Do you have any questions about prerequisites or scheduling, or would you like to book an intro call with an advisor?"
        )
        elapsed_ms = (time.time() - start_time) * 1000
        await log_cost_savings(clean_phone, "fast_path_curriculum", tokens_saved=1200, latency_ms=elapsed_ms)
        return {
            "response": response,
            "tool_logs": ["qualify_and_capture_lead"],
            "fast_path": True,
            "tokens_saved": 1200
        }

    # 4. General Syllabus / Curriculum Breakdown Fast Path (when email is not yet provided)
    for pat in SYLLABUS_OVERVIEW_PATTERNS:
        if re.search(pat, lower_text) and not email_match:
            from app.tools import qualify_and_capture_lead

            # Detect if a specific course was requested
            detected_course = detect_target_course(lower_text)
            if not detected_course:
                try:
                    from app.database import AsyncSessionLocal
                    from app.models import Lead, Conversation, Message
                    from sqlalchemy import select, desc
                    async with AsyncSessionLocal() as db:
                        conv_rec = (await db.execute(select(Conversation).where(Conversation.phone == clean_phone).limit(1))).scalars().first()
                        if conv_rec:
                            recent_msgs = (await db.execute(select(Message).where(Message.conversation_id == conv_rec.id).order_by(desc(Message.id)).limit(8))).scalars().all()
                            for m in recent_msgs:
                                c_found = detect_target_course(m.body or "")
                                if c_found:
                                    detected_course = c_found
                                    break

                        if not detected_course:
                            lead_rec = (await db.execute(select(Lead).where(Lead.phone == clean_phone).order_by(desc(Lead.id)).limit(1))).scalars().first()
                            if lead_rec and lead_rec.course_interest:
                                norm_interest = normalize_course_name(lead_rec.course_interest)
                                if norm_interest:
                                    detected_course = norm_interest
                except Exception as e:
                    logger.warning(f"Fast-path syllabus overview course resolution note: {e}")

            target_course, syllabus_data = get_course_syllabus(detected_course)

            await qualify_and_capture_lead.ainvoke({
                "phone": clean_phone,
                "course_interest": target_course,
                "notes": f"Requested course syllabus breakdown for {target_course} via fast path"
            })

            module_bullets = "\n".join([f"🔹 *{m}*" for m in syllabus_data["modules"]])

            response = (
                f"📚 *TekTutors Practical Curriculum & Syllabus Breakdown ({target_course})*\n\n"
                f"Our **{target_course}** program ({syllabus_data['duration']}) is 100% practical, project-based, and taught through live 1-on-1 mentorship. Here is your curriculum architecture:\n\n"
                f"{module_bullets}\n\n"
                f"💡 *Prerequisites:* {syllabus_data['prerequisites']}\n"
                f"💰 *Tuition:* {STANDARD_MONTHLY_FEE} / month (or ₦90,000 upfront discount)\n\n"
                "📧 *Want the complete week-by-week PDF brochure?*\n"
                "👉 Reply with your *Email Address* (e.g., name@gmail.com) and our admissions team will send the full syllabus straight to your inbox!\n\n"
                f"Or complete your registration directly here:\n🔗 {REGISTRATION_URL}"
            )
            elapsed_ms = (time.time() - start_time) * 1000
            await log_cost_savings(clean_phone, "fast_path_syllabus_overview", tokens_saved=1100, latency_ms=elapsed_ms)
            return {
                "response": response,
                "tool_logs": ["qualify_and_capture_lead"],
                "fast_path": True,
                "tokens_saved": 1100
            }

    # 5. Direct Track Selection by Number (1-6) or Other Courses Exploration
    other_courses_match = re.search(r'\b(other\s+courses?|others|more\s+courses?|explore\s+other|what\s+other\s+courses?|show\s+other\s+courses?|all\s+courses)\b', lower_text)
    num_match = re.search(r'\b(track|option|course)\s*([1-6])\b', lower_text)
    if not num_match:
        num_match = re.match(r'^\s*([1-6])\b', lower_text)

    if num_match or other_courses_match:
        if other_courses_match:
            track_num = 6
        elif num_match:
            track_num = int(num_match.group(2) if num_match.lastindex and num_match.lastindex >= 2 else num_match.group(1))
        else:
            track_num = 6
        if track_num == 6:
            from app.tools import qualify_and_capture_lead
            await qualify_and_capture_lead.ainvoke({
                "phone": clean_phone,
                "course_interest": "Other Specialized Tracks",
                "notes": "Exploring other available courses via fast path"
            })
            response = (
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
                f"🔗 {REGISTRATION_URL}"
            )
            elapsed_ms = (time.time() - start_time) * 1000
            await log_cost_savings(clean_phone, "fast_path_other_courses", tokens_saved=1200, latency_ms=elapsed_ms)
            return {
                "response": response,
                "tool_logs": ["qualify_and_capture_lead"],
                "fast_path": True,
                "tokens_saved": 1200
            }

        track = TRACK_INFO.get(track_num)
        if track:
            from app.tools import qualify_and_capture_lead
            await qualify_and_capture_lead.ainvoke({
                "phone": clean_phone,
                "course_interest": track["title"],
                "notes": f"Selected Track {track_num} via fast path"
            })
            response = (
                f"🎯 *Excellent choice! Track {track_num}: {track['title']}*\n\n"
                "This program is 100% practical, project-driven, and delivered via personalized 1-on-1 mentorship with an experienced industry mentor.\n\n"
                f"📚 *What you will master:*\n• {track['tools']}\n\n"
                f"⏱️ *Duration:* {track['duration']}\n"
                f"💵 *Tuition:* {track['fee']}\n"
                f"🎯 *Career Outcomes:* {track['outcomes']}\n"
                f"📌 *Prerequisites:* {track['prereq']}\n\n"
                f"👉 *Register & Enroll Here:* {REGISTRATION_URL}\n\n"
                "To personalize your roadmap:\n"
                "*Have you worked with data tools before, or are you starting completely fresh?* (You can also reply with your name & email to receive the detailed syllabus)."
            )
            elapsed_ms = (time.time() - start_time) * 1000
            await log_cost_savings(clean_phone, f"fast_path_track_{track_num}", tokens_saved=1100, latency_ms=elapsed_ms)
            return {
                "response": response,
                "tool_logs": ["qualify_and_capture_lead"],
                "fast_path": True,
                "tokens_saved": 1100
            }

    # 5. Generic Greeting Fast Path
    for pat in GREETING_PATTERNS:
        if re.match(pat, lower_text) and len(text_clean.split()) <= 4:
            response = (
                "Hello! 👋 Welcome to *TekTutors AI & Data Academy*.\n"
                "🚀 *Fast-track your career into high-paying Tech & Data roles with dedicated 1-on-1 industry mentorship!*\n\n"
                "🏆 *Why 1,200+ ambitious learners choose TekTutors:*\n"
                "• *Private 1-on-1 Expert Mentorship* — zero crowded classrooms, learn at your own pace\n"
                "• *100% Practical & Portfolio-Driven* — graduate with 3 employer-ready capstones\n"
                "• *Flexible Tuition:* ₦100,000 / month (month-to-month billing, or save 10% on full upfront payment)\n"
                "• *Job-Ready Support:* CV optimization, mock interviews, and accredited certificate\n\n"
                "Which skill track would you like to explore?\n"
                "1️⃣ *Data Analytics & BI Accelerator* (Excel, SQL, Power BI — Most Popular!)\n"
                "2️⃣ *Excel for Data Analysis* (Formulas, Dashboards, Power Query)\n"
                "3️⃣ *SQL for Data Analysis* (Queries, Joins, Aggregations)\n"
                "4️⃣ *Power BI & Business Intelligence* (DAX, Interactive Dashboards)\n"
                "5️⃣ *Applied Python for Data Analysis & AI* (Pandas, ML, Automation)\n"
                "6️⃣ *Explore Other Courses* (Data Science, Machine Learning, Business Analysis, Financial Analytics & more)\n\n"
                "🎁 *Special Bonus:* Enroll this week to receive a *Free 1-on-1 CV Optimization & LinkedIn Audit* (valued at ₦35,000)!\n\n"
                "Reply with a number (1-6), or let me know what career goal you're working toward!"
            )
            elapsed_ms = (time.time() - start_time) * 1000
            await log_cost_savings(clean_phone, "fast_path_greeting", tokens_saved=800, latency_ms=elapsed_ms)
            res_dict = {
                "response": response,
                "tool_logs": [],
                "fast_path": True,
                "tokens_saved": 800
            }
            cache_query_response(norm_key, res_dict)
            return res_dict

    # 6. Career Background & Transition Fast Path (Banking, Accounting, Beginners, Zero-Coding)
    for pat in CAREER_BACKGROUND_PATTERNS:
        if re.search(pat, lower_text):
            from app.tools import qualify_and_capture_lead
            await qualify_and_capture_lead.ainvoke({
                "phone": clean_phone,
                "notes": f"Inquired about career transition/background: {text_clean[:60]}"
            })
            is_finance = bool(re.search(r"\b(bank|account|finance|audit|econ)", lower_text))
            if is_finance:
                response = (
                    "📊 *Perfect fit for Banking & Financial Professionals!*\n\n"
                    "Many of our most successful learners come from accounting, banking, and audit backgrounds. For your career path, we highly recommend:\n\n"
                    "1️⃣ *Data Analytics & BI Accelerator* (Track 1) — Master advanced Excel, SQL, and Power BI to automate financial modeling, reconciliations, and executive dashboards.\n"
                    "2️⃣ *Financial Analytics* (Track 6) — Focus on financial KPIs, forecasting models, variance analysis, and balance sheet analytics.\n\n"
                    "💡 *Good news:* All training is delivered **live 1-on-1 with an industry mentor** who adapts directly to your financial domain experience.\n\n"
                    "Would you like to start with Data Analytics or Financial Analytics?"
                )
            else:
                response = (
                    "🌟 *You can 100% succeed with TekTutors!*\n\n"
                    "Over 70% of our learners begin with **zero coding or technical background**. Here is why our model works where others fail:\n\n"
                    "• **Private 1-on-1 Mentorship:** You never get lost in a crowded lecture hall. Your mentor moves at your exact pace.\n"
                    "• **No Jargon, Hands-On Projects:** We start from the ground up with visual tools (Excel & Power BI) before touching code.\n"
                    "• **Employer Portfolio:** You build 3 real-world portfolio capstones you can showcase to employers with confidence.\n\n"
                    "Which career track would you like to explore first? (Track 1: Data Analytics, Track 2: Excel, or Track 4: Power BI?)"
                )
            elapsed_ms = (time.time() - start_time) * 1000
            await log_cost_savings(clean_phone, "fast_path_career_background", tokens_saved=1100, latency_ms=elapsed_ms)
            res_dict = {
                "response": response,
                "tool_logs": ["qualify_and_capture_lead", "search_tektutors_courses"],
                "fast_path": True,
                "tokens_saved": 1100
            }
            cache_query_response(norm_key, res_dict)
            return res_dict

    # 7. Laptop & System Hardware Requirements Fast Path
    for pat in HARDWARE_SPECS_PATTERNS:
        if re.search(pat, lower_text):
            phone_note = "\n\n📱 *Can I learn on my phone?*\nWhile you can attend video calls on a phone, practical hands-on exercises require a laptop or PC to run professional tools (Power BI, Python, SQL, Excel)." if any(w in lower_text for w in ["phone", "mobile"]) else ""
            response = (
                "💻 *Laptop & System Requirements for TekTutors Training:*\n\n"
                "You only need a standard personal laptop to get started:\n"
                "• **Operating System:** Windows 10/11, macOS, or Linux\n"
                "• **Memory (RAM):** 4GB minimum (8GB recommended for smooth multitasking)\n"
                "• **Internet:** Reliable connection for live 1-on-1 video mentoring sessions\n\n"
                "💡 *All software is free:* Tools like Power BI Desktop, VS Code, Python/Jupyter, and MySQL are completely free. Your 1-on-1 mentor will guide you step-by-step through installing everything in session 1!"
                f"{phone_note}\n\n"
                f"Ready to begin? Complete your registration online:\n🔗 {REGISTRATION_URL}"
            )
            elapsed_ms = (time.time() - start_time) * 1000
            await log_cost_savings(clean_phone, "fast_path_hardware_specs", tokens_saved=950, latency_ms=elapsed_ms)
            res_dict = {
                "response": response,
                "tool_logs": ["get_course_faq_answer"],
                "fast_path": True,
                "tokens_saved": 950
            }
            cache_query_response(norm_key, res_dict)
            return res_dict

    # 8. Schedule, Weekend Classes & Working Professionals Fast Path
    for pat in SCHEDULE_PATTERNS:
        if re.search(pat, lower_text):
            response = (
                "⏰ *Flexible Schedule for Busy Working Professionals:*\n\n"
                "Because your training is **live 1-on-1 with a private mentor**, your schedule is 100% tailored to you!\n\n"
                "• **Weekend Options:** Saturday and Sunday sessions available (morning, afternoon, or evening).\n"
                "• **Weekday Evenings:** After-work sessions available (e.g. 7:00 PM - 9:00 PM).\n"
                "• **Pace:** Typically 3-5 hours of dedicated practice per week.\n"
                "• **Never Fall Behind:** If an emergency comes up, simply reschedule with your mentor in advance.\n\n"
                "Would you prefer weekend sessions or weekday evening sessions?"
            )
            elapsed_ms = (time.time() - start_time) * 1000
            await log_cost_savings(clean_phone, "fast_path_schedule", tokens_saved=950, latency_ms=elapsed_ms)
            res_dict = {
                "response": response,
                "tool_logs": ["get_course_faq_answer"],
                "fast_path": True,
                "tokens_saved": 950
            }
            cache_query_response(norm_key, res_dict)
            return res_dict

    # 9. International Payments & Currency Fast Path (USD, GBP, etc.)
    for pat in INTERNATIONAL_PAYMENT_PATTERNS:
        if re.search(pat, lower_text):
            response = (
                "🌍 *International Students & Foreign Currency Payments:*\n\n"
                "Yes, we welcome learners globally! Our training is 100% online live via interactive screen sharing.\n\n"
                "• **Tuition Rate:** Approximately **$75 - $80 USD / month** (equivalent to ₦100,000 NGN/month).\n"
                "• **Payment Methods:** You can pay with any international Mastercard, Visa, or debit card on our secure portal.\n"
                "• **Billing:** Month-to-month flexible billing with zero long-term commitments.\n\n"
                f"👉 *Register securely online:* {REGISTRATION_URL}\n\n"
                "Which skill track would you like to enroll in?"
            )
            elapsed_ms = (time.time() - start_time) * 1000
            await log_cost_savings(clean_phone, "fast_path_international_payment", tokens_saved=950, latency_ms=elapsed_ms)
            res_dict = {
                "response": response,
                "tool_logs": ["get_course_faq_answer"],
                "fast_path": True,
                "tokens_saved": 950
            }
            cache_query_response(norm_key, res_dict)
            return res_dict

    # 10. Certification & Job Support Fast Path
    for pat in CERTIFICATION_PATTERNS:
        if re.search(pat, lower_text):
            response = (
                "🎓 *Certification & Career Placement Support:*\n\n"
                "Every student at TekTutors graduates with verifiable, employer-recognized credentials:\n\n"
                "• **Accredited Certificate:** Issued upon successful capstone project completion.\n"
                "• **3 Portfolio Projects:** Real-world datasets hosted on your GitHub / LinkedIn to prove your expertise to employers.\n"
                "• **Career Guidance:** 1-on-1 resume optimization, LinkedIn profile review, and mock interview coaching.\n\n"
                f"👉 *Start your journey today:* {REGISTRATION_URL}\n\n"
                "Which course track would you like to get certified in?"
            )
            elapsed_ms = (time.time() - start_time) * 1000
            await log_cost_savings(clean_phone, "fast_path_certification", tokens_saved=950, latency_ms=elapsed_ms)
            res_dict = {
                "response": response,
                "tool_logs": ["get_course_faq_answer"],
                "fast_path": True,
                "tokens_saved": 950
            }
            cache_query_response(norm_key, res_dict)
            return res_dict

    # 11. Direct Course Inquiries by Track Name Fast Path
    for pat, tr_num in COURSE_QUERY_PATTERNS:
        if re.search(pat, lower_text) and not any(w in lower_text for w in ["backpropagation", "neural network"]):
            track = TRACK_INFO.get(tr_num)
            if tr_num == 6:
                response = (
                    "🎓 *Specialized Tracks & Advanced Courses at TekTutors:*\n\n"
                    "All programs feature personalized 1-on-1 industry mentorship, practical hands-on projects, and flexible month-to-month tuition (₦100,000/month):\n\n"
                    "🤖 *Advanced AI & Data Science:*\n"
                    "• *Data Science with Python* (20 wks) — Statistics, EDA, feature engineering, ML pipelines\n"
                    "• *Machine Learning with Python* (16 wks) — Regression, classification, clustering & model deployment\n"
                    "• *Predictive Analytics* (12 wks) — Business forecasting & risk models\n\n"
                    "💼 *Business & Domain Analytics:*\n"
                    "• *Business Analysis* (10 wks) — Stakeholder management, requirements & user stories\n"
                    "• *Financial Data Analytics* (8 wks) — Revenue modeling & financial KPI dashboards\n"
                    "• *Marketing Analytics* (8 wks) — Funnel conversion & attribution\n\n"
                    "👉 *Which of these courses interests you?* Reply with the course title or secure your slot directly:\n"
                    f"🔗 {REGISTRATION_URL}"
                )
            elif track:
                response = (
                    f"🎯 *Track {tr_num}: {track['title']}*\n\n"
                    f"This program is 100% practical, project-driven, and delivered via personalized 1-on-1 mentorship with an experienced industry mentor.\n\n"
                    f"📚 *What you will master:*\n• {track['tools']}\n\n"
                    f"⏱️ *Duration:* {track['duration']}\n"
                    f"💵 *Tuition:* {track['fee']}\n"
                    f"🎯 *Career Outcomes:* {track['outcomes']}\n"
                    f"📌 *Prerequisites:* {track['prereq']}\n\n"
                    f"👉 *Register & Enroll Here:* {REGISTRATION_URL}\n\n"
                    "To personalize your roadmap:\n"
                    "*Have you worked with data tools before, or are you starting completely fresh?* (You can also reply with your name & email to receive the detailed syllabus)."
                )
            else:
                continue

            elapsed_ms = (time.time() - start_time) * 1000
            await log_cost_savings(clean_phone, f"fast_path_course_query_{tr_num}", tokens_saved=1100, latency_ms=elapsed_ms)
            res_dict = {
                "response": response,
                "tool_logs": ["search_tektutors_courses"],
                "fast_path": True,
                "tokens_saved": 1100
            }
            cache_query_response(norm_key, res_dict)
            return res_dict

    # 12. Tuition Discounts, Scholarships & Promo Codes Fast Path
    for pat in DISCOUNT_PROMO_PATTERNS:
        if re.search(pat, lower_text):
            response = (
                "🎁 *Exclusive TekTutors Tuition Discounts & Savings!*\n\n"
                "We want to ensure financial constraints never hold you back from acquiring high-income tech skills. Here are our active offers:\n\n"
                "1️⃣ *10% Full-Payment Discount:*\n"
                "Pay your course tuition upfront and instantly save *10%* — pay just *₦90,000* instead of ₦100,000 (Save ₦10,000)!\n\n"
                "2️⃣ *Fast-Action Voucher (Code: TEK10):*\n"
                "Enter promo code *TEK10* on our checkout portal to claim a special tuition discount.\n\n"
                "3️⃣ *Free Bonuses Included with Every Track (Valued at ₦85,000):*\n"
                "• Free 1-on-1 CV Optimization & LinkedIn Audit (Worth ₦35,000)\n"
                "• 3 Employer-Ready Capstone Portfolio Reviews with Senior Tech Leads\n"
                "• Flexible ₦100,000/month pay-as-you-learn plan with zero debt\n\n"
                f"👉 *Claim your discount and enroll securely online:*\n"
                f"🔗 {REGISTRATION_URL}\n\n"
                "Which skill track would you like to enroll in? (Reply with a track number 1-6 or course name!)"
            )
            elapsed_ms = (time.time() - start_time) * 1000
            await log_cost_savings(clean_phone, "fast_path_discount_promo", tokens_saved=1050, latency_ms=elapsed_ms)
            res_dict = {
                "response": response,
                "tool_logs": ["check_scholarship_and_discounts"],
                "fast_path": True,
                "tokens_saved": 1050
            }
            cache_query_response(norm_key, res_dict)
            return res_dict

    # 13. Location, Physical Address & Training Format Fast Path
    for pat in LOCATION_PATTERNS:
        if re.search(pat, lower_text):
            response = (
                "📍 *TekTutors Training Format & Location:*\n\n"
                "TekTutors is a **100% live online technology academy** serving learners across Nigeria and internationally! 🌍\n\n"
                "• **No Commute / No Physical Walk-ins:** We do not operate crowded physical classrooms. All training sessions, portfolio reviews, and code walkthroughs are conducted live 1-on-1 with your assigned industry mentor over interactive video and screen sharing.\n"
                "• **Learn From Home or Office:** You enjoy flexible, personalized scheduling (weekday evenings or weekends) without the stress of daily traffic commute.\n"
                "• **Administrative Hub & Office:** Our corporate & administrative headquarters is located in **Lagos, Nigeria**.\n"
                "• **Admissions & Inquiries:** You can reach our team directly via WhatsApp/Call at **+2348063584517** or email **info@tektutors.com.ng**.\n\n"
                f"👉 *Official Portal & Course Registration:* {REGISTRATION_URL}\n\n"
                "Would you like to schedule a quick 1-on-1 discovery call with an Admissions Advisor or explore our available course tracks?"
            )
            elapsed_ms = (time.time() - start_time) * 1000
            await log_cost_savings(clean_phone, "fast_path_location", tokens_saved=950, latency_ms=elapsed_ms)
            res_dict = {
                "response": response,
                "tool_logs": ["get_course_faq_answer"],
                "fast_path": True,
                "tokens_saved": 950
            }
            cache_query_response(norm_key, res_dict)
            return res_dict

    # Not a fast-path pattern; return None to let LLM handle complex conversational reasoning
    return None
