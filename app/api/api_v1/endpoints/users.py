from fastapi import APIRouter, Depends, HTTPException
from typing import List
from app.db.supabase import get_db
from app.schemas.base import (
    UserManagementCreate, UserManagementUpdate, UserResponse,
    UserLocationCreate, UserLocationUpdate, UserLocationResponse
)
from app.core.auth import get_current_user, check_organization_access, check_location_access
from app.core.security import get_password_hash
from supabase import Client
from datetime import datetime
from uuid import UUID
import json

class UUIDEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

router = APIRouter()

async def get_user_locations(db: Client, user_id: UUID) -> List[UserLocationResponse]:
    """Helper function to get user locations"""
    locations = db.table('user_locations').select("*").eq('user_id', str(user_id)).execute()
    return [UserLocationResponse(**loc) for loc in locations.data]

@router.get("/", response_model=List[UserResponse])
async def list_users(
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """List all users in the organization. Only accessible by org_admin."""
    try:
        # Check if user is org_admin
        if current_user["role"] != "org_admin":
            raise HTTPException(status_code=403, detail="Only organization admins can list users")
            
        # Get all users in the organization
        users = db.table('users').select("*").eq('organization_id', current_user["organization_id"]).execute()
        
        # Get locations for each user
        user_responses = []
        for user in users.data:
            locations = await get_user_locations(db, user["id"])
            user_response = {**user, "locations": locations}
            user_responses.append(user_response)
            
        return user_responses
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """Get user details. Only accessible by org_admin."""
    try:
        # Check if user is org_admin
        if current_user["role"] != "org_admin":
            raise HTTPException(status_code=403, detail="Only organization admins can view user details")
            
        # Get user
        response = db.table('users').select("*").eq('id', str(user_id)).single().execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="User not found")
            
        # Check if user belongs to the same organization
        if str(response.data["organization_id"]) != str(current_user["organization_id"]):
            raise HTTPException(status_code=403, detail="Access to this user not allowed")
            
        # Get user locations
        locations = await get_user_locations(db, user_id)
        user_response = {**response.data, "locations": locations}
            
        return user_response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/", response_model=UserResponse)
async def create_user(
    user_data: UserManagementCreate,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """Create a new user in the organization. Only accessible by org_admin."""
    try:
        # Check if user is org_admin
        if current_user["role"] != "org_admin":
            raise HTTPException(status_code=403, detail="Only organization admins can create users")
            
        # Check if primary location belongs to the organization
        if not await check_location_access(current_user, user_data.location_id, db):
            raise HTTPException(status_code=403, detail="Primary location does not belong to your organization")
            
        # Check if additional locations belong to the organization
        for loc_id in user_data.additional_location_ids:
            if not await check_location_access(current_user, loc_id, db):
                raise HTTPException(status_code=403, detail=f"Location {loc_id} does not belong to your organization")
            
        # Check if email already exists
        existing_user = db.table('users').select("*").eq('email', user_data.email).execute()
        if existing_user.data:
            raise HTTPException(status_code=400, detail="Email already registered")
            
        # Validate role
        valid_roles = ["org_admin", "manager", "end_user"]
        if user_data.role not in valid_roles:
            raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(valid_roles)}")
            
        # Validate status
        valid_statuses = ["pending", "active", "inactive"]
        if user_data.status not in valid_statuses:
            raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}")
        
        # Create user
        now = datetime.utcnow().isoformat()
        user_create_data = {
            "email": user_data.email,
            "password_hash": get_password_hash(user_data.password),
            "first_name": user_data.first_name,
            "last_name": user_data.last_name,
            "organization_id": str(current_user["organization_id"]),
            "role": user_data.role,
            "status": user_data.status,
            "email_verified": True,  # Since org_admin is creating the user
            "created_at": now,
            "updated_at": now
        }
        
        # Create user
        user_response = db.table('users').insert(user_create_data).execute()
        if not user_response.data:
            raise HTTPException(status_code=500, detail="Failed to create user")
            
        user = user_response.data[0]
        
        # Create primary location
        primary_location = {
            "user_id": user["id"],
            "location_id": str(user_data.location_id),
            "is_primary": True,
            "created_at": now,
            "updated_at": now
        }
        db.table('user_locations').insert(primary_location).execute()
        
        # Create additional locations
        additional_locations = [
            {
                "user_id": user["id"],
                "location_id": str(loc_id),
                "is_primary": False,
                "created_at": now,
                "updated_at": now
            }
            for loc_id in user_data.additional_location_ids
        ]
        if additional_locations:
            db.table('user_locations').insert(additional_locations).execute()
            
        # Get all locations for response
        locations = await get_user_locations(db, user["id"])
        user_response = {**user, "locations": locations}
            
        return user_response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    user_data: UserManagementUpdate,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """Update user details. Only accessible by org_admin."""
    try:
        # Check if user is org_admin
        if current_user["role"] != "org_admin":
            raise HTTPException(status_code=403, detail="Only organization admins can update users")
            
        # Get user to update
        user = db.table('users').select("*").eq('id', str(user_id)).single().execute()
        if not user.data:
            raise HTTPException(status_code=404, detail="User not found")
            
        # Check if user belongs to the same organization
        if str(user.data["organization_id"]) != str(current_user["organization_id"]):
            raise HTTPException(status_code=403, detail="Access to this user not allowed")
            
        # If email is being updated, check if it already exists
        if user_data.email and user_data.email != user.data["email"]:
            existing_user = db.table('users').select("*").eq('email', user_data.email).execute()
            if existing_user.data:
                raise HTTPException(status_code=400, detail="Email already registered")
                
        # Validate role if being updated
        if user_data.role:
            valid_roles = ["org_admin", "manager", "end_user"]
            if user_data.role not in valid_roles:
                raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(valid_roles)}")
                
        # Validate status if being updated
        if user_data.status:
            valid_statuses = ["pending", "active", "inactive"]
            if user_data.status not in valid_statuses:
                raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}")
        
        # Update user basic info
        update_data = user_data.model_dump(exclude={"location_id", "additional_location_ids"}, exclude_unset=True)
        update_data["updated_at"] = datetime.utcnow().isoformat()
        
        if update_data:  # Only update if there are fields to update
            response = db.table('users').update(update_data).eq('id', str(user_id)).execute()
            if not response.data:
                raise HTTPException(status_code=500, detail="Failed to update user")
        
        # Handle location updates
        now = datetime.utcnow().isoformat()
        
        # Only process location updates if either location_id or additional_location_ids is provided
        if user_data.location_id is not None or user_data.additional_location_ids is not None:
            # Get current locations
            current_locations = db.table('user_locations')\
                .select("*")\
                .eq('user_id', str(user_id))\
                .execute()
            
            current_primary = next((loc for loc in current_locations.data if loc["is_primary"]), None)
            
            # Determine the primary location
            primary_location_id = None
            if user_data.location_id:
                # Verify the location belongs to the organization
                if not await check_location_access(current_user, user_data.location_id, db):
                    raise HTTPException(status_code=403, detail="Primary location does not belong to your organization")
                primary_location_id = str(user_data.location_id)
            elif current_primary:
                # Keep existing primary if not changing
                primary_location_id = str(current_primary["location_id"])
            elif user_data.additional_location_ids and len(user_data.additional_location_ids) > 0:
                # Use first additional location as primary if no primary specified
                primary_location_id = str(user_data.additional_location_ids[0])
            
            if not primary_location_id:
                raise HTTPException(status_code=400, detail="User must have at least one primary location")
            
            # Build the complete list of locations
            all_location_ids = set()
            all_location_ids.add(primary_location_id)
            
            if user_data.additional_location_ids is not None:
                for loc_id in user_data.additional_location_ids:
                    if not await check_location_access(current_user, loc_id, db):
                        raise HTTPException(status_code=403, detail=f"Location {loc_id} does not belong to your organization")
                    all_location_ids.add(str(loc_id))
            
            # Delete existing locations
            db.table('user_locations').delete().eq('user_id', str(user_id)).execute()
            
            # Insert primary location
            db.table('user_locations').insert({
                "user_id": str(user_id),
                "location_id": primary_location_id,
                "is_primary": True,
                "created_at": now,
                "updated_at": now
            }).execute()
            
            # Insert additional locations (excluding primary)
            additional_locations = [
                {
                    "user_id": str(user_id),
                    "location_id": loc_id,
                    "is_primary": False,
                    "created_at": now,
                    "updated_at": now
                }
                for loc_id in all_location_ids
                if loc_id != primary_location_id
            ]
            
            if additional_locations:
                db.table('user_locations').insert(additional_locations).execute()
        
        # Get updated user with locations for response
        updated_user = db.table('users').select("*").eq('id', str(user_id)).single().execute()
        locations = await get_user_locations(db, user_id)
        user_response = {**updated_user.data, "locations": locations}
            
        return user_response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
