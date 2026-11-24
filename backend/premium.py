"""Emergent-managed email (Resend) and the premium waitlist form."""

import ipaddress
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from billing import db, member_dep

logger = logging.getLogger(__name__)

EMAIL_BASE_URL = "https://integrations.emergentagent.com"
EMAIL_KEY = os.environ["EMERGENT_EMAIL_KEY"]
EMAIL_FROM_NAME = os.environ["EMAIL_FROM_NAME"]
EMAIL_REPLY_TO = os.environ.get("EMAIL_REPLY_TO")
PREMIUM_REQUEST_EMAIL = os.environ["PREMIUM_REQUEST_EMAIL"]
DAILY_LIMIT = 3

premium_requests = db["premium_waitlist"]
premium_router = APIRouter(prefix="/api/premium")

_SHORTENERS = ("bit.ly", "tinyurl.com", "t.co", "is.gd", "cutt.ly", "goo.gl", "rebrand.ly")
_CRED_ASK = ("reply with your password", "reply with the code", "send your password", "cvv",
             "send us your password", "enter your password below", "confirm your card number",
             "your full card number", "seed phrase", "recovery phrase", "verify your card",
             "social security number", "confirm your bank details")
_HOSTISH = re.compile(r"\b(?:https?://)?((?:[a-z0-9-]+\.)+[a-z]{2,})", re.I)


def _host_ok(host: str) -> bool:
    if not host or "xn--" in host:
        return False
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    return not any(host == s or host.endswith("." + s) for s in _SHORTENERS)


def _same_site(shown: str, real: str) -> bool:
    return shown == real or real.endswith("." + shown) or shown.endswith("." + real)


class _EmailScan(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags, self.urls, self.anchors = set(), [], []
        self._href, self._text = None, []

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag.lower())
        self.urls += [v for k, v in attrs if k.lower() in ("href", "src") and v]
        if tag.lower() == "a":
            self._href = dict((k.lower(), v) for k, v in attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            self.anchors.append((self._href, "".join(self._text)))
            self._href, self._text = None, []


def _assert_safe_email(subject: str, html: str) -> None:
    scan = _EmailScan()
    scan.feed(html)
    if scan.tags & {"form", "input", "textarea", "select"}:
        raise ValueError("No forms or input fields in email (G2)")
    body = f"{subject}\n{html}".lower()
    for p in _CRED_ASK:
        if p in body:
            raise ValueError(f"Email asks the recipient for credentials: {p!r} (G2)")
    for url in scan.urls:
        low = url.strip().lower()
        if low.startswith(("mailto:", "tel:", "cid:", "#")):
            continue
        if not low.startswith("https://"):
            raise ValueError(f"Email links/assets must be absolute https: {url!r} (G3)")
        host = urlparse(low).hostname or ""
        if not _host_ok(host) or urlparse(low).username is not None:
            raise ValueError(f"Shortened, numeric-host or credential-bearing URL: {url!r} (G3)")
    for href, text in scan.anchors:
        real = urlparse(href.strip().lower()).hostname or ""
        if not real:
            continue
        for m in _HOSTISH.finditer(text):
            if not _same_site(m.group(1).lower(), real):
                raise ValueError(f"Anchor text {m.group(1)!r} ≠ real link host {real!r} (G3)")


async def send_email(*, to: str, subject: str, html: str, reply_to: str | None = None) -> str | None:
    _assert_safe_email(subject, html)
    payload = {"to": [to], "subject": subject, "html": html, "from_name": EMAIL_FROM_NAME}
    if reply_to or EMAIL_REPLY_TO:
        payload["contact_email"] = reply_to or EMAIL_REPLY_TO
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{EMAIL_BASE_URL}/api/v1/email/send",
                                     headers={"X-Email-Key": EMAIL_KEY}, json=payload)
        resp.raise_for_status()
        return resp.json().get("id")
    except httpx.HTTPStatusError as e:
        try:
            code = e.response.json().get("code", "")
        except ValueError:
            code = ""
        if code in ("insufficient_credits", "integration_disabled", "daily_limit_reached"):
            logger.warning(f"Email paused: {code} ({e.response.status_code}): {e.response.json().get('message', '')}")
            raise HTTPException(status_code=503, detail="Email is temporarily unavailable")
        logger.error(f"Email send failed: {e.response.status_code} {e.response.text}")
        raise HTTPException(status_code=502, detail="Failed to send email")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Email send error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to send email")


class PremiumIn(BaseModel):
    subject: str = Field(..., min_length=3, max_length=120)
    reason: str = Field(..., min_length=10, max_length=2000)


def _template(member: dict, body: PremiumIn) -> str:
    reason = escape(body.reason).replace("\n", "<br>")
    return (
        '<table role="presentation" width="100%"><tr><td style="padding:24px;font-family:Arial,sans-serif;color:#1f2937">'
        f'<p style="font-size:16px;font-weight:bold;margin:0 0 12px">New premium waitlist signup</p>'
        f'<p style="margin:0 0 4px"><b>From:</b> {escape(member.get("email") or member["user_id"])}</p>'
        f'<p style="margin:0 0 4px"><b>Current credits:</b> {member.get("credits", 0)}</p>'
        f'<p style="margin:0 0 12px"><b>Subject:</b> {escape(body.subject)}</p>'
        f'<p style="margin:0 0 4px"><b>Reason</b></p>'
        f'<p style="margin:0 0 16px;padding:12px;background:#f5f4f0;border-radius:6px">{reason}</p>'
        '<p style="margin:0;font-size:12px;color:#888">Reply to this email to answer the requester directly. '
        f'Sent by {escape(EMAIL_FROM_NAME)}.</p>'
        '</td></tr></table>'
    )


@premium_router.post("/waitlist")
async def join_waitlist(body: PremiumIn, member: dict = Depends(member_dep)):
    since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    if premium_requests.count_documents({"user_id": member["user_id"], "created_at": {"$gte": since}}) >= DAILY_LIMIT:
        raise HTTPException(429, detail="You're already on the waitlist. We'll be in touch soon.")
    doc = {"user_id": member["user_id"], "email": member.get("email"), "subject": body.subject,
           "reason": body.reason, "status": "joined", "created_at": datetime.now(timezone.utc).isoformat()}
    premium_requests.insert_one(doc)
    email_id = await send_email(to=PREMIUM_REQUEST_EMAIL, subject=f"{EMAIL_FROM_NAME}: new premium waitlist signup",
                                html=_template(member, body), reply_to=member.get("email"))
    premium_requests.update_one({"user_id": member["user_id"], "created_at": doc["created_at"]},
                                {"$set": {"email_id": email_id}})
    return {"status": "joined"}


@premium_router.get("/waitlist")
def my_waitlist(member: dict = Depends(member_dep)):
    entries = list(premium_requests.find({"user_id": member["user_id"]}, {"_id": 0, "user_id": 0})
                .sort("created_at", -1).limit(20))
    return {"joined": bool(entries), "entries": entries}
