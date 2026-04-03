from __future__ import annotations

import base64
import json
import smtplib
from email.message import EmailMessage
from urllib import request

from app.config import settings
from app.models import TenantEmailConfig


def encrypt_secret(raw: str | None) -> str | None:
    if raw is None or raw == "":
        return None
    payload = f"{settings.jwt_secret}:{raw}".encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii")


def decrypt_secret(raw: str | None) -> str | None:
    if raw is None or raw == "":
        return None
    try:
        decoded = base64.urlsafe_b64decode(raw.encode("ascii")).decode("utf-8")
    except Exception:
        return None
    prefix = f"{settings.jwt_secret}:"
    if not decoded.startswith(prefix):
        return None
    return decoded[len(prefix) :]


def send_tenant_email(
    config: TenantEmailConfig,
    *,
    to_email: str,
    subject: str,
    text_body: str,
) -> None:
    provider = config.provider.strip().lower()
    if provider == "smtp":
        _send_via_smtp(config, to_email=to_email, subject=subject, text_body=text_body)
        return
    if provider == "sendgrid":
        _send_via_sendgrid(config, to_email=to_email, subject=subject, text_body=text_body)
        return
    raise ValueError("unsupported_email_provider")


def _send_via_smtp(
    config: TenantEmailConfig,
    *,
    to_email: str,
    subject: str,
    text_body: str,
) -> None:
    if not config.smtp_host or not config.smtp_port:
        raise ValueError("smtp_config_incomplete")
    msg = EmailMessage()
    msg["From"] = _from_header(config)
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(text_body)

    password = decrypt_secret(config.smtp_password_encrypted)
    with smtplib.SMTP(config.smtp_host, int(config.smtp_port), timeout=15) as server:
        server.starttls()
        if config.smtp_username and password:
            server.login(config.smtp_username, password)
        server.send_message(msg)


def _send_via_sendgrid(
    config: TenantEmailConfig,
    *,
    to_email: str,
    subject: str,
    text_body: str,
) -> None:
    api_key = decrypt_secret(config.api_key_encrypted)
    if not api_key:
        raise ValueError("sendgrid_api_key_missing")
    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": config.from_email, "name": config.from_name or config.from_email},
        "subject": subject,
        "content": [{"type": "text/plain", "value": text_body}],
    }
    req = request.Request(
        "https://api.sendgrid.com/v3/mail/send",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with request.urlopen(req, timeout=15) as resp:
        code = resp.getcode()
        if code not in (200, 202):
            raise ValueError("sendgrid_delivery_failed")


def _from_header(config: TenantEmailConfig) -> str:
    if config.from_name:
        return f"{config.from_name} <{config.from_email}>"
    return config.from_email
