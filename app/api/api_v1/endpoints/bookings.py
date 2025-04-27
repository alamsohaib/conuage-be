from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from app.db.supabase import get_db
from pydantic import BaseModel, EmailStr, constr
from typing import Dict, Optional
from datetime import datetime
import pytz
from supabase import Client
from app.core.mail import send_booking_confirmation_email

router = APIRouter()

class DemoBooking(BaseModel):
    name: constr(min_length=1, max_length=255)
    email: EmailStr
    phone: Optional[constr(max_length=50)] = None
    services_interested: Dict = {}
    how_can_we_help: Optional[str] = None
    where_did_you_hear: Optional[str] = None

@router.post("/demo-booking", status_code=201)
async def book_demo(
    booking: DemoBooking,
    background_tasks: BackgroundTasks,
    db: Client = Depends(get_db)
):
    """Book a demo with the company. This endpoint is public."""
    try:
        now = datetime.now(pytz.UTC).isoformat()
        
        # Check if email already has a recent booking (anti-spam)
        recent_booking = db.table('demo_bookings')\
            .select("created_at")\
            .eq('email', booking.email)\
            .order('created_at', desc=True)\
            .limit(1)\
            .execute()
            
        if recent_booking.data:
            last_booking_time = datetime.fromisoformat(recent_booking.data[0]['created_at'])
            time_diff = datetime.now(pytz.UTC) - last_booking_time
            
            # If less than 1 hour since last booking
            if time_diff.total_seconds() < 3600:
                raise HTTPException(
                    status_code=429,
                    detail="Please wait at least 1 hour between booking requests"
                )
        
        booking_data = {
            "name": booking.name,
            "email": booking.email,
            "phone": booking.phone,
            "services_interested": booking.services_interested,
            "how_can_we_help": booking.how_can_we_help,
            "where_did_you_hear": booking.where_did_you_hear,
            "created_at": now,
            "updated_at": now
        }
        
        response = db.table('demo_bookings').insert(booking_data).execute()
        
        if not response.data:
            raise HTTPException(status_code=500, detail="Failed to create booking")
            
        # Send confirmation email in background
        background_tasks.add_task(
            send_booking_confirmation_email,
            email=booking.email,
            name=booking.name
        )
            
        return {
            "message": "Demo booking created successfully",
            "booking": response.data[0]
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))