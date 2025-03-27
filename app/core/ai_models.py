from enum import Enum
from typing import Dict, Optional, Tuple
from pydantic import BaseModel
from datetime import datetime

class TokenType(str, Enum):
    """Token types matching the database constraints"""
    CHAT = "chat"
    TEXT_EMBEDDING = "text_embedding"
    EMBEDDING = "embedding"
    TABLE_EMBEDDING = "table_embedding"
    IMAGE_EMBEDDING = "image_embedding"
    VISION = "vision"

class OperationType(str, Enum):
    """Operation types matching the database constraints"""
    CHAT = "chat"
    DOCUMENT_PROCESSING = "document_processing"

class ModelConfig(BaseModel):
    """Configuration for an AI model"""
    model_id: str
    max_tokens: int
    temperature: float
    token_type: TokenType

class AIModels:
    """Centralized configuration for AI models"""
    
    def __init__(self):
        self._models = {
            # Chat models
            "default_chat": ModelConfig(
                model_id="gpt-4o",
                max_tokens=1000,
                temperature=0.7,
                token_type=TokenType.CHAT
            ),
            "vision_chat": ModelConfig(
                model_id="gpt-4o-mini",  # Your current vision model
                max_tokens=1000,
                temperature=0.7,
                token_type=TokenType.VISION
            ),
            
            # Embedding models
            "text_embedding": ModelConfig(
                model_id="text-embedding-3-large",  # Your current embedding model
                max_tokens=8191,
                temperature=0.0,
                token_type=TokenType.EMBEDDING
            ),
            "table_embedding": ModelConfig(
                model_id="text-embedding-3-large",
                max_tokens=8191,
                temperature=0.0,
                token_type=TokenType.TABLE_EMBEDDING
            ),
            "image_embedding": ModelConfig(
                model_id="text-embedding-3-large",
                max_tokens=8191,
                temperature=0.0,
                token_type=TokenType.IMAGE_EMBEDDING
            )
        }
    
    def get_model(self, model_key: str) -> ModelConfig:
        """Get model configuration by key"""
        if model_key not in self._models:
            raise ValueError(f"Unknown model key: {model_key}")
        return self._models[model_key]
    
    def update_model(self, model_key: str, config: ModelConfig) -> None:
        """Update model configuration"""
        if model_key not in self._models:
            raise ValueError(f"Unknown model key: {model_key}")
        self._models[model_key] = config

    async def log_token_usage(
        self,
        db,
        user_id: str,
        organization_id: str,
        model_key: str,
        tokens_used: int,
        operation_type: OperationType,
        document_id: Optional[str] = None,
        chat_id: Optional[str] = None
    ) -> None:
        """Log token usage to the token_logs table"""
        model = self.get_model(model_key)
        
        db.table('token_logs')\
            .insert({
                'user_id': user_id,
                'organization_id': organization_id,
                'token_type': model.token_type,
                'operation_type': operation_type,
                'tokens_used': tokens_used,
                'document_id': document_id,
                'chat_id': chat_id,
                'model': model.model_id,
                'created_at': datetime.utcnow().isoformat()
            })\
            .execute()

# Global instance
ai_models = AIModels()