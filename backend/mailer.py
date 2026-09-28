"""
Sends emails (password resets and email verification).

If SMTP settings are in .env it sends real email. If not, it prints the email
in the terminal instead, which is handy while developing: you can just click
the link from there.
"""

import os
import smtplib
from email.message import EmailMessage

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
FROM = os.getenv("MAIL_FROM", "Callcade <no-reply@callcade.local>")
SITE_URL = os.getenv("SITE_URL", "http://localhost:8000")

outbox = []  # the last few emails, so tests (and I) can see what was sent


def enabled():
    return bool(SMTP_HOST)


def send(to, subject, body):
    outbox.append({"to": to, "subject": subject, "body": body})
    del outbox[:-20]
    if not enabled():
        print(f"\n----- EMAIL to {to} -----\n{subject}\n\n{body}\n--------------------------\n", flush=True)
        return
    msg = EmailMessage()
    msg["From"] = FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
        s.starttls()
        if SMTP_USER:
            s.login(SMTP_USER, SMTP_PASSWORD)
        s.send_message(msg)


def send_verify(user, token):
    send(user["email"], "Verify your Callcade email",
         f"Hey {user['display_name']},\n\nClick this link to verify your email:\n"
         f"{SITE_URL}/#/verify?token={token}\n\nIf you didn't make a Callcade account, you can ignore this.")


def send_reset(user, token):
    send(user["email"], "Reset your Callcade password",
         f"Hey {user['display_name']},\n\nClick this link to pick a new password (it works for 1 hour):\n"
         f"{SITE_URL}/#/reset?token={token}\n\nIf you didn't ask for this, you can ignore it.")
