from typing import Dict, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from postgrest import Client
from datetime import datetime
import base64
import mimetypes
from app.db.supabase import get_db, get_supabase
from app.core.auth import get_current_user
from app.schemas.base import UserProfile, UpdateProfile

router = APIRouter()

@router.get("/profile", response_model=UserProfile)
async def get_profile(
    current_user: Dict = Depends(get_current_user),
    db: Client = Depends(get_db),
    supabase_client: Client = Depends(get_supabase)
):
    """Get current user's profile"""
    try:
        # Get user with all fields
        user = db.table('users')\
            .select("""
                id,
                email,
                first_name,
                last_name,
                role,
                status,
                email_verified,
                last_login,
                created_at,
                updated_at,
                chat_tokens_used,
                document_processing_tokens_used,
                daily_chat_tokens_used,
                daily_document_processing_tokens_used,
                daily_token_limit
            """)\
            .eq('id', current_user['id'])\
            .single()\
            .execute()
            
        if not user.data:
            raise HTTPException(status_code=404, detail="User not found")
            
        # Get user's locations
        locations = db.table('user_locations')\
            .select(
                "location_id",
                "is_primary",
                "created_at",
                "updated_at",
                "locations(name)"
            )\
            .eq('user_id', current_user['id'])\
            .execute()
            
        # Format locations data
        user_locations = []
        for loc in locations.data:
            user_locations.append({
                "location_id": loc['location_id'],
                "location_name": loc['locations']['name'],
                "is_primary": loc['is_primary'],
                "created_at": loc['created_at'],
                "updated_at": loc['updated_at']
            })
            
        # Get profile photo URL if it exists
        profile_photo_url = None
        try:
            # Use direct path without 'profiles/' prefix since it's already the bucket name
            profile_photo_path = f"profile-photos/{current_user['id']}.jpg"
            profile_photo_url = supabase_client.storage.from_('profiles').get_public_url(profile_photo_path)
        except Exception as e:
            print(f"Error getting profile photo URL: {e}")
            
        # Combine all data
        profile_data = {
            **user.data,
            "locations": user_locations,
            "profile_photo_url": profile_photo_url
        }
        
        return profile_data
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/profile", response_model=UserProfile)
async def update_profile(
    profile: UpdateProfile,
    current_user: Dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """Update user profile"""
    try:
        update_data = profile.dict(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="No valid update data provided")
            
        # Update user
        updated_user = db.table('users')\
            .update({
                **update_data,
                "updated_at": datetime.utcnow().isoformat()
            })\
            .eq('id', current_user['id'])\
            .execute()
            
        if not updated_user.data:
            raise HTTPException(status_code=404, detail="User not found")
            
        # Return full profile
        return await get_profile(current_user, db)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/profile/photo")
async def update_profile_photo(
    photo: UploadFile = File(...),
    current_user: Dict = Depends(get_current_user),
    supabase_client: Client = Depends(get_supabase)
):
    """Update profile photo"""
    try:
        # Validate file type
        content_type = photo.content_type
        if not content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="File must be an image")
            
        # Read file
        contents = await photo.read()
        if len(contents) > 5 * 1024 * 1024:  # 5MB limit
            raise HTTPException(status_code=400, detail="File too large. Maximum size is 5MB")
            
        # Upload to Supabase storage
        file_path = f"profile-photos/{current_user['id']}.jpg"
        
        # First try to remove the existing file
        try:
            supabase_client.storage\
                .from_('profiles')\
                .remove([file_path])
        except:
            # Ignore error if file doesn't exist
            pass
        
        # Upload new file with proper content type
        supabase_client.storage\
            .from_('profiles')\
            .upload(
                file_path,
                contents,
                {"content-type": "image/jpeg"}
            )
            
        # Get public URL
        photo_url = supabase_client.storage\
            .from_('profiles')\
            .get_public_url(file_path)
            
        return {"message": "Profile photo updated", "url": photo_url}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))