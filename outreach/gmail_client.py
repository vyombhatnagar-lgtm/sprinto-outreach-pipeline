"""Step 7 transport: Gmail API (OAuth) or Gmail SMTP (app password).

`send_email` has no `to` parameter on purpose. The recipient is always
HARDCODED_RECIPIENT, and `_guard` re-checks the built message before it leaves.
"""
import base64
import smtplib
from email.mime.text import MIMEText
from email.utils import make_msgid
from typing import Optional

from .config import HARDCODED_RECIPIENT, Settings
from .models import SendResult

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


class RecipientGuardError(RuntimeError):
    pass


def _guard(msg: MIMEText) -> None:
    to = (msg["To"] or "").strip().lower()
    if to != HARDCODED_RECIPIENT.lower() or msg["Cc"] or msg["Bcc"]:
        raise RecipientGuardError(f"Refusing to send: recipient {to!r} is not the hardcoded address")


def build_message(sender: str, subject: str, body: str, domain: Optional[str] = None) -> MIMEText:
    msg = MIMEText(body, "plain", "utf-8")
    msg["To"] = HARDCODED_RECIPIENT
    if sender:
        msg["From"] = sender
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid(domain="outreach.local")
    if domain:
        msg["X-Outreach-Prospect"] = domain  # lets you filter test sends in Gmail
    _guard(msg)
    return msg


def _oauth_service(settings: Settings, interactive: bool = True):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds_file = settings.secrets_dir / "credentials.json"
    token_file = settings.secrets_dir / "token.json"
    creds = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:
        if not interactive:
            raise RuntimeError("No valid Gmail token. Run: python -m outreach gmail-auth")
        if not creds_file.exists():
            raise FileNotFoundError(
                f"Missing {creds_file}. Create a Desktop OAuth client in Google Cloud "
                "(Gmail API enabled) and download its JSON there."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(creds_file), SCOPES)
        creds = flow.run_local_server(port=0)
    token_file.write_text(creds.to_json())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def authorize(settings: Settings) -> str:
    """Interactive one-time setup. Returns a human-readable status line."""
    if settings.gmail_mode == "smtp":
        if not (settings.gmail_sender and settings.gmail_app_password):
            raise RuntimeError("GMAIL_MODE=smtp needs GMAIL_SENDER and GMAIL_APP_PASSWORD in .env")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as s:
            s.login(settings.gmail_sender, settings.gmail_app_password)
        return f"SMTP login OK for {settings.gmail_sender}"
    _oauth_service(settings, interactive=True)
    return f"OAuth token saved to {settings.secrets_dir / 'token.json'}"


def send_email(settings: Settings, subject: str, body: str, domain: Optional[str] = None) -> SendResult:
    msg = build_message(settings.gmail_sender, subject, body, domain)
    try:
        if settings.gmail_mode == "smtp":
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as s:
                s.login(settings.gmail_sender, settings.gmail_app_password)
                s.send_message(msg, to_addrs=[HARDCODED_RECIPIENT])
            message_id = msg["Message-ID"]
        else:
            service = _oauth_service(settings, interactive=False)
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            resp = service.users().messages().send(userId="me", body={"raw": raw}).execute()
            message_id = resp.get("id")
        return SendResult(domain=domain or "-", sent=True, recipient=HARDCODED_RECIPIENT,
                          mode=settings.gmail_mode, message_id=message_id)
    except RecipientGuardError:
        raise
    except Exception as e:  # recorded in the trace rather than crashing a batch run
        return SendResult(domain=domain or "-", sent=False, recipient=HARDCODED_RECIPIENT,
                          mode=settings.gmail_mode, error=f"{type(e).__name__}: {e}")
