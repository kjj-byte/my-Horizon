"""Send one plain-text email through QQ SMTP using the EMAIL_ADDRESS/PASSWORD secrets."""

from __future__ import annotations

import os
import smtplib
import ssl
import sys
from email.mime.text import MIMEText


def mailbox() -> str:
    address = os.environ.get("EMAIL_ADDRESS", "").strip()
    if not address:
        raise RuntimeError("EMAIL_ADDRESS secret is empty or not set")
    return address


def send_mail(subject: str, body: str) -> None:
    address = mailbox()
    password = os.environ.get("EMAIL_PASSWORD", "")
    if not password:
        raise RuntimeError("EMAIL_PASSWORD secret is empty or not set")

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = f"Horizon Daily <{address}>"
    msg["To"] = address
    with smtplib.SMTP_SSL(
        "smtp.qq.com", 465, context=ssl.create_default_context(), timeout=30
    ) as server:
        server.login(address, password)
        server.send_message(msg)


if __name__ == "__main__":
    send_mail(sys.argv[1], sys.argv[2])