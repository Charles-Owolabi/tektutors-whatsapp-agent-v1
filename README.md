# TekTutors WhatsApp AI Customer Service & Sales Agent

Enterprise-grade, low-cost **WhatsApp AI Sales & Customer Support Agent** built for **TekTutors** (AI & Data Analytics Training Academy).

The agent automatically responds to WhatsApp inquiries, answers course questions, overcomes objections (e.g. non-coders, payment installment plans), qualifies prospective students, captures leads into Supabase/PostgreSQL, and escalates hot leads to human admissions advisors via a built-in web dashboard.

---

## 🛠️ Core Tech Stack

- **Backend & Webhooks**: Python **FastAPI** (Async ASGI engine)
- **AI Engine & Orchestration**: **LangChain** + **Groq**
- **Database**: **Supabase / PostgreSQL** (SQLAlchemy Async ORM with SQLite auto-fallback for local development)
- **WhatsApp Integration**: **Meta WhatsApp Business Cloud API** (Graph API v20.0)
- **Web Interface**: **TekTutors Control Panel & Browser WhatsApp Simulator** (Live Human Handoff, Leads CRM, Course KB)

---

## 🚀 Quick Start Guide (Local Development)

### 1. Install Dependencies
Ensure Python 3.10+ is installed.
```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Edit `.env` with your Groq API key and Meta credentials:
```env
GROQ_API_KEY=gsk_...
GROQ_MODEL=llama-3.3-70b-versatile

WHATSAPP_TOKEN=EAAG...
WHATSAPP_PHONE_NUMBER_ID=100000...
WHATSAPP_VERIFY_TOKEN=tektutors_verify_token_secret

# Supabase / PostgreSQL or local SQLite fallback
DATABASE_URL=sqlite+aiosqlite:///./tektutors.db
```

### 3. Run the FastAPI Application
```bash
python app/main.py
```
Or with uvicorn:
```bash
uvicorn app.main:app --reload --port 8000
```

### 4. Access Web Admin Dashboard & Browser Simulator
Open `http://localhost:8000/dashboard` in your browser.

You can instantly test talking to the **TekTutors AI Sales Agent** using the interactive **WhatsApp Browser Simulator** without needing Meta API keys right away!

---

## 📲 Meta WhatsApp Business Cloud API Setup

1. **Meta Developer Console**:
   - Go to [Meta for Developers](https://developers.facebook.com/) and create a **Business App**.
   - Add **WhatsApp** product to your app.

2. **Retrieve Credentials**:
   - Copy **Temporary / Permanent Access Token** to `WHATSAPP_TOKEN`.
   - Copy **Phone Number ID** to `WHATSAPP_PHONE_NUMBER_ID`.

3. **Expose Local Server to Public Internet (ngrok / Cloudflare Tunnel)**:
   ```bash
   ngrok http 8000
   ```
   Copy the https URL (e.g. `https://abc1234.ngrok-free.app`).

4. **Configure Webhook in Meta Console**:
   - **Callback URL**: `https://abc1234.ngrok-free.app/webhook`
   - **Verify Token**: `tektutors_verify_token_secret` (matches `WHATSAPP_VERIFY_TOKEN` in `.env`)
   - Subscribe to **`messages`** webhook field.

---

## 🗄️ Supabase / PostgreSQL Setup

To use Supabase in production:
1. Create a database on [Supabase.com](https://supabase.com/).
2. Under Project Settings -> Database -> Connection String (URI), copy the URI string.
3. Update `DATABASE_URL` in `.env`:
   ```env
   DATABASE_URL=postgresql+asyncpg://postgres:YOUR_PASSWORD@db.xxxx.supabase.co:5432/postgres
   ```
4. On application launch, FastAPI will automatically create the tables (`leads`, `conversations`, `messages`, `courses`, `faqs`, `appointments`) and seed TekTutors course data!

---

## 🧪 Running Automated Tests

Run pytest to execute all 46 enterprise test suites covering production readiness, security headers, tool calling, accuracy, and latency:
```bash
pytest
```

---

## 🚀 Enterprise Production Deployment & Scaling

### Option A: One-Command Docker Compose (Recommended)
Spin up the complete production stack (FastAPI Multi-Worker Agent + PostgreSQL with healthchecks):
```bash
docker compose up -d --build
```
Check health:
```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

### Option B: Cloud Hosting (Render, Railway, Fly.io, AWS ECS, Heroku)
The project includes a production-ready `Procfile` and `Dockerfile`:
1. Set the environment variables in your cloud dashboard according to `.env.example`.
2. Ensure `APP_ENV=production` and `WEBHOOK_VERIFY_SIGNATURE_STRICT=True`.
3. Set your Meta webhook callback to `https://your-domain.com/webhook`.
4. Point your cloud health check monitor to `https://your-domain.com/health`.

### ⚡ Sub-Second Latency & Affordability Architecture
- **Inference Speed**: Powered by Groq's high-speed LPU inference engine (`qwen/qwen3.8-27b`) delivering ~0.4s LLM turnaround time.
- **Zero-Cost Fast Path**: High-frequency queries (greetings, course menu 1-6, registration links, and common FAQ inquiries) resolve instantly in under 5ms at $0.00 token cost.
- **In-Memory Configuration Caching**: Dynamic system prompts and tone configurations are cached in-memory with automatic cache invalidation on updates, eliminating per-message database overhead.
- **Immediate Webhook Delivery**: WhatsApp webhooks return HTTP 200 immediately to Meta, completely preventing webhook retries or timeouts.
- **Hardened Security**: Includes `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and HMAC SHA-256 Meta webhook signature validation.

---

## 🏛️ Project Architecture

```
WhatsApp Agent v1/
├── app/
│   ├── main.py                  # FastAPI app entrypoint & db seed
│   ├── config.py                # Pydantic configuration & env vars
│   ├── database.py              # Async SQLAlchemy engine (Supabase/Postgres/SQLite)
│   ├── models.py                # Database models (Lead, Conversation, Message, Course, FAQ)
│   ├── schemas.py               # Pydantic schemas
│   ├── whatsapp.py              # Meta WhatsApp Business Cloud API client
│   ├── webhook.py               # Webhook verification & incoming payload router
│   ├── agent.py                 # LangChain ChatGroq agent setup & prompt engine
│   ├── tools.py                 # TekTutors sales tools (course search, lead capture, FAQ, advisor call)
│   ├── data.py                  # Default TekTutors course & FAQ seed dataset
│   └── dashboard_routes.py      # Control Panel & Simulator REST endpoints
├── templates/
│   └── dashboard.html           # Sleek Web Admin Dashboard & Simulator UI
├── static/
│   ├── css/dashboard.css        # Premium dark glassmorphism styling
│   └── js/dashboard.js          # Live chat polling, human handoff toggle & simulator logic
├── tests/                       # Pytest test suite
├── requirements.txt             # Dependency list
└── README.md                    # Project documentation
```
