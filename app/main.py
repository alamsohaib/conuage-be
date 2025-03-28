from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.api_v1.api import api_router
from app.db.supabase import create_supabase_client
import logging
import sys

import contextlib
from app.core.clients import init_openai_client, close_openai_client

# Configure root logger to ERROR to suppress most third-party logs
logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Configure app-specific logging
app_logger = logging.getLogger('app')
app_logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)
app_logger.handlers = [handler]  # Replace any existing handlers

# Explicitly set third-party loggers to ERROR
logging.getLogger('uvicorn').setLevel(logging.ERROR)
logging.getLogger('asyncio').setLevel(logging.ERROR)
logging.getLogger('urllib3').setLevel(logging.ERROR)
logging.getLogger('PIL').setLevel(logging.ERROR)

# Test logging configuration
logger = logging.getLogger('app')
logger.debug("App logging configured successfully at DEBUG level")

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize AsyncOpenAI client
    init_openai_client()
    
    yield
    
    # Cleanup
    await close_openai_client()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Document Management API with Supabase backend",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# Set all CORS enabled origins
if settings.BACKEND_CORS_ORIGINS:
    origins = [str(origin) for origin in settings.BACKEND_CORS_ORIGINS]
    if "*" in origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    else:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

# Initialize Supabase client in app state
app.state.supabase = create_supabase_client()

# Include API router
app.include_router(api_router, prefix=settings.API_V1_STR)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
