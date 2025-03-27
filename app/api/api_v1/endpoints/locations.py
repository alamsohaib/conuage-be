from fastapi import APIRouter, Depends, HTTPException
from typing import List
from app.db.supabase import get_db
from app.schemas.base import LocationCreate, LocationUpdate, Location
from app.core.auth import get_current_user, check_organization_access
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

@router.post("/", response_model=Location)
async def create_location(
    location: LocationCreate,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    try:
        # Check if user is org_admin
        if current_user["role"] != "org_admin":
            raise HTTPException(status_code=403, detail="Only organization admins can create locations")
            
        # Check if user has access to this organization
        if not await check_organization_access(current_user, location.organization_id, db):
            raise HTTPException(status_code=403, detail="Access to this organization not allowed")
            
        now = datetime.utcnow().isoformat()
        location_data = json.loads(json.dumps(location.model_dump(), cls=UUIDEncoder))
        location_data.update({
            "created_at": now,
            "updated_at": now
        })
        
        response = db.table('locations').insert(location_data).execute()
        return response.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/organization/{org_id}", response_model=List[Location])
async def list_organization_locations(
    org_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    try:
        # Check if user has access to this organization
        if not await check_organization_access(current_user, org_id, db):
            raise HTTPException(status_code=403, detail="Access to this organization not allowed")
            
        response = db.table('locations').select("*").eq('organization_id', str(org_id)).execute()
        return response.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{location_id}", response_model=Location)
async def get_location(
    location_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    try:
        # Get location first to check organization access
        location = db.table('locations').select("*").eq('id', str(location_id)).single().execute()
        if not location.data:
            raise HTTPException(status_code=404, detail="Location not found")
            
        # Check if user has access to this organization
        if not await check_organization_access(current_user, location.data["organization_id"], db):
            raise HTTPException(status_code=403, detail="Access to this organization not allowed")
            
        return location.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/{location_id}", response_model=Location)
async def update_location(
    location_id: UUID,
    location: LocationUpdate,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    try:
        # Check if user is org_admin
        if current_user["role"] != "org_admin":
            raise HTTPException(status_code=403, detail="Only organization admins can update locations")
            
        # Get location first to check organization access
        exists = db.table('locations').select("*").eq('id', str(location_id)).single().execute()
        if not exists.data:
            raise HTTPException(status_code=404, detail="Location not found")
            
        # Check if user has access to this organization
        if not await check_organization_access(current_user, exists.data["organization_id"], db):
            raise HTTPException(status_code=403, detail="Access to this organization not allowed")
        
        # Update location
        now = datetime.utcnow().isoformat()
        update_data = json.loads(json.dumps(location.model_dump(exclude_unset=True), cls=UUIDEncoder))
        update_data["updated_at"] = now
        
        response = db.table('locations').update(update_data).eq('id', str(location_id)).execute()
        return response.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{location_id}")
async def delete_location(
    location_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    try:
        # Check if user is org_admin
        if current_user["role"] != "org_admin":
            raise HTTPException(status_code=403, detail="Only organization admins can delete locations")
            
        # Get location first to check organization access
        exists = db.table('locations').select("*").eq('id', str(location_id)).single().execute()
        if not exists.data:
            raise HTTPException(status_code=404, detail="Location not found")
            
        # Check if user has access to this organization
        if not await check_organization_access(current_user, exists.data["organization_id"], db):
            raise HTTPException(status_code=403, detail="Access to this organization not allowed")
        
        # Delete location
        response = db.table('locations').delete().eq('id', str(location_id)).execute()
        return {"message": "Location deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
