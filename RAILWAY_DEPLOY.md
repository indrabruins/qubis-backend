# Qubis Backend — Railway Deployment Guide

This guide walks you through deploying the Qubis waitlist backend on [Railway](https://railway.app) in under 10 minutes.

---

## Prerequisites

- A [Railway](https://railway.app) account (free tier works)
- A GitHub repository connected to Railway (or use Railway's GitHub integration)
- A [Resend](https://resend.com) account for email delivery (free: 100 emails/day)

---

## Step 1: Push Code to GitHub

```bash
cd ~/work/qubis
git add -A
git commit -m "Add referral system, admin stats, and improved landing page"
git push origin main
```

Your repo should contain `prelaunch/waitlist_backend.py`.

---

## Step 2: Create a New Railway Project

1. Go to [https://railway.app](https://railway.app) and log in
2. Click **New Project** → **Deploy from GitHub repo**
3. Select `indrabruins/qubis-backend` (or your repo name)
4. Railway will detect the Python app automatically

---

## Step 3: Configure the Start Command

In Railway's project settings, set the **Start Command**:

```
python prelaunch/waitlist_backend.py
```

Or use gunicorn for production:
```
gunicorn prelaunch.waitlist_backend:app -w 2 -b 0.0.0.0:5003
```

To install gunicorn, add a `requirements.txt`:

```text
flask
python-dotenv
gunicorn
```

---

## Step 4: Set Environment Variables

In Railway's Variables tab, add these:

| Variable | Value | Notes |
|---|---|---|
| `WAITLIST_API_KEY` | `your-secret-key-here` | Generate with `openssl rand -hex 32` |
| `RESEND_API_KEY` | `re_xxxxx` | From resend.com API keys |
| `RESEND_FROM` | `Qubis <hello@qubis.co>` | Must be a verified domain in Resend |
| `APP_URL` | `https://qubis-backend-production.up.railway.app` | Update after deployment |
| `PORT` | `5003` | Railway sets this automatically |
| `PYTHON_VERSION` | `3.11` | Optional, for reproducibility |

> **Important:** After your first deploy, update `APP_URL` to the actual Railway URL (e.g., `https://qubis-backend-production.up.railway.app`) so confirmation emails contain the correct links.

---

## Step 5: Health Check

Railway uses a health check to determine if the app is running. The `/health` endpoint is already configured:

```
GET /
```

The endpoint returns `{"status": "ok", "service": "qubis-waitlist"}` on port 5003.

In Railway's settings:
- **Health Check Path:** `/health`
- **Health Check Port:** `5003`

---

## Step 6: Custom Domain (qubis.co)

Once you own `qubis.co`:

1. In Railway project → **Settings** → **Networking** → **Custom Domains**
2. Add `qubis.co` and `www.qubis.co`
3. In your DNS provider, add a CNAME record pointing to your Railway proxy:
   ```
   CNAME  qubis.co  →  qubis-backend-production.up.railway.app
   CNAME  www.qubis.co  →  qubis-backend-production.up.railway.app
   ```
4. Wait ~5 minutes for SSL certificate provisioning (Railway handles this automatically)
5. Update `APP_URL` in Railway variables to `https://qubis.co`

---

## Step 7: Update Landing Page

Update `index.html` to point to your Railway URL instead of localhost:

```javascript
// Replace:
var res = await fetch('https://qubis-backend-production.up.railway.app/subscribe', {...});

// With your custom domain when ready:
var res = await fetch('https://qubis.co/subscribe', {...});
```

Also update the `/count` fetch URL.

---

## API Reference

Base URL: `https://qubis-backend-production.up.railway.app`

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/health` | GET | None | Health check |
| `/subscribe` | POST | None | Add email to waitlist |
| `/confirm` | GET | None | Confirm email (click link) |
| `/count` | GET | None | Get waitlist count |
| `/referrals/<code>` | GET | None | Get referral stats |
| `/stats` | GET | API_KEY | Full stats with referral metrics |
| `/admin/stats` | GET | API_KEY | Full analytics dashboard |
| `/export` | GET | API_KEY | Download CSV |

### Subscribe Payload

```json
{
  "email": "user@example.com",
  "source": "landing-page",
  "referred_by": "ABC123"   // optional
}
```

### Subscribe Response

```json
{
  "message": "You are on the list! Check your inbox to confirm.",
  "count": 123,
  "referral_code": "XYZ789"
}
```

### Admin Stats Response

```json
{
  "generated_at": "2026-04-01T00:00:00Z",
  "waitlist": {
    "total": 500,
    "confirmed": 340,
    "pending": 160,
    "confirmation_rate": 68.0
  },
  "email": {
    "sent": 500,
    "opened": 287,
    "open_rate": 57.4
  },
  "referrals": {
    "top_10": [
      {"referral_code": "XYZ789", "email": "user@example.com", "confirmed_referrals": 12}
    ]
  },
  "signups_by_day": [
    {"day": "2026-03-25", "count": 23}
  ],
  "sources": [
    {"source": "landing-page", "count": 400}
  ]
}
```

### Auth Header (for protected endpoints)

```
Authorization: Bearer <WAITLIST_API_KEY>
```

---

## Troubleshooting

### "Address already in use" on Railway
Railway sets `PORT` env var. Make sure your app uses `PORT` from env:
```python
PORT = int(os.environ.get("PORT", 5003))
```

### Emails not sending
1. Check `RESEND_API_KEY` is set correctly in Railway variables
2. Verify the sender domain is verified in [Resend](https://resend.com/domains)
3. Check Railway logs: click on the deployment → Logs tab

### 500 errors on endpoints
1. Check Railway logs for Python tracebacks
2. Make sure the DB migration ran (it runs automatically on startup)
3. Verify `APP_URL` is set correctly (required for confirmation links)

### Database persistence
Railway's ephemeral filesystem means the SQLite DB may be reset on redeploy. For production:
- Use Railway's **Persistent Disks** (add a volume mounted at the DB directory)
- Or migrate to PostgreSQL (change `DATABASE` connection string)

To add a persistent disk:
1. Railway dashboard → your project → **Storage** → **Add Persistent Disk**
2. Mount at `/data` or similar
3. Set `DATABASE = os.environ.get("DATABASE_PATH", "/data/waitlist.db")`

### Cold starts
Railway's free tier spins down after inactivity. First request may take ~30s. Use a uptime monitor (e.g., UptimeRobot) to keep it warm, or upgrade to Hobby tier (~$5/mo).

### Debug mode
Remove `debug=True` from `app.run()` for production. Use gunicorn instead.

---

## Recommended: Production Gunicorn Setup

Create `prelaunch/gunicorn.conf.py`:

```python
bind = f"0.0.0.0:{os.environ.get('PORT', 5003)}"
workers = 2
accesslog = "-"
errorlog = "-"
```

Then start with:
```
gunicorn -c prelaunch/gunicorn.conf.py prelaunch.waitlist_backend:app
```
