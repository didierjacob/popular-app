import os
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from jinja2 import Template
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

# Admin alert email for critical email failures
ADMIN_ALERT_EMAIL = "didier@coffeeandfilms.com"


class EmailService:
    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.from_email = os.getenv("SMTP_FROM_EMAIL", self.smtp_user)
        self.from_name = os.getenv("SMTP_FROM_NAME", "Popularoo")
        self._db = None  # Will be set after DB init

    def set_db(self, db):
        """Set the database reference for error logging."""
        self._db = db

    async def _log_email_error(self, error_type: str, error_message: str,
                                to_email: str, subject: str, http_code: Optional[int] = None):
        """Log email sending errors to MongoDB admin_notifications collection."""
        notification = {
            "type": "email_error",
            "status": "urgent",
            "error_type": error_type,
            "error_message": str(error_message),
            "http_code": http_code,
            "to_email": to_email,
            "subject": subject,
            "timestamp": datetime.now(timezone.utc),
            "resolved": False,
        }
        try:
            if self._db is not None:
                await self._db.admin_notifications.insert_one(notification)
                logger.error(f"[EMAIL_ERROR] Logged to admin_notifications: {error_type} — {error_message}")
            else:
                logger.error(f"[EMAIL_ERROR] DB not available. Error: {error_type} — {error_message}")
        except Exception as log_err:
            logger.error(f"[EMAIL_ERROR] Failed to log to DB: {log_err}")

    async def _send_admin_alert(self, error_type: str, error_message: str,
                                 original_to: str, original_subject: str):
        """Send an alert email to admin about email delivery failure."""
        try:
            alert_subject = f"⚠️ [Popularoo] Email delivery failure: {error_type}"
            alert_body = f"""
            <div style="font-family:sans-serif;max-width:500px;padding:20px;">
                <h2 style="color:#E04F5F;">⚠️ Email Delivery Failure</h2>
                <p><b>Error type:</b> {error_type}</p>
                <p><b>Message:</b> {error_message}</p>
                <p><b>Original recipient:</b> {original_to}</p>
                <p><b>Original subject:</b> {original_subject}</p>
                <p><b>Timestamp:</b> {datetime.now(timezone.utc).isoformat()}</p>
                <hr>
                <p style="font-size:12px;color:#888;">This is an automated alert from Popularoo email monitoring.</p>
            </div>
            """
            message = MIMEMultipart("alternative")
            message["Subject"] = alert_subject
            message["From"] = f"{self.from_name} <{self.from_email}>"
            message["To"] = ADMIN_ALERT_EMAIL
            message.attach(MIMEText(alert_body, "html"))

            await aiosmtplib.send(
                message,
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.smtp_user,
                password=self.smtp_password,
                start_tls=True,
            )
            logger.info(f"[EMAIL_ALERT] Admin alert sent to {ADMIN_ALERT_EMAIL}")
        except Exception as alert_err:
            logger.error(f"[EMAIL_ALERT] Failed to send admin alert: {alert_err}")

    async def send_email(self, to_email: str, subject: str, html_content: str):
        """Send an email via SMTP with robust error handling and admin alerting."""
        if not self.smtp_user or not self.smtp_password:
            error_msg = "SMTP credentials not configured (SMTP_USER or SMTP_PASSWORD missing)"
            logger.error(f"[EMAIL_ERROR] {error_msg}")
            await self._log_email_error("CREDENTIALS_MISSING", error_msg, to_email, subject)
            raise ValueError(error_msg)

        try:
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = f"{self.from_name} <{self.from_email}>"
            message["To"] = to_email
            html_part = MIMEText(html_content, "html")
            message.attach(html_part)

            await aiosmtplib.send(
                message,
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.smtp_user,
                password=self.smtp_password,
                start_tls=True,
            )

            logger.info(f"[EMAIL_OK] Sent to {to_email}: {subject}")
            return True

        except aiosmtplib.SMTPAuthenticationError as e:
            error_msg = f"SMTP Authentication failed (401/403): {e}"
            logger.error(f"[EMAIL_ERROR] {error_msg}")
            await self._log_email_error("AUTH_FAILURE", error_msg, to_email, subject, http_code=401)
            await self._send_admin_alert("AUTH_FAILURE", error_msg, to_email, subject)
            raise

        except aiosmtplib.SMTPConnectError as e:
            error_msg = f"SMTP connection failed: {e}"
            logger.error(f"[EMAIL_ERROR] {error_msg}")
            await self._log_email_error("CONNECTION_FAILED", error_msg, to_email, subject)
            await self._send_admin_alert("CONNECTION_FAILED", error_msg, to_email, subject)
            raise

        except aiosmtplib.SMTPRecipientsRefused as e:
            error_msg = f"Recipient refused: {e}"
            logger.error(f"[EMAIL_ERROR] {error_msg}")
            await self._log_email_error("RECIPIENT_REFUSED", error_msg, to_email, subject, http_code=422)
            raise

        except aiosmtplib.SMTPResponseException as e:
            error_msg = f"SMTP error {e.code}: {e.message}"
            logger.error(f"[EMAIL_ERROR] {error_msg}")
            await self._log_email_error("SMTP_ERROR", error_msg, to_email, subject, http_code=e.code)
            if e.code in (401, 403, 535):
                await self._send_admin_alert(f"SMTP_ERROR_{e.code}", error_msg, to_email, subject)
            raise

        except Exception as e:
            error_msg = f"Unexpected error: {type(e).__name__}: {e}"
            logger.error(f"[EMAIL_ERROR] {error_msg}")
            await self._log_email_error("UNEXPECTED", error_msg, to_email, subject)
            await self._send_admin_alert("UNEXPECTED", error_msg, to_email, subject)
            raise

    async def send_daily_report(self, to_email: str, stats: Dict[str, Any]):
        """Send daily report email."""
        try:
            with open("/app/backend/email_template.html", "r") as f:
                template_content = f.read()
            template = Template(template_content)
            html_content = template.render(**stats)
            subject = f"📊 Rapport Quotidien Popularoo - {stats['date']}"
            await self.send_email(to_email, subject, html_content)
            return True
        except Exception as e:
            logger.error(f"Failed to send daily report: {e}")
            raise


# Global instance
email_service = EmailService()
