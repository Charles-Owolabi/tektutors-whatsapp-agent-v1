# 🚀 TekTutors WhatsApp AI Sales Agent — Railway Deployment Guide

This guide walks you through deploying the **TekTutors WhatsApp AI Sales Agent & Email Engine** to **[Railway.app](https://railway.app)** in under 10 minutes.

Railway keeps your service permanently awake (preventing Meta webhook timeouts) and includes an integrated PostgreSQL database.

---

## Step 1: Push Your Code to GitHub

If your project is not yet on GitHub:

1. Open a terminal in your project directory:
   ```bash
   git init
   git add .
   git commit -m "feat: production ready WhatsApp AI sales agent & email engine"
   ```
2. Create a new repository on [GitHub.com](https://github.com/new) (e.g., `tektutors-whatsapp-agent`).
3. Link and push your repository:
   ```bash
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/tektutors-whatsapp-agent.git
   git push -u origin main
   ```

---

## Step 2: Create a Project on Railway

1. Go to **[Railway.app](https://railway.app)** and log in using your GitHub account.
2. Click the **"+ New Project"** button.
3. Select **"Deploy from GitHub repo"**.
4. Choose your repository (`tektutors-whatsapp-agent`).
5. Click **"Deploy Now"**.

---

## Step 3: Add Managed PostgreSQL Database

1. In your Railway project canvas, click the **"+ Create"** or **"+ New"** button.
2. Select **"Database"** $\rightarrow$ **"Add PostgreSQL"**.
3. Railway will provision a dedicated PostgreSQL database container in a few seconds.

Railway automatically creates a `DATABASE_URL` variable linked to your database!

---

## Step 4: Configure Environment Variables

1. Click on your **Web Service** card (not the database card).
2. Go to the **"Variables"** tab.
3. Click **"RAW Editor"** in the top-right corner.
4. Paste the following configuration (replacing with your real keys from your `.env`):

```env
APP_ENV=production
DEBUG=False
PORT=8000
WORKERS=1
ALLOWED_ORIGINS=*
WEBHOOK_VERIFY_SIGNATURE_STRICT=True

# Groq LLM Inference
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=qwen/qwen3.8-27b

# Meta WhatsApp Cloud API
WHATSAPP_TOKEN=your_whatsapp_system_user_token
WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id
WHATSAPP_VERIFY_TOKEN=tektutors_verify_token_secret
WHATSAPP_APP_SECRET=your_meta_app_secret

# Connect Railway PostgreSQL (Reference Railway Variable)
DATABASE_URL=${{Postgres.DATABASE_URL}}

# Live Gmail SMTP (Encrypted SSL)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_USER=tektutorsng@gmail.com
SMTP_PASSWORD=your_16_letter_app_password
SMTP_FROM_EMAIL=tektutorsng@gmail.com
SMTP_FROM_NAME=TekTutors
SMTP_USE_TLS=False
```

> [!TIP]
> Notice `${{Postgres.DATABASE_URL}}`: Railway will automatically route your web app to your private PostgreSQL instance. Our database adapter automatically converts `postgres://` to `postgresql+asyncpg://` behind the scenes.

5. Click **Save** or **Update**. Railway will automatically trigger a new deployment.

---

## Step 5: Generate a Public Domain

1. In your Web Service on Railway, go to the **"Settings"** tab.
2. Scroll down to the **"Public Networking"** section.
3. Click **"Generate Domain"**.
4. Railway will assign a permanent public HTTPS URL (e.g. `https://tektutors-whatsapp-agent-production.up.railway.app`).

---

## Step 6: Verify Deployment Health

Open your generated Railway domain in your browser to verify:

| Endpoint | Expected Result | Purpose |
| :--- | :--- | :--- |
| `https://YOUR_DOMAIN/health` | `{"status": "healthy", ...}` | Liveness check |
| `https://YOUR_DOMAIN/ready` | `{"status": "ready", "database": "ok", "groq_engine": "configured"}` | Readiness check |
| `https://YOUR_DOMAIN/dashboard` | Executive Dashboard & Simulator | Live Admin Panel |

---

## Step 7: Connect Meta WhatsApp Webhook

Now that your production server is live on public HTTPS:

1. Open the **[Meta for Developers Console](https://developers.facebook.com/)**.
2. Select your WhatsApp Business App $\rightarrow$ **WhatsApp** $\rightarrow$ **Configuration**.
3. Under the **Webhook** section, click **Edit**:
   - **Callback URL**: `https://YOUR_RAILWAY_DOMAIN/webhook`
   - **Verify Token**: `tektutors_verify_token_secret` (matches `WHATSAPP_VERIFY_TOKEN`)
4. Click **"Verify and Save"**.
5. Under **Webhook fields**, click **Manage** and make sure you are subscribed to **`messages`**.

---

## 🎉 Congratulations!

Your **TekTutors WhatsApp AI Sales Agent** and **Email Conversion Engine** is now live in production!

* Inquiries to your WhatsApp Business number will receive AI responses in ~0.4s.
* Leads, consultation appointments, and conversations are stored in PostgreSQL.
* Live curriculum emails and campaign follow-ups dispatch through your configured Gmail SMTP server.
* You can manage the CRM, send 1-click email broadcasts, and inspect audit logs directly on your live Railway dashboard.
