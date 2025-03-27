from typing import Optional, List
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from app.core.config import settings
from app.db.supabase import get_db
from supabase import Client
from uuid import UUID

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme), db: Client = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    user = db.table('users').select("*").eq('email', email).single().execute()
    if not user.data:
        raise credentials_exception
    return user.data

def check_user_role(required_roles: List[str]):
    async def role_checker(current_user: dict = Depends(get_current_user)):
        if current_user["role"] not in required_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation not permitted. Required roles: {', '.join(required_roles)}"
            )
        return current_user
    return role_checker

# Role-based permission decorators
def org_admin_only():
    return check_user_role(["org_admin"])

def manager_or_admin():
    return check_user_role(["org_admin", "manager"])

def all_authenticated_users():
    return check_user_role(["org_admin", "manager", "end_user"])

async def check_organization_access(user_data: dict, org_id: UUID, db: Client) -> bool:
    """Check if user has access to the specified organization"""
    return str(user_data["organization_id"]) == str(org_id)

# async def check_location_access(user_data: dict, location_id: UUID, db: Client) -> bool:
#     """Check if user has access to the specified location"""
#     location = db.table('locations').select("*").eq('id', str(location_id)).single().execute()
#     print('result: ',location.data["organization_id"]) == str(user_data["organization_id"])
#     print('result2: ',str(location.data["organization_id"]) , str(user_data["organization_id"]))
#     print('result3: ', str(location.data["organization_id"]) == str(user_data["organization_id"]))
#     if not location.data:
#         return False
#     return str(location.data["organization_id"]) == str(user_data["organization_id"])

async def check_location_access(user_data: dict, location_id: UUID, db: Client) -> bool:
    """Check if user has access to the specified location"""
    print('location_id: ',location_id)
    location = db.table('locations').select("*").eq('id', str(location_id)).single().execute()
    print('location_id: ',location)
    
    # Check if the result is empty or contains no data
    if not location.data:
        print("No location found")
        return False

    # Check if organization_id matches
    return str(location.data["organization_id"]) == str(user_data["organization_id"])
