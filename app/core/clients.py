from openai import AsyncOpenAI
from app.core.config import settings

# Global variable to store the client
_openai_client = None

def init_openai_client(api_key: str = None) -> AsyncOpenAI:
    """Initialize the global OpenAI client."""
    global _openai_client
    if not _openai_client:
        _openai_client = AsyncOpenAI(api_key=api_key or settings.OPENAI_API_KEY)
    return _openai_client

def get_openai_client() -> AsyncOpenAI:
    """Get the global OpenAI client."""
    if not _openai_client:
        return init_openai_client()
    return _openai_client

async def close_openai_client() -> None:
    """Close the OpenAI client connection."""
    global _openai_client
    if _openai_client:
        await _openai_client.close()
        _openai_client = None