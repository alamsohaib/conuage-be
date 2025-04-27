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

async def send_booking_confirmation_email(email: str, name: str) -> None:
    """Send demo booking confirmation email"""
    await send_email_template(
        email_to=email,
        subject="Thank You for Your Demo Request",
        template_name="booking_confirmation",
        template_body={"name": name}
    )

async def send_account_setup_email(
    email_to: str,
    first_name: str,
    role: str,
    locations: List[dict]
) -> None:
    """Send account setup confirmation email"""
    # Convert locations to the format expected by the template
    location_list = [{"name": loc.location_name} for loc in locations]
    
    template_body = {
        "first_name": first_name,
        "email": email_to,
        "role": role.replace('_', ' ').title(),  # Convert 'org_admin' to 'Org Admin'
        "locations": location_list
    }
    
    await send_email_template(
        email_to=email_to,
        subject="Welcome to Conuage - Your Account is Ready",
        template_name="account_setup",
        template_body=template_body
    )

async def send_inactive_account_email(
    email_to: str,
    first_name: str,
    is_org_inactive: bool,
    is_user_inactive: bool,
    org_admins: List[dict]
) -> None:
    """Send email notification when user tries to login to inactive account/org"""
    print(f"Preparing inactive account email for {email_to}")  # Debug print
    
    template_body = {
        "first_name": first_name,
        "is_org_inactive": is_org_inactive,
        "is_user_inactive": is_user_inactive,
        "org_admins": org_admins
    }
    print(f"Template body: {template_body}")  # Debug print
    
    try:
        await send_email_template(
            email_to=email_to,
            subject="Important: Conuage Account Access Notification",
            template_name="inactive_account",
            template_body=template_body
        )
        print(f"Inactive account email sent successfully to {email_to}")
    except Exception as e:
        print(f"Error in send_inactive_account_email: {str(e)}")
        raise  # Re-raise the exception for proper error handling