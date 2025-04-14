from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from pydantic import EmailStr
from app.core.config import settings
from pathlib import Path
from typing import List, Dict, Any

# Email configuration
conf = ConnectionConfig(
    MAIL_USERNAME=settings.MAIL_USERNAME,
    MAIL_PASSWORD=settings.MAIL_PASSWORD,
    MAIL_FROM=settings.MAIL_FROM,
    MAIL_PORT=settings.MAIL_PORT,
    MAIL_SERVER=settings.MAIL_SERVER,
    MAIL_STARTTLS=settings.MAIL_TLS,
    MAIL_SSL_TLS=settings.MAIL_SSL,
    USE_CREDENTIALS=settings.USE_CREDENTIALS,
    VALIDATE_CERTS=settings.VALIDATE_CERTS,
    TEMPLATE_FOLDER=Path(settings.TEMPLATE_FOLDER)
)

# Create FastMail instance
mail = FastMail(conf)

async def send_email_template(
    email_to: str,
    subject: str,
    template_name: str,
    template_body: Dict[str, Any]
) -> None:
    """
    Send an email using a template
    
    Args:
        email_to: Recipient email address
        subject: Email subject
        template_name: Name of the template file (without .html extension)
        template_body: Dictionary of variables to pass to the template
    """
    message = MessageSchema(
        subject=subject,
        recipients=[email_to],
        template_body=template_body,
        subtype=MessageType.html
    )
    
    await mail.send_message(message, template_name=f"{template_name}.html")

async def send_verification_email(email: str, code: str) -> None:
    """Send verification code email"""
    await send_email_template(
        email_to=email,
        subject="Verify Your Email",
        template_name="verification",
        template_body={"code": code}
    )

async def send_reset_code_email(email: str, code: str) -> None:
    """Send password reset code email"""
    await send_email_template(
        email_to=email,
        subject="Password Reset Code",
        template_name="reset_password",
        template_body={"code": code}
    )