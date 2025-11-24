import os
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from jinja2 import Template
from datetime import datetime, timedelta
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

class EmailService:
    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.from_email = os.getenv("SMTP_FROM_EMAIL", self.smtp_user)
        self.from_name = os.getenv("SMTP_FROM_NAME", "Popular App")
        
    async def send_email(self, to_email: str, subject: str, html_content: str):
        """Envoie un email via SMTP"""
        if not self.smtp_user or not self.smtp_password:
            logger.error("SMTP credentials not configured")
            raise ValueError("SMTP credentials not configured. Please set SMTP_USER and SMTP_PASSWORD in .env")
        
        try:
            # Créer le message
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = f"{self.from_name} <{self.from_email}>"
            message["To"] = to_email
            
            # Ajouter le contenu HTML
            html_part = MIMEText(html_content, "html")
            message.attach(html_part)
            
            # Envoyer via SMTP
            await aiosmtplib.send(
                message,
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.smtp_user,
                password=self.smtp_password,
                start_tls=True,
            )
            
            logger.info(f"Email sent successfully to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            raise
    
    async def send_daily_report(self, to_email: str, stats: Dict[str, Any]):
        """Envoie le rapport quotidien"""
        try:
            # Charger le template
            with open("/app/backend/email_template.html", "r") as f:
                template_content = f.read()
            
            template = Template(template_content)
            
            # Générer le HTML avec les données
            html_content = template.render(**stats)
            
            # Envoyer l'email
            subject = f"📊 Rapport Quotidien Popular - {stats['date']}"
            await self.send_email(to_email, subject, html_content)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to send daily report: {e}")
            raise

# Instance globale
email_service = EmailService()
