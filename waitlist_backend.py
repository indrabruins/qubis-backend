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
import secrets
import string
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from flask import Flask, request, jsonify, Response, send_file
from dotenv import load_dotenv

# ── Config ────────────────────────────────────────────────────────────────────
load_dotenv()  # Load .env if present
DATABASE = os.path.join(os.path.dirname(__file__), "waitlist.db")
PORT = int(os.environ.get("PORT", 5003))
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
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            email         TEXT    UNIQUE NOT NULL,
            source        TEXT    DEFAULT '',
            referral_code TEXT    UNIQUE,
            referred_by   TEXT    DEFAULT '',
            status        TEXT    DEFAULT 'pending',
            token         TEXT,
            confirmed_at  TEXT,
            created_at    TEXT    DEFAULT (datetime('now'))
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
    # Migration: add referral columns if they don't exist
    try:
        conn.execute("ALTER TABLE waitlist ADD COLUMN referral_code TEXT UNIQUE")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE waitlist ADD COLUMN referred_by TEXT DEFAULT ''")
    except Exception:
        pass
    conn.commit()
    conn.close()

# ── Referral Code Generation ────────────────────────────────────────────────────
REFERRAL_CHARS = string.ascii_uppercase + string.digits

def generate_referral_code(length=6):
    """Generate a unique 6-char alphanumeric referral code."""
    while True:
        code = ''.join(secrets.choice(REFERRAL_CHARS) for _ in range(length))
        conn = get_db()
        existing = conn.execute(
            "SELECT id FROM waitlist WHERE referral_code = ?", (code,)
        ).fetchone()
        conn.close()
        if not existing:
            return code

# ── Email Validation ────────────────────────────────────────────────────────────
EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")

def is_valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(email.strip()))

# ── Resend Integration ─────────────────────────────────────────────────────────
def send_confirmation_email(email: str, token: str, referral_code: str = None) -> bool:
    """Send confirmation email via Resend API. Returns True on success."""
    confirm_url = f"{APP_URL}/confirm?token={token}&email={email}"
    referral_url = f"{APP_URL}/referrals/{referral_code}" if referral_code else None

    referral_section = ""
    if referral_url:
        referral_section = f"""
        <div style="background: rgba(0,212,255,0.08); border: 1px dashed rgba(0,212,255,0.3); border-radius: 12px; padding: 20px; margin: 24px 0; text-align: center;">
          <p style="color: rgba(255,255,255,0.7); margin: 0 0 12px; font-size: 14px;">
            <strong style="color: #00D4FF;">Skip the line</strong> — share your referral link and move up the waitlist.
          </p>
          <p style="color: rgba(255,255,255,0.5); margin: 0 0 16px; font-size: 13px;">
            Each friend who joins moves you higher. Unlimited upgrades.
          </p>
          <a href="{referral_url}"
             style="display: inline-block; background: rgba(0,212,255,0.15); border: 1px solid rgba(0,212,255,0.4); color: #00D4FF; font-weight: 700; font-size: 13px; padding: 10px 24px; border-radius: 8px; text-decoration: none;">
            {referral_url}
          </a>
        </div>
        """

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
        {referral_section}
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
        print(f"\n[DEV EMAIL] To: {email}")
        print(f"[DEV EMAIL] Confirm link: {confirm_url}")
        if referral_url:
            print(f"[DEV EMAIL] Referral link: {referral_url}")
        print()
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
    referred_by = (data.get("referred_by") or "").strip().upper()

    if not email or not is_valid_email(email):
        return jsonify({"error": "Please provide a valid email address."}), 400

    conn = get_db()
    existing = conn.execute(
        "SELECT id, status, referral_code FROM waitlist WHERE email = ?", (email,)
    ).fetchone()

    if existing:
        conn.close()
        return jsonify({
            "message": "You are already on the list!",
            "count": _get_count(),
            "referral_code": existing["referral_code"] or None
        }), 200

    token = str(uuid.uuid4())
    referral_code = generate_referral_code()

    conn.execute(
        "INSERT INTO waitlist (email, source, status, token, referral_code, referred_by) VALUES (?, ?, 'pending', ?, ?, ?)",
        (email, source, token, referral_code, referred_by)
    )
    conn.execute(
        "INSERT INTO confirmation_log (email, token) VALUES (?, ?)",
        (email, token)
    )
    conn.commit()
    conn.close()

    try:
        send_confirmation_email(email, token, referral_code)
    except Exception as e:
        print(f"[WARNING] Could not send confirmation email: {e}")

    return jsonify({
        "message": "You are on the list! Check your inbox to confirm.",
        "count": _get_count(),
        "referral_code": referral_code
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
    offset = 2847
    return jsonify({"count": db_count + offset})


@app.route("/referrals/<code>", methods=["GET"])
def referrals(code):
    """Return referrer's position and referral count for a given referral code."""
    code = code.strip().upper()
    conn = get_db()
    referrer = conn.execute(
        "SELECT id, email, referral_code FROM waitlist WHERE referral_code = ?",
        (code,)
    ).fetchone()

    if not referrer:
        conn.close()
        return jsonify({"error": "Invalid referral code."}), 404

    # Position: count of confirmed signups before this referrer (by id)
    position = conn.execute(
        "SELECT COUNT(*) as c FROM waitlist WHERE id < ? AND status = 'confirmed'",
        (referrer["id"],)
    ).fetchone()["c"] + 1

    # Count of confirmed referrals (people this referrer brought in)
    referral_count = conn.execute(
        "SELECT COUNT(*) as c FROM waitlist WHERE referred_by = ? AND status = 'confirmed'",
        (code,)
    ).fetchone()["c"]

    conn.close()

    return jsonify({
        "referral_code": code,
        "referral_count": referral_count,
        "waitlist_position": position,
        "message": f"You have {referral_count} confirmed referrals. You are #{position} on the confirmed waitlist."
    })


@app.route("/export", methods=["GET"])
def export():
    """Export all waitlist emails as CSV. Requires API key in Authorization header."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or auth[7:] != API_KEY:
        return jsonify({"error": "Unauthorized. Provide header: Authorization: Bearer <WAITLIST_API_KEY>"}), 401

    conn = get_db()
    rows = conn.execute(
        "SELECT email, status, source, referral_code, referred_by, created_at, confirmed_at FROM waitlist ORDER BY created_at ASC"
    ).fetchall()
    conn.close()

    def generate():
        import io
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=["email", "status", "source", "referral_code", "referred_by", "created_at", "confirmed_at"])
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
    """Stats with referral metrics. Requires API key."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or auth[7:] != API_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_db()
    total = conn.execute("SELECT COUNT(*) as c FROM waitlist").fetchone()["c"]
    confirmed = conn.execute("SELECT COUNT(*) as c FROM waitlist WHERE status='confirmed'").fetchone()["c"]
    pending = conn.execute("SELECT COUNT(*) as c FROM waitlist WHERE status='pending'").fetchone()["c"]

    total_referrals = conn.execute(
        "SELECT COUNT(*) as c FROM waitlist WHERE referred_by != ''"
    ).fetchone()["c"]
    confirmed_referrals = conn.execute(
        "SELECT COUNT(*) as c FROM waitlist WHERE referred_by != '' AND status='confirmed'"
    ).fetchone()["c"]
    top_referrers = conn.execute("""
        SELECT referred_by, COUNT(*) as cnt
        FROM waitlist
        WHERE referred_by != ''
        GROUP BY referred_by
        ORDER BY cnt DESC
        LIMIT 10
    """).fetchall()

    recent = conn.execute(
        "SELECT email, created_at FROM waitlist ORDER BY created_at DESC LIMIT 10"
    ).fetchall()
    conn.close()

    return jsonify({
        "total": total,
        "confirmed": confirmed,
        "pending": pending,
        "confirmation_rate": round(confirmed / total * 100, 1) if total else 0,
        "total_referrals": total_referrals,
        "confirmed_referrals": confirmed_referrals,
        "top_referrers": [dict(r) for r in top_referrers],
        "recent_signups": [dict(r) for r in recent]
    })


@app.route("/admin/stats", methods=["GET"])
def admin_stats():
    """Full analytics dashboard. Requires API key."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or auth[7:] != API_KEY:
        return jsonify({"error": "Unauthorized. Provide header: Authorization: Bearer <WAITLIST_API_KEY>"}), 401

    conn = get_db()

    total = conn.execute("SELECT COUNT(*) as c FROM waitlist").fetchone()["c"]
    confirmed = conn.execute("SELECT COUNT(*) as c FROM waitlist WHERE status='confirmed'").fetchone()["c"]
    pending = conn.execute("SELECT COUNT(*) as c FROM waitlist WHERE status='pending'").fetchone()["c"]

    emails_sent = conn.execute("SELECT COUNT(*) as c FROM confirmation_log").fetchone()["c"]
    emails_clicked = conn.execute("SELECT SUM(clicked) as c FROM confirmation_log").fetchone()["c"] or 0
    open_rate = round(emails_clicked / emails_sent * 100, 1) if emails_sent else 0

    by_day_rows = conn.execute("""
        SELECT DATE(created_at) as day, COUNT(*) as count
        FROM waitlist
        WHERE created_at >= datetime('now', '-14 days')
        GROUP BY DATE(created_at)
        ORDER BY day ASC
    """).fetchall()

    top_referrers = conn.execute("""
        SELECT w.referral_code, w.email, COUNT(*) as confirmed_referrals
        FROM waitlist r
        JOIN waitlist w ON r.referred_by = w.referral_code
        WHERE r.referred_by != '' AND r.status = 'confirmed'
        GROUP BY w.referral_code
        ORDER BY confirmed_referrals DESC
        LIMIT 10
    """).fetchall()

    sources = conn.execute("""
        SELECT source, COUNT(*) as count
        FROM waitlist
        GROUP BY source
        ORDER BY count DESC
    """).fetchall()

    conn.close()

    return jsonify({
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "waitlist": {
            "total": total,
            "confirmed": confirmed,
            "pending": pending,
            "confirmation_rate": round(confirmed / total * 100, 1) if total else 0
        },
        "email": {
            "sent": emails_sent,
            "opened": int(emails_clicked),
            "open_rate": open_rate
        },
        "referrals": {
            "top_10": [dict(r) for r in top_referrers]
        },
        "signups_by_day": [dict(r) for r in by_day_rows],
        "sources": [dict(r) for r in sources]
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
