"""
Qubis Pre-Launch Waitlist Backend
Flask API — stores emails in SQLite, supports Resend for confirmations
Run: python3 waitlist_backend.py  (starts on port 5003)
"""

import os
import re
import csv
import uuid
import sqlite3
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from flask import Flask, request, jsonify, Response, send_file
from dotenv import load_dotenv

# ── Config ────────────────────────────────────────────────────────────────────
load_dotenv()  # Load .env if present
DATABASE = os.path.join(os.path.dirname(__file__), "waitlist.db")
PORT = 5003
API_KEY = os.environ.get("WAITLIST_API_KEY", "qubis-secret-key-change-me")
APP_URL = os.environ.get("APP_URL", "http://localhost:5003")

# Resend config (set in environment or .env)
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
RESEND_FROM = os.environ.get("RESEND_FROM", "Qubis <hello@qubis.co>")

app = Flask(__name__)
app.json.sort_keys = False

# ── DB Setup ───────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS waitlist (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            email      TEXT    UNIQUE NOT NULL,
            source     TEXT    DEFAULT '',
            status     TEXT    DEFAULT 'pending',
            token      TEXT,
            confirmed_at TEXT,
            created_at TEXT    DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS confirmation_log (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            email     TEXT NOT NULL,
            token     TEXT NOT NULL,
            sent_at   TEXT DEFAULT (datetime('now')),
            clicked   INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

# ── Email Validation ───────────────────────────────────────────────────────────
EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")

def is_valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(email.strip()))

# ── Resend Integration ─────────────────────────────────────────────────────────
def send_confirmation_email(email: str, token: str) -> bool:
    """Send confirmation email via Resend API. Returns True on success."""
    confirm_url = f"{APP_URL}/confirm?token={token}&email={email}"

    html_body = f"""
    <div style="font-family: Inter, system-ui, sans-serif; max-width: 560px; margin: 0 auto; padding: 40px 20px; background: #080C14; color: #fff;">
      <div style="text-align: center; margin-bottom: 32px;">
        <div style="display: inline-block; width: 48px; height: 48px; background: #00D4FF; border-radius: 12px; line-height: 48px; font-size: 24px; font-weight: 900; color: #080C14;">Q</div>
        <h1 style="margin: 16px 0 8px; font-size: 28px; font-weight: 800;">You are on the list!</h1>
        <p style="color: rgba(255,255,255,0.5); margin: 0;">Confirm your email to secure your early access spot.</p>
      </div>
      <div style="background: rgba(13,21,38,0.8); border: 1px solid rgba(0,212,255,0.15); border-radius: 16px; padding: 32px; text-align: center;">
        <p style="color: rgba(255,255,255,0.7); margin: 0 0 24px; line-height: 1.6;">
          Welcome to the Qubis waitlist. You are joining thousands of people who are tired of generic fitness plans. We are building something different — and we will let you know the moment it launches.
        </p>
        <a href="{confirm_url}"
           style="display: inline-block; background: #00D4FF; color: #080C14; font-weight: 800; font-size: 16px; padding: 16px 40px; border-radius: 12px; text-decoration: none;">
          Confirm My Spot
        </a>
        <p style="color: rgba(255,255,255,0.25); font-size: 12px; margin-top: 20px;">
          If you did not sign up for Qubis, ignore this email.
        </p>
      </div>
    </div>
    """

    if RESEND_API_KEY:
        # Use Resend API
        import urllib.request
        import json
        payload = json.dumps({
            "from": RESEND_FROM,
            "to": [email],
            "subject": "Confirm your Qubis waitlist spot",
            "html": html_body
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://api.resend.com/emails",
            data=payload,
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json"
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status == 200 or resp.status == 202
        except Exception:
            return False
    else:
        # Log to console for local dev
        print(f"\n[DEV EMAIL] To: {email}")
        print(f"[DEV EMAIL] Confirm link: {confirm_url}\n")
        return True


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "qubis-waitlist"})


@app.route("/subscribe", methods=["POST"])
def subscribe():
    """Accept email submission. Returns 201 on new, 200 on duplicate, 400 on bad input."""
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    source = (data.get("source") or "").strip()

    if not email or not is_valid_email(email):
        return jsonify({"error": "Please provide a valid email address."}), 400

    conn = get_db()
    existing = conn.execute(
        "SELECT id, status FROM waitlist WHERE email = ?", (email,)
    ).fetchone()

    if existing:
        conn.close()
        # Still return success so we don't leak which emails are registered
        return jsonify({
            "message": "You are already on the list!",
            "count": _get_count()
        }), 200

    token = str(uuid.uuid4())

    conn.execute(
        "INSERT INTO waitlist (email, source, status, token) VALUES (?, ?, 'pending', ?)",
        (email, source, token)
    )
    conn.execute(
        "INSERT INTO confirmation_log (email, token) VALUES (?, ?)",
        (email, token)
    )
    conn.commit()
    conn.close()

    # Send confirmation email (non-blocking — log error but don't fail the request)
    try:
        send_confirmation_email(email, token)
    except Exception as e:
        print(f"[WARNING] Could not send confirmation email: {e}")

    return jsonify({
        "message": "You are on the list! Check your inbox to confirm.",
        "count": _get_count(get_db())
    }), 201


@app.route("/confirm", methods=["GET"])
def confirm():
    """Email confirmation link handler. Marks email as confirmed."""
    token = request.args.get("token", "").strip()
    email = request.args.get("email", "").strip().lower()

    if not token or not email:
        return """
        <html><body style="font-family:Inter,system-ui,sans-serif;background:#080C14;color:#fff;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;">
          <div style="text-align:center;padding:40px;">
            <h1 style="color:#ff4444;">Invalid confirmation link.</h1>
            <p style="color:rgba(255,255,255,0.5);">Please contact hello@qubis.co if you need assistance.</p>
          </div>
        </body></html>
        """, 400, {"Content-Type": "text/html"}

    conn = get_db()
    row = conn.execute(
        "SELECT id, status FROM waitlist WHERE email = ? AND token = ?",
        (email, token)
    ).fetchone()

    if not row:
        conn.close()
        return """
        <html><body style="font-family:Inter,system-ui,sans-serif;background:#080C14;color:#fff;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;">
          <div style="text-align:center;padding:40px;">
            <h1 style="color:#ff4444;">Confirmation failed.</h1>
            <p style="color:rgba(255,255,255,0.5);">This link may have expired. Please sign up again.</p>
          </div>
        </body></html>
        """, 400, {"Content-Type": "text/html"}

    if row["status"] == "confirmed":
        conn.close()
        return """
        <html><body style="font-family:Inter,system-ui,sans-serif;background:#080C14;color:#fff;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;">
          <div style="text-align:center;padding:40px;">
            <h1 style="color:#00D4FF;">Already confirmed!</h1>
            <p style="color:rgba(255,255,255,0.5);">Your spot is secured. We will be in touch before launch.</p>
          </div>
        </body></html>
        """, 200, {"Content-Type": "text/html"}

    conn.execute(
        "UPDATE waitlist SET status='confirmed', confirmed_at=datetime('now') WHERE email=?",
        (email,)
    )
    conn.execute("UPDATE confirmation_log SET clicked=1 WHERE token=?", (token,))
    conn.commit()
    conn.close()

    return """
    <html><body style="font-family:Inter,system-ui,sans-serif;background:#080C14;color:#fff;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;">
      <div style="text-align:center;padding:40px;">
        <div style="display:inline-block;width:64px;height:64px;background:rgba(0,212,255,0.2);border-radius:50%;display:flex;align-items:center;justify-content:center;margin:0 auto 24px;">
          <svg width="32" height="32" fill="none" stroke="#00D4FF" viewBox="0 0 24 24" stroke-width="2.5"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/></svg>
        </div>
        <h1 style="font-size:32px;font-weight:800;margin:0 0 12px;">Spot confirmed!</h1>
        <p style="color:rgba(255,255,255,0.5);margin:0 0 32px;line-height:1.6;">You are on the list. We will email you the moment Qubis launches — and you will get early access before anyone else.</p>
        <p style="color:rgba(255,255,255,0.3);font-size:14px;">Follow us @qubisapp for updates.</p>
      </div>
    </body></html>
    """, 200, {"Content-Type": "text/html"}


@app.route("/count", methods=["GET"])
def count():
    """Return total waitlist signups (DB count + hardcoded offset for social proof)."""
    conn = get_db()
    db_count = conn.execute("SELECT COUNT(*) as c FROM waitlist").fetchone()["c"]
    conn.close()
    # Add offset so displayed count = real + offset (2847)
    offset = 2847
    return jsonify({"count": db_count + offset})


@app.route("/export", methods=["GET"])
def export():
    """Export all waitlist emails as CSV. Requires API key in Authorization header."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or auth[7:] != API_KEY:
        return jsonify({"error": "Unauthorized. Provide header: Authorization: Bearer <WAITLIST_API_KEY>"}), 401

    conn = get_db()
    rows = conn.execute(
        "SELECT email, status, source, created_at, confirmed_at FROM waitlist ORDER BY created_at ASC"
    ).fetchall()
    conn.close()

    def generate():
        import io
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=["email", "status", "source", "created_at", "confirmed_at"])
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))
        yield output.getvalue()

    return Response(
        generate(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=qubis-waitlist.csv",
            "Content-Type": "text/csv; charset=utf-8"
        }
    )


@app.route("/stats", methods=["GET"])
def stats():
    """Simple dashboard stats. Requires API key."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or auth[7:] != API_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_db()
    total = conn.execute("SELECT COUNT(*) as c FROM waitlist").fetchone()["c"]
    confirmed = conn.execute("SELECT COUNT(*) as c FROM waitlist WHERE status='confirmed'").fetchone()["c"]
    pending = conn.execute("SELECT COUNT(*) as c FROM waitlist WHERE status='pending'").fetchone()["c"]
    recent = conn.execute(
        "SELECT email, created_at FROM waitlist ORDER BY created_at DESC LIMIT 10"
    ).fetchall()
    conn.close()

    return jsonify({
        "total": total,
        "confirmed": confirmed,
        "pending": pending,
        "confirmation_rate": round(confirmed / total * 100, 1) if total else 0,
        "recent_signups": [dict(r) for r in recent]
    })


# ── Helpers ────────────────────────────────────────────────────────────────────
def _get_count(conn=None):
    own = False
    if conn is None:
        conn = get_db()
        own = True
    c = conn.execute("SELECT COUNT(*) as c FROM waitlist").fetchone()["c"]
    if own:
        conn.close()
    return c


# ── Run ─────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    print(f"\n  Qubis Waitlist Backend")
    print(f"  ─────────────────────────")
    print(f"  Port:     {PORT}")
    print(f"  DB:       {DATABASE}")
    print(f"  API Key:  {API_KEY}")
    print(f"  Resend:   {'Enabled' if RESEND_API_KEY else 'Disabled (dev mode — logs to console)'}")
    print(f"  ─────────────────────────\n")
    app.run(host="0.0.0.0", port=PORT, debug=True)
