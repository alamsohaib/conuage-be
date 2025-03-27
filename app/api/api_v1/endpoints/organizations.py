from fastapi import APIRouter, Depends, HTTPException
from typing import List
from app.db.supabase import get_db
from app.schemas.base import (
    OrganizationCreate, OrganizationInDB, 
    OrganizationDetail, OrganizationUpdate,
    PricingPlan, PricingPlanSubscription, PricingPlanSubscriptionResponse
)
from app.core.auth import get_current_user, org_admin_only, check_organization_access
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


@router.get("/", response_model=List[OrganizationInDB])
async def list_organizations(db: Client = Depends(get_db)):
    try:
        response = db.table('organizations').select("*").execute()
        return response.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/my-organization", response_model=OrganizationDetail)
async def get_organization(
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """Get detailed information about user's organization"""
    try:
        # Check if user is org_admin
        if current_user["role"] != "org_admin":
            raise HTTPException(status_code=403, detail="Only organization admins can view organization details")
            
        org_id = current_user["organization_id"]
            
        # Get organization with all fields
        org = db.table('organizations')\
            .select("*")\
            .eq('id', str(org_id))\
            .single()\
            .execute()
            
        if not org.data:
            raise HTTPException(status_code=404, detail="Organization not found")
            
        # Get primary contact details if set
        primary_contact = None
        if org.data.get('primary_contact_id'):
            contact = db.table('users')\
                .select("id,email,first_name,last_name")\
                .eq('id', org.data['primary_contact_id'])\
                .single()\
                .execute()
            if contact.data:
                primary_contact = contact.data
                
        # Get default location details if set
        default_location = None
        if org.data.get('default_location_id'):
            location = db.table('locations')\
                .select("id,name")\
                .eq('id', org.data['default_location_id'])\
                .single()\
                .execute()
            if location.data:
                default_location = location.data
                
        # Combine all data
        org_data = {
            **org.data,
            "primary_contact": primary_contact,
            "default_location": default_location
        }
        
        return OrganizationDetail(**org_data)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



    """Get detailed organization information"""
    try:
        # Check if user has access to this organization
        if not await check_organization_access(current_user, org_id, db):
            raise HTTPException(status_code=403, detail="Access to this organization not allowed")
            
        # Check if user is org_admin
        if current_user["role"] != "org_admin":
            raise HTTPException(status_code=403, detail="Only organization admins can view organization details")
            
        # Get organization with all fields
        org = db.table('organizations')\
            .select("*")\
            .eq('id', str(org_id))\
            .single()\
            .execute()
            
        if not org.data:
            raise HTTPException(status_code=404, detail="Organization not found")
            
        # Get primary contact details if set
        primary_contact = None
        if org.data.get('primary_contact_id'):
            contact = db.table('users')\
                .select("id,email,first_name,last_name")\
                .eq('id', org.data['primary_contact_id'])\
                .single()\
                .execute()
            if contact.data:
                primary_contact = contact.data
                
        # Get default location details if set
        default_location = None
        if org.data.get('default_location_id'):
            location = db.table('locations')\
                .select("id,name")\
                .eq('id', org.data['default_location_id'])\
                .single()\
                .execute()
            if location.data:
                default_location = location.data
                
        # Combine all data
        org_data = {
            **org.data,
            "primary_contact": primary_contact,
            "default_location": default_location
        }
        
        return OrganizationDetail(**org_data)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=OrganizationInDB)
async def create_organization(org: OrganizationCreate, db: Client = Depends(get_db)):
    try:
        now = datetime.utcnow().isoformat()
        org_data = json.loads(json.dumps(org.model_dump(exclude_unset=True), cls=UUIDEncoder))
        
        # Remove None values for optional UUID fields
        if org_data.get('primary_contact_id') is None:
            org_data.pop('primary_contact_id', None)
        if org_data.get('default_location_id') is None:
            org_data.pop('default_location_id', None)
            
        org_data.update({
            "created_at": now,
            "updated_at": now
        })
        
        response = db.table('organizations').insert(org_data).execute()
        return response.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/my-organization", response_model=OrganizationDetail)
async def update_organization(
    org_update: OrganizationUpdate,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """Update organization details"""
    try:
        # Check if user is org_admin
        if current_user["role"] != "org_admin":
            raise HTTPException(status_code=403, detail="Only organization admins can update organization details")
            
        org_id = current_user["organization_id"]
            
        # Get current organization
        org = db.table('organizations')\
            .select("*")\
            .eq('id', str(org_id))\
            .single()\
            .execute()
            
        if not org.data:
            raise HTTPException(status_code=404, detail="Organization not found")
            
        # Prepare update data
        update_data = org_update.dict(exclude_unset=True)
        
        # Handle primary contact update if email provided
        if "primary_contact_email" in update_data:
            email = update_data.pop("primary_contact_email")
            if email:
                # Find user by email
                user = db.table('users')\
                    .select("id")\
                    .eq('email', email)\
                    .single()\
                    .execute()
                if not user.data:
                    raise HTTPException(status_code=404, detail=f"User with email {email} not found")
                update_data["primary_contact_id"] = user.data["id"]
                
        # Handle default location update
        if "default_location_id" in update_data:
            location_id = update_data["default_location_id"]
            if location_id:
                # Verify location exists and belongs to organization
                location = db.table('locations')\
                    .select("id")\
                    .eq('id', str(location_id))\
                    .eq('organization_id', str(org_id))\
                    .single()\
                    .execute()
                if not location.data:
                    raise HTTPException(
                        status_code=400,
                        detail="Invalid location ID or location does not belong to this organization"
                    )
                    
        # Update organization
        update_data["updated_at"] = datetime.utcnow().isoformat()
        db.table('organizations')\
            .update(update_data)\
            .eq('id', str(org_id))\
            .execute()
            
        # Return updated organization
        return await get_organization(current_user, db)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



    """Update organization details"""
    try:
        # Check if user has access to this organization
        if not await check_organization_access(current_user, org_id, db):
            raise HTTPException(status_code=403, detail="Access to this organization not allowed")
            
        # Check if user is org_admin
        if current_user["role"] != "org_admin":
            raise HTTPException(status_code=403, detail="Only organization admins can update organization details")
            
        # Get current organization
        org = db.table('organizations')\
            .select("*")\
            .eq('id', str(org_id))\
            .single()\
            .execute()
            
        if not org.data:
            raise HTTPException(status_code=404, detail="Organization not found")
            
        # Prepare update data
        update_data = org_update.dict(exclude_unset=True)
        
        # Handle primary contact update if email provided
        if "primary_contact_email" in update_data:
            email = update_data.pop("primary_contact_email")
            if email:
                # Find user by email
                user = db.table('users')\
                    .select("id")\
                    .eq('email', email)\
                    .single()\
                    .execute()
                if not user.data:
                    raise HTTPException(status_code=404, detail=f"User with email {email} not found")
                update_data["primary_contact_id"] = user.data["id"]
                
        # Handle default location update
        if "default_location_id" in update_data:
            location_id = update_data["default_location_id"]
            if location_id:
                # Verify location exists and belongs to organization
                location = db.table('locations')\
                    .select("id")\
                    .eq('id', str(location_id))\
                    .eq('organization_id', str(org_id))\
                    .single()\
                    .execute()
                if not location.data:
                    raise HTTPException(
                        status_code=400,
                        detail="Invalid location ID or location does not belong to this organization"
                    )
                    
        # Update organization
        update_data["updated_at"] = datetime.utcnow().isoformat()
        db.table('organizations')\
            .update(update_data)\
            .eq('id', str(org_id))\
            .execute()
            
        # Return updated organization
        return await get_organization(org_id, current_user, db)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pricing-plans", response_model=List[PricingPlan])
async def list_pricing_plans(
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """List all available pricing plans"""
    try:
        response = db.table('pricing_plans')\
            .select("*")\
            .eq('is_active', True)\
            .execute()
        return response.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/subscription", response_model=PricingPlanSubscriptionResponse)
async def update_subscription(
    subscription: PricingPlanSubscription,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """Update organization's pricing plan subscription. Only org admins can perform this action."""
    try:
        # Check if user is org_admin
        if current_user["role"] != "org_admin":
            raise HTTPException(
                status_code=403, 
                detail="Only organization admins can update subscription plans"
            )
        
        org_id = current_user["organization_id"]
        
        # Get the pricing plan details
        plan = db.table('pricing_plans')\
            .select("*")\
            .eq('id', str(subscription.pricing_plan_id))\
            .eq('is_active', True)\
            .single()\
            .execute()
            
        if not plan.data:
            raise HTTPException(
                status_code=404,
                detail="Selected pricing plan not found or is inactive"
            )
            
        # Calculate monthly cost
        monthly_cost = plan.data['cost'] * subscription.number_of_users_paid
        
        # Get current timestamp for subscription start
        now = datetime.utcnow()
        
        # Update organization's subscription
        org_update = {
            'selected_pricing_plan_id': str(subscription.pricing_plan_id),
            'number_of_users_paid': subscription.number_of_users_paid,
            'subscription_start_date': now.isoformat(),
            'updated_at': now.isoformat()
        }
        
        updated_org = db.table('organizations')\
            .update(org_update)\
            .eq('id', str(org_id))\
            .execute()
            
        if not updated_org.data:
            raise HTTPException(
                status_code=500,
                detail="Failed to update organization subscription"
            )
            
        # Prepare response
        response = {
            'organization_id': org_id,
            'pricing_plan': plan.data,
            'number_of_users_paid': subscription.number_of_users_paid,
            'subscription_start_date': now,
            'subscription_end_date': None,  # Can be implemented for fixed-term subscriptions
            'monthly_cost': monthly_cost
        }
        
        return response
            
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/subscription", response_model=PricingPlanSubscriptionResponse)
async def get_subscription(
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """Get organization's current pricing plan subscription"""
    try:
        org_id = current_user["organization_id"]
        
        # Get organization details with pricing plan
        org = db.table('organizations')\
            .select("*, pricing_plans(*)")\
            .eq('id', str(org_id))\
            .single()\
            .execute()
            
        if not org.data or not org.data.get('selected_pricing_plan_id'):
            raise HTTPException(
                status_code=404,
                detail="No active subscription found"
            )
            
        # Calculate monthly cost
        monthly_cost = org.data['pricing_plans']['cost'] * org.data['number_of_users_paid']
        
        # Prepare response
        response = {
            'organization_id': org_id,
            'pricing_plan': org.data['pricing_plans'],
            'number_of_users_paid': org.data['number_of_users_paid'],
            'subscription_start_date': org.data['subscription_start_date'],
            'subscription_end_date': org.data.get('subscription_end_date'),
            'monthly_cost': monthly_cost
        }
        
        return response
            
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))
