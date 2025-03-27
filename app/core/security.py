from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.core.config import settings
import secrets
import string

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

# JWT token functions
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

# Verification code functions
def generate_verification_code(length: int = 6) -> str:
    # Generate a random verification code
    alphabet = string.digits  # Only numbers
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def is_valid_verification_code(stored_code: str, provided_code: str) -> bool:
    return stored_code == provided_code

# Email domain extraction
def get_organization_name_from_email(email: str) -> str:
    """Extract organization name from email domain (e.g., 'google' from 'user@google.com')"""
    domain = email.split('@')[1]
    org_name = domain.split('.')[0]
    return org_name.title()  # Capitalize first letter
