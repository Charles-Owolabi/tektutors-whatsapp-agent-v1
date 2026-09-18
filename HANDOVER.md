# TekTutors WhatsApp AI Sales Agent — Production Handover Manual & Runbook

**Version:** 1.0.0 (Commercial Production Release)  
**Author:** Antigravity AI Engineering  
**Repository:** `Charles-Owolabi/tektutors-whatsapp-agent-v1`  
**Target Platform:** Railway / Docker / PostgreSQL / Meta Cloud API  

---

## 1. System Overview & Executive Summary

The **TekTutors WhatsApp AI Sales & Academy Management Agent** is an autonomous, commercial-grade AI sales representative and marketing automation suite tailored for **TekTutors** (Data Science, Machine Learning, Power BI, Python, and Full-Stack training programs).

### Core Capabilities
1. **Commercial Conversational AI**:
   - Powered by Groq's high-speed **`openai/gpt-oss-120b`** (120B reasoning model) with automatic fallback to `openai/gpt-oss-20b`.
   - Sub-second to ~1.1s turnaround time for lightning-fast WhatsApp replies.
   - Consultative sales methodology: asks diagnostic questions, qualifies career goals, overcomes non-coder & pricing objections, and drives leads toward booking an advisor call or enrolling.
2. **Zero-Cost Fast-Path Cache Engine**:
   - Common high-frequency queries (greetings, course numbered menus `1`–`6`, syllabus requests, payment terms, phone-vs-laptop requirements, and physical location) resolve instantly in **< 1ms** at **$0.00 token cost**.
3. **Automated 5-Day Nurture Drip Campaign**:
   - Automatically enrolls captured leads in a value-packed 5-day email sequence (Day 1: 1-on-1 Mentorship Difference; Day 2: Irresistible Offer & Tuition Bonus; Day 3: Market Relevance & Salary ROI; Day 4: 3 Employer Capstone Projects; Day 5: Mentor Reservation Urgency).
   - Intelligently cancels remaining pending emails once a student officially enrolls.
4. **Email Scheduling & Broadcast Suite**:
   - Schedule one-off or sequence emails from both WhatsApp ("send me the syllabus tomorrow morning") and the Admin Dashboard.
   - Built-in rich HTML email engine with Gmail SSL (Port 465) integration.
   - Categorized templates (conversion, follow-up, marketing, promotional).
5. **Human Escalation & Live Chat Takeover**:
   - Seamless human handoff toggle in the web dashboard.
   - When an advisor pauses AI mode, the human advisor can chat directly with the student via WhatsApp.
6. **Built-in Interactive WhatsApp Simulator**:
   - Complete browser-based WhatsApp simulation to test prompts, lead qualification, and tools without sending billable Meta messages.

---

## 2. Architecture & Data Flow

```mermaid
flowchart TD
    User([WhatsApp User]) -->|Incoming Message| Meta[Meta Cloud API Graph v20.0]
    Meta -->|HTTP POST Webhook| FastAPI[FastAPI Webhook /webhook]
    
    FastAPI --> Security[HMAC SHA-256 Signature Verification]
    Security --> FastPath{Fast-Path Match?}
    
    FastPath -->|Yes: Greeting / Menu / Price / Location| ZeroCost[Instant Response < 1ms at $0.00 Cost]
    FastPath -->|No: Complex Consultation| Agent[LangChain Groq Agent: gpt-oss-120b]
    
    Agent --> Tools[Agent Tools]
    Tools --> CourseKB[(Course & FAQ Catalog)]
    Tools --> LeadCRM[(Leads & Appointments DB)]
    Tools --> DripQueue[(ScheduledEmail Queue)]
    
    DripQueue --> Worker[Async Background Dispatcher (60s)]
    Worker --> SMTP[Gmail SMTP SSL Port 465]
    SMTP --> StudentEmail([Student Inbox])
    
    ZeroCost --> Outbound[Meta Graph API Outbound]
    Agent --> Outbound
    Outbound --> User
    
    Admin([Admissions Staff]) --> Dashboard[Web Control Panel /dashboard]
    Dashboard --> LeadCRM
    Dashboard --> DripQueue
    Dashboard --> Simulator[WhatsApp Simulator]
```

---

## 3. Environment Configuration & Secrets

All settings are configured via environment variables (or `.env` in local development).

| Environment Variable | Description | Production Recommendation / Example | Required |
|:---|:---|:---|:---:|
| `GROQ_API_KEY` | Groq Console API Key | `gsk_...` | **Yes** |
| `GROQ_MODEL` | High-speed LLM model | `openai/gpt-oss-120b` | **Yes** |
| `WHATSAPP_TOKEN` | Meta System User Access Token | `EAAG...` (Permanent) | **Yes** |
| `WHATSAPP_PHONE_NUMBER_ID` | Meta WhatsApp Business Phone Number ID | `100000000000000` | **Yes** |
| `WHATSAPP_VERIFY_TOKEN` | Secret token for Meta webhook verification | `tektutors_verify_token_secret` | **Yes** |
| `WHATSAPP_APP_SECRET` | Meta App Secret for HMAC SHA-256 header validation | `your_meta_app_secret_here` | **Yes** |
| `DATABASE_URL` | PostgreSQL or Supabase Connection URI | `postgresql+asyncpg://user:pass@host:5432/db` | **Yes** |
| `SMTP_HOST` | Outbound Mail Server Host | `smtp.gmail.com` | **Yes** |
| `SMTP_PORT` | Outbound Mail Server Port | `465` (SSL recommended over 587) | **Yes** |
| `SMTP_USER` | SMTP Username / Gmail Account | `tektutorsng@gmail.com` | **Yes** |
| `SMTP_PASSWORD` | 16-character Google App Password | `xxxx xxxx xxxx xxxx` | **Yes** |
| `SMTP_FROM_EMAIL` | Sender Email Header | `tektutorsng@gmail.com` | **Yes** |
| `SMTP_FROM_NAME` | Sender Display Name | `TekTutors Academy` | **Yes** |
| `SMTP_USE_TLS` | SSL vs TLS selector | `False` (when using Port 465) | **Yes** |
| `APP_ENV` | Application Environment | `production` | **Yes** |
| `DEBUG` | Debug logging toggle | `False` | No |
| `WEBHOOK_VERIFY_SIGNATURE_STRICT` | Enforce Meta HMAC signature checking | `True` | **Yes** |
| `PORT` | Web Server Port | `8000` (or injected by Railway) | No |
| `WORKERS` | Uvicorn Worker Count | `2` (recommended for production) | No |

---

## 4. Third-Party Setup Runbooks

### 4.1 Meta WhatsApp Business Cloud API
1. Log in to [Meta for Developers](https://developers.facebook.com/).
2. Create or open your **Business App** with the **WhatsApp** product.
3. In **WhatsApp -> API Setup**:
   - Note the **Phone number ID** -> set to `WHATSAPP_PHONE_NUMBER_ID`.
   - Under **App Settings -> Basic**, copy the **App Secret** -> set to `WHATSAPP_APP_SECRET`.
4. Generate a **Permanent System User Token**:
   - Go to [Meta Business Settings](https://business.facebook.com/settings).
   - Navigate to **Users -> System Users**. Add a system user (Role: Admin).
   - Click **Generate New Token**, select your WhatsApp App, and check permissions:
     - `whatsapp_business_messaging`
     - `whatsapp_business_management`
   - Set expiration to **Never**. Copy the token -> set to `WHATSAPP_TOKEN`.
5. Configure Webhook:
   - In **WhatsApp -> Configuration**:
     - **Callback URL**: `https://your-domain.railway.app/webhook`
     - **Verify Token**: `tektutors_verify_token_secret` (matches `WHATSAPP_VERIFY_TOKEN`)
   - Click **Verify and Save**.
   - Under **Webhook Fields**, click **Manage** and subscribe to **`messages`**.

### 4.2 Google SMTP Setup (16-Character App Password)
Do not use your standard Google account login password.
1. Log in to the Google Account (`tektutorsng@gmail.com`).
2. Go to [Google Account Security](https://myaccount.google.com/security).
3. Ensure **2-Step Verification** is turned ON.
4. In the top search bar, search for **App passwords**.
5. Create a new App Password:
   - App name: `TekTutors Agent`
   - Click **Create**.
6. Google will generate a 16-character code (e.g. `abcd efgh ijkl mnop`).
7. Copy this string into `SMTP_PASSWORD` in your production environment settings (spaces are automatically stripped by the app).
8. Use `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=465`, `SMTP_USE_TLS=False`.

### 4.3 Groq Console Setup
1. Log in to [Groq Console](https://console.groq.com/).
2. Navigate to **API Keys** and create a new key.
3. Copy the key starting with `gsk_...` into `GROQ_API_KEY`.
4. Set `GROQ_MODEL=openai/gpt-oss-120b`.

---

## 5. Deployment Options

### Option A: Railway (Active Production Setup)
1. The repository is connected to Railway (`main` branch).
2. Every `git push origin main` triggers an automatic container build and zero-downtime rolling restart.
3. Database: If using Railway's built-in PostgreSQL, add a **Postgres Database** service in the Railway canvas. The `DATABASE_URL` is automatically wired.

### Option B: Docker Compose (Self-Hosted / VPS)
Run on any Ubuntu/Debian VPS with Docker installed:
```bash
# 1. Clone repository
git clone https://github.com/Charles-Owolabi/tektutors-whatsapp-agent-v1.git
cd tektutors-whatsapp-agent-v1

# 2. Setup environment
cp .env.example .env
nano .env

# 3. Start PostgreSQL and FastAPI
docker compose up -d --build

# 4. Verify running services
docker compose ps
curl http://localhost:8000/health
```

### Option C: Local Development with Python
```bash
# 1. Create and activate virtual environment
python -m venv venv
venv\Scripts\activate     # Windows
source venv/bin/activate  # Linux/macOS

# 2. Install dependencies
pip install -r requirements.txt

# 3. Launch server
uvicorn app.main:app --reload --port 8000
```
Visit `http://localhost:8000/dashboard` in your browser.

---

## 6. Admin Dashboard Operations Manual

Access the Control Panel at `/dashboard` (or `https://your-domain.railway.app/dashboard`).

### 6.1 WhatsApp Simulator
- On the right pane of the dashboard, click **Open Simulator**.
- Send any test message (e.g. *"Tell me about Machine Learning"*, *"How much is Data Analytics?"*, *"Can I pay in installments?"*).
- Verify the AI responses, tool invocations, and qualification behavior without incurring Meta messaging costs.

### 6.2 Leads CRM & Funnel Management
- Navigate to **Leads Management**.
- View leads grouped by status:
  - `inquiry`: Initial interaction.
  - `qualified`: Lead provided name/email/course preference.
  - `call_scheduled`: Lead booked a call with an advisor.
  - `invoice_sent`: Payment link / checkout invoice generated.
  - `enrolled`: Student made payment and is actively enrolled.
  - `lost`: Prospect opted out.
- Actions:
  - Click **Notes** to view conversation summaries.
  - Click **Send Email** to launch the branded quick composer.
  - Click **Export CSV** to download leads for Google Sheets or CRM import.

### 6.3 Live Human Handoff
- Navigate to **Conversations**.
- Select an active chat.
- Toggle **"Pause AI / Take Over Chat"**.
- While AI is paused, inbound WhatsApp messages will not trigger automated bot replies, allowing human advisors to chat directly with the customer.
- Toggle **"Resume AI"** when the human consultation is complete.

### 6.4 Email Marketing & Campaign Suite
- **Template Library**: Over 18 pre-written, high-converting templates covering course curriculums, cart abandonment recovery, career ROI breakdowns, and beginner transitions.
- **Audience Segmentation**: Filter recipients by Course Interest or Lead Stage.
- **Scheduled Follow-Up Email Queue**:
  - View all queued nurture drip emails (Days 1–5) and one-off scheduled deliveries.
  - Cancel any scheduled email with one click.
  - Click **"Process Due Emails Now"** to manually flush and send all due items immediately.

### 6.5 Course & FAQ Management
- Under **Course Management**, add new courses, modify durations, or update tuition prices. Changes instantly invalidate the in-memory cache and update the AI agent's responses.
- Under **FAQ Management**, add common questions and answers.

---

## 7. Health Checks, Monitoring & Maintenance

### Endpoints
- **Liveness Probe**: `GET /health`  
  Returns application name, environment, and uptime.
- **Readiness Probe**: `GET /ready`  
  Tests database connection pool, Groq configuration, WhatsApp credentials, and recent webhook health.
- **Telemetry**: `GET /api/system/stats`  
  Reports cost savings, fast-path hit rates, and total messages processed.

### Database Backups (PostgreSQL)
To take a manual backup:
```bash
pg_dump -U postgres -h <HOST> -d <DB_NAME> > tektutors_backup_$(date +%Y%m%d).sql
```

---

## 8. Troubleshooting Guide

| Issue | Likely Cause | Resolution |
|---|---|---|
| **Webhook verification returns 403** | `WHATSAPP_VERIFY_TOKEN` mismatch | Verify that the token in Meta App Console matches `WHATSAPP_VERIFY_TOKEN` in `.env`. |
| **Incoming messages rejected with 401** | HMAC SHA-256 signature invalid | Verify `WHATSAPP_APP_SECRET` in `.env` matches the App Secret under Meta Basic Settings. |
| **Outbound WhatsApp message fails** | Expired or invalid `WHATSAPP_TOKEN` | Regenerate a permanent System User Token in Meta Business Manager. |
| **Email fails with connection timeout** | Port 587 blocked by cloud host firewall | Switch `SMTP_PORT=465` and `SMTP_USE_TLS=False` (SSL connection). |
| **Gmail SMTP Authentication Error (535)** | Standard account password used instead of App Password | Generate a dedicated 16-character Google App Password in Google Account Security. |
| **AI agent gives generic responses** | Groq API Key missing or quota exceeded | Check `GROQ_API_KEY` at [Groq Console](https://console.groq.com/). The agent will use fallback mechanisms if primary models fail. |

---

## 9. Verification & Test Suite

The entire codebase is validated by **64 automated tests** covering:
- Production readiness and security headers
- Fast-path routing and token cost telemetry
- 5-Day daily drip sequence scheduling and cancellation
- Email HTML rendering and SMTP delivery
- Tool calling accuracy and pricing hallucination guards
- Human escalation and LangGraph multi-turn conversation state

Run the test suite anytime:
```bash
pytest tests/ -v
```
*(All 64 tests passing with zero failures).*
