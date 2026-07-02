"""
Email Service — sends emails via SMTP.

For development: prints to console (no real SMTP needed).
For production:  set MAIL_USERNAME / MAIL_PASSWORD in .env and
                 flip DEV_MODE = False below.

Usage:
    from app.services.email_service import send_email
    send_email("user@example.com", "Subject", "<h1>HTML body</h1>")
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app

DEV_MODE = False  # Set to False when SMTP credentials are configured


def send_email(to_email, subject, html_body, plain_body=None):
    """Send an email. In DEV_MODE, just logs to console."""

    if DEV_MODE:
        current_app.logger.info(
            f"\n{'─'*50}\n"
            f"  📧 EMAIL (dev mode — not actually sent)\n"
            f"  To:      {to_email}\n"
            f"  Subject: {subject}\n"
            f"  Body:    {plain_body or html_body[:200]}\n"
            f"{'─'*50}\n"
        )
        return True

    try:
        cfg = current_app.config

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = cfg["MAIL_DEFAULT_SENDER"]
        msg["To"]      = to_email

        if plain_body:
            msg.attach(MIMEText(plain_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(cfg["MAIL_SERVER"], cfg["MAIL_PORT"]) as server:
            if cfg["MAIL_USE_TLS"]:
                server.starttls()
            server.login(cfg["MAIL_USERNAME"], cfg["MAIL_PASSWORD"])
            server.send_message(msg)

        return True

    except Exception as e:
        current_app.logger.error(f"Email send failed: {e}")
        return False


def send_otp_email(to_email, otp_code, purpose="signup"):
    """Convenience wrapper for OTP emails."""
    if purpose == "signup":
        subject = "Verify Your Email — Attendance Portal"
        html = f"""
        <div style="font-family:sans-serif;max-width:400px;margin:auto;padding:2rem">
            <h2 style="color:#1a1d23">Email Verification</h2>
            <p>Your verification code is:</p>
            <div style="font-size:2rem;font-weight:bold;letter-spacing:8px;
                        background:#f0f2f5;padding:1rem;text-align:center;
                        border-radius:8px;margin:1rem 0">{otp_code}</div>
            <p style="color:#5f6577;font-size:0.9rem">
                This code expires in 5 minutes. If you didn't create an account,
                please ignore this email.
            </p>
        </div>
        """
    else:
        subject = "Password Reset — Attendance Portal"
        html = f"""
        <div style="font-family:sans-serif;max-width:400px;margin:auto;padding:2rem">
            <h2 style="color:#1a1d23">Password Reset</h2>
            <p>Your reset code is:</p>
            <div style="font-size:2rem;font-weight:bold;letter-spacing:8px;
                        background:#f0f2f5;padding:1rem;text-align:center;
                        border-radius:8px;margin:1rem 0">{otp_code}</div>
            <p style="color:#5f6577;font-size:0.9rem">
                This code expires in 5 minutes. If you didn't request a reset,
                please ignore this email.
            </p>
        </div>
        """
    return send_email(to_email, subject, html, plain_body=f"Your code: {otp_code}")
