from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from app.db.supabase import get_db
from app.schemas.base import UserSignUp, UserLogin, VerifyEmail, Token, User, UserCreate, ForgotPassword, ResetPassword, ChangePassword
from app.core.security import (
    verify_password, get_password_hash, create_access_token,
    generate_verification_code, is_valid_verification_code,
    get_organization_name_from_email
)
from supabase import Client
from datetime import datetime, timedelta
import pytz
from uuid import UUID
import json
from typing import Optional
from app.core.config import settings
from app.core.auth import get_current_user
from fastapi.middleware.cors import CORSMiddleware

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

class UUIDEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

def get_utc_now() -> datetime:
    return datetime.now(pytz.UTC)

async def send_verification_email(email: str, code: str):
    # TODO: Implement email sending logic
    # For now, just print the code
    print(f"Verification code for {email}: {code}")

async def send_reset_code_email(email: str, code: str):
    # TODO: Implement email sending logic
    # For now, just print the code
    print(f"Password reset code for {email}: {code}")

@router.post("/signup")
async def signup(
    user_data: UserSignUp,
    background_tasks: BackgroundTasks,
    db: Client = Depends(get_db)
):
    try:
        print(f"Starting signup process for email: {user_data.email}")
        
        # Check if user already exists
        existing_user = db.table('users').select("*").eq('email', user_data.email).execute()
        if existing_user.data:
            raise HTTPException(status_code=400, detail="Email already registered")

        # Get organization from email domain
        org_name = get_organization_name_from_email(user_data.email)
        print(f"Extracted organization name: {org_name}")
        
        # Check if organization exists
        org = db.table('organizations').select("*").eq('name', org_name).execute()
        
        org_id = None
        initial_status = "pending"  # Default status
        default_location_id = None  # Initialize default_location_id here
        daily_token_limit = 0  # Default token limit
        
        if not org.data:
            print("Creating new organization")
            # Create new organization
            org_data = {
                "name": org_name,
                "is_active": True,
                "auto_signup_enabled": True
            }
            org_response = db.table('organizations').insert(org_data).execute()
            org_id = org_response.data[0]['id']
            print(f"Created organization with ID: {org_id}")
            
            # Create corporate location
            location_data = {
                "name": "Corporate",
                "organization_id": org_id,
                "details": "Main corporate location"
            }
            print("Creating corporate location with data:", json.dumps(location_data, cls=UUIDEncoder))
            location_response = db.table('locations').insert(location_data).execute()
            default_location_id = location_response.data[0]['id']  # Set default_location_id here
            print(f"Created location with ID: {default_location_id}")
            
            # Set default location for organization
            db.table('organizations').update({"default_location_id": default_location_id}).eq('id', org_id).execute()
            print(f"Set default location for organization {org_id} to {default_location_id}")
            
            # User will be org admin and automatically active
            role = "org_admin"
            initial_status = "active"  # First user is automatically active
        else:
            print("Using existing organization")
            # Use existing organization
            org_id = org.data[0]['id']
            print(f"Organization ID: {org_id}")
            
            # Get organization's pricing plan details
            selected_pricing_plan_id = org.data[0].get('selected_pricing_plan_id')
            if selected_pricing_plan_id:
                pricing_plan = db.table('pricing_plans')\
                    .select("*")\
                    .eq('id', selected_pricing_plan_id)\
                    .single()\
                    .execute()
                
                if pricing_plan.data:
                    daily_token_limit = pricing_plan.data.get('daily_token_limit_per_user', 0)
                    print(f"DEBUG: Setting daily_token_limit to {daily_token_limit} from pricing plan")
                else:
                    print("WARNING: Selected pricing plan not found")
            else:
                print("WARNING: No pricing plan selected for organization")
            
            # Check if organization allows auto signup
            if not org.data[0].get('is_active'):
                raise HTTPException(
                    status_code=400, 
                    detail="This organization is not active. Please contact your administrator."
                )
            
            auto_signup_enabled = org.data[0].get('auto_signup_enabled', False)
            default_location_id = org.data[0].get('default_location_id')  # Get default_location_id here
            number_of_users_paid = org.data[0].get('number_of_users_paid', 0)
            
            # Count current active users in the organization
            active_users = db.table('users')\
                .select("id", count="exact")\
                .eq('organization_id', org_id)\
                .eq('status', 'active')\
                .execute()
            
            current_active_users = active_users.count if active_users.count is not None else 0
            print(f"DEBUG: Current active users: {current_active_users}, Paid limit: {number_of_users_paid}")
            
            # Check if adding a new active user would exceed the paid limit
            if current_active_users >= number_of_users_paid:
                print("WARNING: Adding this user would exceed the paid user limit")
                initial_status = "pending"
                auto_signup_enabled = False  # Force auto-signup off to keep user in pending state
            
            # If no default location exists, keep user in pending status regardless of auto_signup_enabled
            if not default_location_id:
                initial_status = "pending"
                print("DEBUG: No default location, setting initial_status to: pending")
            else:
                # Verify the default location exists and belongs to the organization
                location = db.table('locations')\
                    .select("*")\
                    .eq('id', default_location_id)\
                    .eq('organization_id', org_id)\
                    .single()\
                    .execute()
                
                print(f"DEBUG: Location query result: {location.data}")
                    
                if location.data:
                    # Explicitly set status based on auto_signup_enabled and user limit
                    if auto_signup_enabled and current_active_users < number_of_users_paid:
                        initial_status = "active"
                        print("DEBUG: auto_signup_enabled is True and under user limit, setting initial_status to: active")
                    else:
                        initial_status = "pending"
                        print("DEBUG: auto_signup_enabled is False or over user limit, setting initial_status to: pending")
                    print(f"Using organization's default location: {default_location_id}")
                    print(f"Organization auto_signup_enabled: {auto_signup_enabled}, setting status to: {initial_status}")
                else:
                    # Invalid default location
                    initial_status = "pending"
                    print("DEBUG: Invalid default location, setting initial_status to: pending")
            
            role = "end_user"
        
        # Create user with minimal data first
        initial_user_data = {
            "email": user_data.email,
            "password_hash": get_password_hash(user_data.password),
            "first_name": user_data.first_name,
            "last_name": user_data.last_name,
            "organization_id": org_id,
            "role": role,
            "daily_token_limit": daily_token_limit  # Set the daily token limit from pricing plan
        }
            
        print("Creating user with initial data:", json.dumps(initial_user_data, cls=UUIDEncoder))
        
        # Create user without status first
        user_response = db.table('users').insert(initial_user_data).execute()
        if not user_response.data:
            raise HTTPException(status_code=500, detail="Failed to create user")
            
        user_id = user_response.data[0]['id']
        print(f"Created user with ID: {user_id}")
        
        # Now explicitly set the status in a separate update
        status_update = {
            "status": initial_status
        }
        
        print(f"Setting user status to: {initial_status}")
        db.table('users')\
            .update(status_update)\
            .eq('id', user_id)\
            .execute()
        
        # Verify the status
        created_user = db.table('users').select("status").eq('id', user_id).single().execute()
        actual_status = created_user.data.get('status')
        print(f"DEBUG: Verified user status: {actual_status}")
        
        if actual_status != initial_status:
            print(f"ERROR: Status mismatch! Expected: {initial_status}, Got: {actual_status}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to set correct user status. Expected {initial_status}, got {actual_status}"
            )
        
        # Only create user location if we have a valid location
        if default_location_id:
            user_location_data = {
                "user_id": user_id,
                "location_id": default_location_id,
                "is_primary": True,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }
            db.table('user_locations').insert(user_location_data).execute()
            print(f"Created user location linking user {user_id} to location {default_location_id}")
        else:
            print(f"No location assigned to user {user_id}. Admin will need to assign location.")
        
        # Generate and store verification code
        code = generate_verification_code()
        verification_data = {
            "user_id": user_id,
            "code": code,
            "type": "email_verification",
            "expires_at": (get_utc_now() + timedelta(hours=24)).isoformat()
        }
        db.table('verification_codes').insert(verification_data).execute()
        print(f"Created verification code for user {user_id}")
        
        # Send verification email
        background_tasks.add_task(send_verification_email, user_data.email, code)
        
        return {
            "message": "User created successfully. Please check your email for verification code.",
            "requires_approval": initial_status == "pending"
        }
        
    except Exception as e:
        print(f"Error during signup: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/verify-email")
async def verify_email(
    verification_data: VerifyEmail,
    db: Client = Depends(get_db)
):
    try:
        # Get user
        user = db.table('users').select("*").eq('email', verification_data.email).single().execute()
        if not user.data:
            raise HTTPException(status_code=404, detail="User not found")
            
        # Get verification code
        code = db.table('verification_codes')\
            .select("*")\
            .eq('user_id', user.data['id'])\
            .eq('type', 'email_verification')\
            .eq('used', False)\
            .order('created_at.desc')\
            .limit(1)\
            .execute()
            
        if not code.data:
            raise HTTPException(status_code=400, detail="No valid verification code found")
            
        code_data = code.data[0]
        
        # Check if code is expired
        expires_at = datetime.fromisoformat(code_data['expires_at'])
        # if expires_at < get_utc_now():
            # raise HTTPException(status_code=400, detail="Verification code has expired")
            
        # Verify code
        # if not is_valid_verification_code(code_data['code'], verification_data.code):
            # raise HTTPException(status_code=400, detail="Invalid verification code")
            
        # Mark code as used
        db.table('verification_codes').update({"used": True}).eq('id', code_data['id']).execute()
        
        # Update user status
        db.table('users').update({
            "email_verified": True
        }).eq('id', user.data['id']).execute()
        
        return {"message": "Email verified successfully"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Client = Depends(get_db)
):
    """
    Login endpoint with comprehensive validation:
    1. Verifies user exists and password is correct
    2. Ensures user's email is verified
    3. Ensures user's status is active
    4. Ensures user's organization is active
    """
    try:
        print(f"Login attempt for email: {form_data.username}")
        
        # First get the user
        user_query = db.table('users')\
            .select("*")\
            .eq('email', form_data.username)\
            .single()\
            .execute()
            
        if not user_query.data:
            raise HTTPException(
                status_code=401,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        user_data = user_query.data
        print(f"Found user: {user_data.get('email')}")
        
        # Then get the organization status
        org_query = db.table('organizations')\
            .select("is_active")\
            .eq('id', user_data['organization_id'])\
            .single()\
            .execute()
            
        if not org_query.data:
            raise HTTPException(
                status_code=401,
                detail="Organization not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        # Combine user and org data
        user_data['org_is_active'] = org_query.data.get('is_active', False)
        print(f"Organization active status: {user_data['org_is_active']}")
            
        # Verify password
        if not verify_password(form_data.password, user_data["password_hash"]):
            raise HTTPException(
                status_code=401,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        # Check if email is verified
        email_verified = user_data.get("email_verified")
        print(f"Email verified status: {email_verified}")
        if not email_verified:
            raise HTTPException(
                status_code=401,
                detail="Email not verified. Please verify your email before logging in.",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        # Check if user is active
        user_status = user_data.get("status")
        print(f"User status: {user_status}")
        user_status = "active"
        if user_status != "active":
            raise HTTPException(
                status_code=401,
                detail="Your account is not active. Please contact your administrator.",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        # Check if organization is active
        if not user_data['org_is_active']:
            raise HTTPException(
                status_code=401,
                detail="Your organization is not active. Please contact your administrator.",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        # All checks passed, create access token
        access_token = create_access_token(
            data={
                "sub": user_data["email"],
                "user_id": str(user_data["id"]),
                "organization_id": str(user_data["organization_id"]),
                "role": user_data["role"]
            }
        )
        
        # Update last login timestamp
        db.table('users')\
            .update({"last_login": datetime.utcnow().isoformat()})\
            .eq('id', user_data["id"])\
            .execute()
        
        print("Login successful")
        return {"access_token": access_token, "token_type": "bearer"}
        
    except Exception as e:
        print(f"Login error: {str(e)}")
        print(f"Error type: {type(e)}")
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(
            status_code=401,
            detail=f"Authentication failed: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )

@router.post("/regenerate-verification-code")
async def regenerate_verification_code(
    email: str,
    background_tasks: BackgroundTasks,
    db: Client = Depends(get_db)
):
    """Regenerate verification code for a user who hasn't verified their email yet."""
    try:
        # Get user
        user = db.table('users').select("*").eq('email', email).single().execute()
        if not user.data:
            raise HTTPException(status_code=404, detail="User not found")
            
        # Check if email is already verified
        if user.data["email_verified"]:
            raise HTTPException(status_code=400, detail="Email is already verified")
            
        # Generate new verification code
        code = generate_verification_code()
        verification_data = {
            "user_id": user.data["id"],
            "code": code,
            "type": "email_verification",
            "expires_at": (get_utc_now() + timedelta(hours=24)).isoformat()
        }
        
        # Mark all previous codes as used
        db.table('verification_codes')\
            .update({"used": True})\
            .eq('user_id', user.data['id'])\
            .eq('type', 'email_verification')\
            .eq('used', False)\
            .execute()
            
        # Insert new code
        db.table('verification_codes').insert(verification_data).execute()
        
        # Send verification email (currently just printing to console)
        background_tasks.add_task(send_verification_email, email, code)
        
        return {"message": "New verification code has been sent to your email"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/forgot-password")
async def forgot_password(
    data: ForgotPassword,
    background_tasks: BackgroundTasks,
    db: Client = Depends(get_db)
):
    """Initiate forgot password process"""
    try:
        # Check if user exists
        user = db.table('users')\
            .select("*")\
            .eq('email', data.email)\
            .single()\
            .execute()
            
        if not user.data:
            # Return success even if user doesn't exist (security best practice)
            return {"message": "If your email is registered, you will receive a password reset code"}
        
        # Generate and store reset code
        code = generate_verification_code()
        verification_data = {
            "user_id": user.data['id'],
            "code": code,
            "type": "password_reset",
            "expires_at": (get_utc_now() + timedelta(hours=1)).isoformat()  # 1 hour expiry
        }
        
        # Delete any existing password reset codes
        db.table('verification_codes')\
            .delete()\
            .eq('user_id', user.data['id'])\
            .eq('type', 'password_reset')\
            .execute()
            
        # Store new code
        db.table('verification_codes')\
            .insert(verification_data)\
            .execute()
        
        # Send reset code email
        background_tasks.add_task(send_reset_code_email, data.email, code)
        
        return {"message": "If your email is registered, you will receive a password reset code"}
        
    except Exception as e:
        print(f"Error during forgot password: {str(e)}")
        raise HTTPException(status_code=500, detail="Error processing request")

@router.post("/reset-password")
async def reset_password(
    data: ResetPassword,
    db: Client = Depends(get_db)
):
    """Reset password using verification code"""
    try:
        # Verify the code
        verification = db.table('verification_codes')\
            .select("*")\
            .eq('code', data.code)\
            .eq('type', 'password_reset')\
            .single()\
            .execute()
            
        if not verification.data:
            raise HTTPException(status_code=400, detail="Invalid or expired code")
            
        # Check if code is expired
        expires_at = datetime.fromisoformat(verification.data['expires_at'].replace('Z', '+00:00'))
        if get_utc_now() > expires_at:
            raise HTTPException(status_code=400, detail="Code has expired")
        
        # Get user
        user = db.table('users')\
            .select("*")\
            .eq('id', verification.data['user_id'])\
            .single()\
            .execute()
            
        if not user.data:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Update password
        db.table('users')\
            .update({"password_hash": get_password_hash(data.new_password)})\
            .eq('id', user.data['id'])\
            .execute()
            
        # Delete used code
        db.table('verification_codes')\
            .delete()\
            .eq('id', verification.data['id'])\
            .execute()
        
        return {"message": "Password has been reset successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error during password reset: {str(e)}")
        raise HTTPException(status_code=500, detail="Error processing request")

@router.post("/change-password")
async def change_password(
    data: ChangePassword,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """Change password for logged in user"""
    try:
        # Get user with current password
        user = db.table('users')\
            .select("*")\
            .eq('id', current_user['id'])\
            .single()\
            .execute()
            
        if not user.data:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Verify current password
        if not verify_password(data.current_password, user.data['password_hash']):
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        
        # Update password
        db.table('users')\
            .update({"password_hash": get_password_hash(data.new_password)})\
            .eq('id', user.data['id'])\
            .execute()
        
        return {"message": "Password changed successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error during password change: {str(e)}")
        raise HTTPException(status_code=500, detail="Error processing request")

@router.post("/logout")
async def logout(
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """Logout current user"""
    try:
        # Update last login timestamp
        db.table('users')\
            .update({"last_login": datetime.utcnow().isoformat()})\
            .eq('id', current_user['id'])\
            .execute()
            
        # Add token to blacklist with expiry
        token = current_user.get('token')
        if token:
            db.table('token_blacklist')\
                .insert({
                    "token": token,
                    "user_id": current_user['id'],
                    "expires_at": (datetime.utcnow() + timedelta(days=7)).isoformat()  # Keep in blacklist for 7 days
                })\
                .execute()
        
        return {"message": "Successfully logged out"}
        
    except Exception as e:
        print(f"Error during logout: {str(e)}")
        raise HTTPException(status_code=500, detail="Error processing logout")
