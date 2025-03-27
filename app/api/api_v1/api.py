from fastapi import APIRouter
from app.api.api_v1.endpoints import organizations, locations, auth, users, documents, chat, profile

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(profile.router, tags=["profile"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(organizations.router, prefix="/organizations", tags=["organizations"])
api_router.include_router(locations.router, prefix="/locations", tags=["locations"])
api_router.include_router(documents.router, prefix="/document-management", tags=["documents"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
