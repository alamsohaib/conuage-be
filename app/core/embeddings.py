from typing import List, Tuple
from app.core.clients import get_openai_client
from app.core.ai_models import ai_models

async def get_embeddings(texts: str | List[str]) -> Tuple[List[List[float]], int]:
    """
    Get embeddings for a text or list of texts using OpenAI's API.
    
    Args:
        texts: Text string or list of text strings to get embeddings for
        
    Returns:
        Tuple of (list of embeddings, total tokens used)
        Each embedding is a list of floats
    """
    try:
        # Get shared OpenAI client
        client = get_openai_client()
        
        # Convert single text to list
        if isinstance(texts, str):
            texts = [texts]
            
        # Ensure all inputs are valid strings and not empty
        texts = [str(text).strip() for text in texts]
        texts = [text for text in texts if text]  # Remove empty strings
        
        if not texts:
            raise ValueError("No valid text content to process")
            
        # Get model configuration
        model_config = ai_models.get_model('text_embedding')
            
        # Get embeddings from OpenAI
        response = await client.embeddings.create(
            model=model_config.model_id,
            input=texts
        )
        
        # Extract embeddings and token usage from response
        embeddings = [data.embedding for data in response.data]
        total_tokens = response.usage.total_tokens
        
        return embeddings, total_tokens
        
    except Exception as e:
        print(f"Error getting embeddings: {str(e)}")
        raise
