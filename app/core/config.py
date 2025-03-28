from typing import List
from pydantic_settings import BaseSettings
from pydantic import AnyHttpUrl, validator

class Settings(BaseSettings):
    PROJECT_NAME: str = "Document Management API"
    VERSION: str = "1.0.0"
    DESCRIPTION: str = "API for document management and chat system with Supabase backend"
    API_V1_STR: str = "/api/v1"
    
    # CORS Configuration
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl | str] = []

    @validator("BACKEND_CORS_ORIGINS", pre=True)
    def assemble_cors_origins(cls, v: str | List[str]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    # Supabase Configuration
    SUPABASE_URL: str
    SUPABASE_KEY: str
    OPENAI_API_KEY: str
    
    # Document Processing Configuration
    TESSERACT_PATH: str = "C:/Program Files/Tesseract-OCR/tesseract.exe"  # Default Windows path
    ENABLE_OCR: bool = True  # Enable OCR by default for image text extraction
    
    # JWT Configuration
    JWT_SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    class Config:
        case_sensitive = True
        env_file = ".env"

settings = Settings()
