# TekTutors WhatsApp AI Sales Agent & Academy Management Platform

[![FastAPI](https://img.shields.io/badge/FastAPI-0.110.0-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg?logo=python)](https://python.org)
[![Groq](https://img.shields.io/badge/Groq-gpt--oss--120b-orange.svg)](https://groq.com)
[![Meta WhatsApp Cloud API](https://img.shields.io/badge/Meta%20WhatsApp-Graph%20v20.0-25D366.svg?logo=whatsapp)](https://developers.facebook.com)
[![Tests](https://img.shields.io/badge/Tests-64%2F64%20Passing-brightgreen.svg)]()
[![License](https://img.shields.io/badge/License-Proprietary-red.svg)]()

Enterprise-grade, ultra-low latency **WhatsApp AI Customer Service & Sales Platform** designed specifically for **TekTutors Academy** (AI, Data Analytics, Python, Machine Learning, Power BI, and Full-Stack Engineering).

The system acts as a 24/7 senior admissions advisor: answering technical syllabus inquiries, addressing prerequisites and non-coder doubts, overcoming pricing objections, qualifying prospective learners into a CRM funnel, booking advisor consultations, and nurturing unconverted leads through an automated **5-day morning drip campaign**.

---

## 🌟 Key Features

### 1. High-Intelligence Conversational Sales Engine
- **State-of-the-Art Reasoning**: Powered by Groq's high-speed **`openai/gpt-oss-120b`** (120B reasoning parameters) with sub-second turnaround (~0.9s–1.2s) and automatic fallback to `openai/gpt-oss-20b`.
- **Diagnostic Sales Discovery**: Discovers learner background, recommends the right track (e.g. Data Analytics vs. Machine Learning), and builds urgency without hard-selling.
- **Accurate Pricing Guardrails**: Firmly defends real academy pricing (₦100,000/month or ₦90,000 upfront discount) with zero hallucinations.

### 2. Sub-Second Latency & Zero-Cost Fast Paths
- **Zero-Token Fast Path Engine**: Frequently asked queries (course numbered menus `1`–`6`, greetings, syllabus download links, payment terms, phone vs. laptop requirements, physical Ikeja location) resolve in **< 1ms** at **$0.00 LLM cost**.
- **In-Memory TTL Caching**: Course catalog and FAQs are cached in memory with automatic cache invalidation upon dashboard updates.

### 3. Automated 5-Day Follow-Up Nurture Drip Sequence
- Automatically schedules a strategic 5-day educational email sequence once a lead is captured:
  - **Day 1**: *What Makes Us Different* (100% Live 1-on-1 Mentorship & Screen Sharing vs. 50-person crowded webinars).
  - **Day 2**: *Our Irresistible Offer* (₦100k/mo flexible tuition, ₦90k upfront discount, and free ₦35k CV/LinkedIn audit).
  - **Day 3**: *Relevance & Career ROI* (Real hiring salaries: ₦350k–₦750k/mo local, $1,500–$3,500 remote, < 3-week tuition payback).
  - **Day 4**: *Our Competitive Advantages* (3 employer-grade GitHub capstone projects and live code walkthroughs).
  - **Day 5**: *Urgency & Seat Reservation* (Mentors strictly capped at 4 students/month; deadline before cohort kickoff).
- **Smart Enrollment De-duplication**: If a student enrolls (`status == "enrolled"`), remaining scheduled drip emails are automatically cancelled.

### 4. Email Scheduling Engine
- Allows learners to request deferred material on WhatsApp (*"Please email me the curriculum tomorrow morning"* or *"Follow up with me next Monday"*).
- Admin dashboard allows scheduling custom or templated emails for future delivery with an interactive queue manager.
- Background asynchronous worker running in the FastAPI lifespan continuously queries and dispatches due emails with rate limiting.

### 5. Unified Web Control Panel & Simulator
- **Live WhatsApp Simulator**: Test conversations, tools, and qualification behavior directly in the browser without spending Meta API credits.
- **Human Escalation & Live Takeover**: Toggle "Pause AI" on any active chat to allow human advisors to step in seamlessly.
- **Lead CRM & Funnel Metrics**: Track leads across `inquiry`, `qualified`, `call_scheduled`, `invoice_sent`, and `enrolled` with one-click CSV export.
- **Marketing Campaign Broadcasts**: Segment leads by stage or course and dispatch personalized bulk emails with live HTML preview and SMTP audit logs.

---

## 🛠️ Architecture & Tech Stack

```
WhatsApp Agent v1/
├── app/
│   ├── main.py                  # FastAPI entrypoint, lifespan worker, security middleware
│   ├── config.py                # Environment configuration & sanitation
│   ├── database.py              # Async SQLAlchemy engine (PostgreSQL / SQLite)
│   ├── models.py                # Database models (Lead, Conversation, Message, Course, FAQ, ScheduledEmail)
│   ├── schemas.py               # Pydantic validation schemas
│   ├── agent.py                 # LangChain Groq agent & prompt engineering
│   ├── tools.py                 # Core tools (course search, lead capture, schedule call, schedule email)
│   ├── email_service.py         # 5-Day Drip sequence, schedule parser, worker dispatcher, Gmail SMTP
│   ├── cache.py                 # Fast-path cache routing & non-blocking cost telemetry
│   ├── whatsapp.py              # Meta Cloud API Graph v20.0 client
│   ├── webhook.py               # Webhook verification & decoupled async worker
│   └── dashboard_routes.py      # Admin control panel REST endpoints
├── templates/
│   └── dashboard.html           # Glassmorphism Admin Dashboard UI
├── static/
│   ├── css/dashboard.css        # Responsive dark theme styling
│   └── js/dashboard.js          # Live chat polling, human handoff, and schedule queue logic
├── tests/                       # 64 Automated unit and integration tests
├── HANDOVER.md                  # Comprehensive operator manual & runbook
├── RAILWAY_DEPLOYMENT_GUIDE.md  # Detailed Railway cloud deployment instructions
├── Dockerfile                   # Production container definition
├── docker-compose.yml           # Local multi-container development environment
└── requirements.txt             # Python dependencies
```

---

## 🚀 Quick Start Guide

### Prerequisites
- Python 3.10+
- Groq API Key ([console.groq.com](https://console.groq.com/))
- Meta WhatsApp Business Account ([developers.facebook.com](https://developers.facebook.com/))

### 1. Installation
```bash
git clone https://github.com/Charles-Owolabi/tektutors-whatsapp-agent-v1.git
cd tektutors-whatsapp-agent-v1

python -m venv venv
venv\Scripts\activate      # Windows
source venv/bin/activate   # Linux/macOS

pip install -r requirements.txt
```

### 2. Environment Configuration
Copy the template configuration:
```bash
cp .env.example .env
```
Fill in the required values in `.env`:
```env
GROQ_API_KEY=gsk_your_groq_key
GROQ_MODEL=openai/gpt-oss-120b

WHATSAPP_TOKEN=EAAG_your_token
WHATSAPP_PHONE_NUMBER_ID=100000000000000
WHATSAPP_VERIFY_TOKEN=tektutors_verify_token_secret
WHATSAPP_APP_SECRET=your_meta_app_secret

SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_USER=tektutorsng@gmail.com
SMTP_PASSWORD=your_16_letter_app_password
```

### 3. Run the Server
```bash
uvicorn app.main:app --reload --port 8000
```
Open `http://localhost:8000/dashboard` to access the Control Panel & Simulator.

---

## 🐳 Docker Deployment

To launch the multi-worker application with PostgreSQL using Docker:
```bash
docker compose up -d --build
```
Health checks:
```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

---

## 🧪 Automated Testing

The platform includes 64 comprehensive automated tests covering webhook security, pricing accuracy, email campaigns, scheduling, and agent tool execution.

```bash
pytest tests/ -v
```

Output:
```
======================== 64 passed in 95.24s ========================
```

---

## 📖 Operational Documentation

For complete production deployment, Meta WhatsApp Cloud API credentials setup, Gmail App Password creation, and administrative procedures, refer to:

- **[HANDOVER.md](HANDOVER.md)**: Full operator manual, API guide, and troubleshooting runbook.
- **[RAILWAY_DEPLOYMENT_GUIDE.md](RAILWAY_DEPLOYMENT_GUIDE.md)**: Step-by-step instructions for Railway cloud deployment.
