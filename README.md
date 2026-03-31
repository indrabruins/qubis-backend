# Qubis Pre-Launch Funnel — Setup Guide

Everything you need to run the Qubis pre-launch waitlist funnel. Built for local testing and production deployment.

---

## Project Structure

```
prelaunch/
  index.html            ← Landing page (serves as static file)
  waitlist_backend.py   ← Flask API (subscribe, count, export, confirm)
  waitlist.db           ← SQLite database (created automatically)
  EMAIL_SEQUENCE.md     ← 5-email drip campaign copy
  README.md             ← This file
  .env                  ← Environment variables (create this)
```

---

## Quick Start (Local Development)

### 1. Install Dependencies

```bash
pip install flask python-dotenv
```

### 2. Set Environment Variables

Create a `.env` file in `prelaunch/`:

```bash
# Required: secret key for the /export and /stats endpoints
WAITLIST_API_KEY=change-me-to-a-strong-random-string

# Optional: Resend API for real confirmation emails
# Get your key at https://resend.com — free tier: 100 emails/month
RESEND_API_KEY=re_your_key_here
RESEND_FROM=Qubis <hello@qubis.co>

# URL of your backend (used in confirmation email links)
# For local dev, use http://localhost:5003
# For production, use your deployed URL (e.g., https://api.qubis.co)
APP_URL=http://localhost:5003
```

### 3. Start the Backend

```bash
cd ~/work/qubis/prelaunch
python3 waitlist_backend.py
```

You should see:
```
  Qubis Waitlist Backend
  ─────────────────────────
  Port:     5003
  DB:       waitlist.db
  API Key:  change-me-to-a-strong-random-string
  ─────────────────────────
```

### 4. Open the Landing Page

Open `index.html` directly in your browser, or serve it:

```bash
# Option A: just open the file directly
open ~/work/qubis/prelaunch/index.html

# Option B: serve with Python (recommended — avoids CORS issues)
cd ~/work/qubis/prelaunch && python3 -m http.server 8080
# Then visit http://localhost:8080
```

> **Note:** The landing page submits to `http://localhost:5003`. If deploying to production, update the `fetch()` URL in `index.html` to point to your production backend URL.

---

## API Reference

All endpoints return JSON unless noted.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/subscribe` | Add email to waitlist |
| `GET`  | `/confirm` | Confirm email via token (link handler) |
| `GET`  | `/count` | Get total waitlist count |
| `GET`  | `/export` | Export CSV (requires API key) |
| `GET`  | `/stats` | Dashboard stats (requires API key) |
| `GET`  | `/health` | Health check |

### `POST /subscribe`

```bash
curl -X POST http://localhost:5003/subscribe \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "source": "landing-page"}'
```

**Response 201 (new signup):**
```json
{"message": "You are on the list! Check your inbox to confirm.", "count": 2848}
```

**Response 200 (duplicate):**
```json
{"message": "You are already on the list!", "count": 2848}
```

**Response 400 (invalid email):**
```json
{"error": "Please provide a valid email address."}
```

### `GET /count`

```bash
curl http://localhost:5003/count
```
```json
{"count": 2847}
```

### `GET /export`

```bash
curl http://localhost:5003/export \
  -H "Authorization: Bearer your-api-key"
```
Returns a CSV file download.

### `GET /stats`

```bash
curl http://localhost:5003/stats \
  -H "Authorization: Bearer your-api-key"
```
```json
{
  "total": 142,
  "confirmed": 98,
  "pending": 44,
  "confirmation_rate": 69.0,
  "recent_signups": [...]
}
```

---

## Connecting Resend (Real Confirmation Emails)

1. Get a Resend API key at [resend.com](https://resend.com) (free tier: 100 emails/month)
2. Add it to your `.env`:
   ```bash
   RESEND_API_KEY=re_your_key_here
   RESEND_FROM=Qubis <hello@qubis.co>
   ```
3. Restart the backend. New signups will receive real confirmation emails.
4. For bulk sending the 5-email sequence, see the email sequence guide below.

> **DMARC/SPF note:** If sending from `@qubis.co`, configure DNS records for Resend. Resend provides automatic DNS setup instructions in your dashboard under Domain Verification.

---

## Deploying to Production

### Option A: Railway (Recommended for Flask)

1. Go to [railway.app](https://railway.app) and create an account
2. New Project → Deploy from GitHub (push this repo to GitHub first)
3. Set environment variables in Railway dashboard:
   - `WAITLIST_API_KEY`
   - `RESEND_API_KEY`
   - `RESEND_FROM`
   - `APP_URL` (e.g., `https://api.qubis.co`)
4. Railway auto-detects Flask and starts on port `5003`
5. Note your deployed URL (e.g., `https://qubis-waitlist.up.railway.app`)

### Option B: Render

1. Go to [render.com](https://render.com) → New → Web Service
2. Connect GitHub repo
3. Settings:
   - **Build Command:** `pip install -r requirements.txt` (create a `requirements.txt` with `flask`, `python-dotenv`)
   - **Start Command:** `python3 waitlist_backend.py`
   - **Environment:** Python 3
4. Add environment variables in the dashboard
5. Set `APP_URL` to your Render URL

### Option C: Vercel (Serverless)

Vercel is not ideal for Flask's persistent server model. Use Railway or Render instead.

### Option D: Fly.io

```bash
fly launch
fly secrets set WAITLIST_API_KEY=your-key RESEND_API_KEY=your-key
fly deploy
```

---

## Serving the Landing Page

### Option 1: Netlify (Recommended)

1. Drag the `prelaunch/` folder to [netlify.com/drop](https://netlify.com/drop)
2. Or connect to GitHub and deploy automatically
3. Update the `fetch()` URL in `index.html` to your backend URL:
   ```javascript
   // Change this:
   fetch('http://localhost:5003/subscribe', {...})
   // To this (production):
   fetch('https://your-backend-url.railway.app/subscribe', {...})
   ```

### Option 2: GitHub Pages

1. Push `index.html` to a GitHub repo
2. Enable GitHub Pages in repo Settings → Pages
3. Update backend URL to match

### Option 3: Cloudflare Pages

Free, fast, global CDN. Upload the `index.html` and set up a redirect rule to your backend API.

---

## Adding Your Link to Instagram / TikTok Bio

### Instagram
1. Go to your profile → **Edit Profile**
2. Under "Website," paste your landing page URL (e.g., `https://qubis.co` or your Netlify URL)
3. In your bio, add a call-to-action: `Early access link in bio 👆` or `AI fitness coach — waitlist in bio 🔥`

### TikTok
1. Go to **Edit Profile** → Website
2. Add your landing page URL
3. Pin a comment on your most viewed video: `Link in bio — join the Qubis waitlist`

### Linktree (Recommended for Multi-Platform)

Create a Linktree at [linktr.ee](https://linktr.ee):
- Qubis Waitlist → your landing page URL
- Instagram → instagram.com/qubisapp
- TikTok → tiktok.com/@qubisapp

---

## Exporting the Waitlist

### From the API (anytime)
```bash
curl http://localhost:5003/export \
  -H "Authorization: Bearer your-api-key" \
  -o qubis-waitlist.csv
```

### From the Database (direct SQLite)
```bash
sqlite3 waitlist.db \
  "SELECT email, status, source, created_at FROM waitlist ORDER BY created_at;"
```

### Import to Email Platform

| Platform | How to Import |
|----------|---------------|
| **ConvertKit** | Settings → Import → Upload CSV |
| **Mailchimp** | Audience → Import → Upload CSV |
| **Resend** | Contacts → Import → Upload CSV |
| **Loops.so** | Import → Upload CSV |

---

## Updating the Social Proof Counter

The displayed waitlist count is: **DB count + 2847** (the hardcoded offset).

To change the offset, edit `waitlist_backend.py`:

```python
# Line ~170 — change this number
offset = 2847
```

To see only real signups (no offset), change `count` route to:

```python
return jsonify({"count": db_count})
```

---

## Troubleshooting

**`fetch()` CORS error in browser console:**
- The landing page must be served from the same domain as the API, or the API must have CORS headers enabled.
- For local dev, serve both from localhost: serve `index.html` with `python3 -m http.server 8080` and keep the backend on `5003`.
- For production, update the `fetch` URL in `index.html` to your deployed backend URL.

**Confirmation emails not sending:**
- Check that `RESEND_API_KEY` is set in `.env`
- Check the console/terminal where the backend is running for `[WARNING]` logs
- In dev mode (no Resend key), confirmation links are printed to the terminal

**Database locked error:**
- Only one backend instance should run at a time
- If using Gunicorn for production, use `--workers 1` to avoid SQLite locking

---

## Cron: Automated Waitlist Export

Run weekly to back up the waitlist:

```bash
# Weekly backup to Dropbox (example)
0 9 * * 1 curl -s http://localhost:5003/export \
  -H "Authorization: Bearer YOUR_KEY" \
  -o ~/Dropbox/qubis-waitlist-$(date +\%Y-\%m-\%d).csv
```

---

*Last updated: 2026-03-30 — Built for Qubis by the Kit swarm*
