from typing import Generator
from supabase import create_client, Client
from app.core.config import settings
from fastapi import Request

def create_supabase_client() -> Client:
    """Create a new Supabase client instance."""
    return create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_KEY
    )

def get_db(request: Request) -> Generator:
    """Get database client from FastAPI state."""
    try:
        yield request.app.state.supabase.postgrest
    finally:
        pass

def get_supabase(request: Request) -> Generator:
    """Get Supabase client from FastAPI state."""
    try:
        yield request.app.state.supabase
    finally:
        pass
