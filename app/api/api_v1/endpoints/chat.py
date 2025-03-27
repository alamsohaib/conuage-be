from typing import Dict, List, Union
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, UploadFile, Form, File 
from fastapi.responses import StreamingResponse
from postgrest import Client
from datetime import datetime
import json
import logging
import base64
from app.core.config import settings
from app.core.auth import get_current_user
from app.db.supabase import get_db, get_supabase
from app.core.embeddings import get_embeddings
from app.core.clients import get_openai_client
from app.core.ai_models import ai_models, OperationType
from app.schemas.base import (
    ChatCreate, Chat, MessageCreate, Message,
    ChatResponse, ChatListResponse, MessageSource,
    StreamingMessageResponse
)
from app.core.document_processing import generate_image_description

# Set up logging
logger = logging.getLogger(__name__)

# Custom JSON encoder to handle UUID serialization
class UUIDEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, UUID):
            return str(obj)
        return json.JSONEncoder.default(self, obj)

# Constants
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_HISTORY_MESSAGES = 50  # Maximum number of messages to load for context

router = APIRouter()

@router.post("/chats", response_model=Chat)
async def create_chat(
    chat: ChatCreate,
    current_user: Dict = Depends(get_current_user),
    db: Client = Depends(get_db),
    supabase_client: Client = Depends(get_supabase)
):
    """Create a new chat"""
    result = db.table('chats')\
        .insert({
            'name': chat.name,
            'user_id': str(current_user['id']),
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat()
        })\
        .execute()
    
    return Chat(**result.data[0])

@router.get("/chats", response_model=ChatListResponse)
async def list_chats(
    current_user: Dict = Depends(get_current_user),
    db: Client = Depends(get_db),
    supabase_client: Client = Depends(get_supabase)
):
    """List all chats for the current user"""
    result = db.table('chats')\
        .select("*")\
        .eq('user_id', str(current_user['id']))\
        .order('created_at', desc=True)\
        .execute()
    
    return ChatListResponse(chats=[Chat(**chat) for chat in result.data])

@router.get("/chats/{chat_id}", response_model=ChatResponse)
async def get_chat(
    chat_id: UUID,
    current_user: Dict = Depends(get_current_user),
    db: Client = Depends(get_db),
    supabase_client: Client = Depends(get_supabase)
):
    """Get a chat and its messages"""
    # Get chat
    chat = db.table('chats')\
        .select("*")\
        .eq('id', str(chat_id))\
        .eq('user_id', str(current_user['id']))\
        .single()\
        .execute()
    
    if not chat.data:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    # Get messages
    messages = db.table('messages')\
        .select("*")\
        .eq('chat_id', str(chat_id))\
        .order('created_at')\
        .execute()
    
    # Get document names for sources
    for message in messages.data:
        if message.get('sources'):
            try:
                sources = json.loads(message['sources'])
                for source in sources:
                    if source.get('document_id'):
                        doc = db.table('documents')\
                            .select("name")\
                            .eq('id', str(source['document_id']))\
                            .single()\
                            .execute()
                        if doc.data:
                            source['document_name'] = doc.data['name']
                message['sources'] = sources
            except json.JSONDecodeError:
                logger.error(f"Failed to parse sources JSON for message {message.get('id')}")
                message['sources'] = []
    
    return ChatResponse(
        chat=Chat(**chat.data),
        messages=[Message(**msg) for msg in messages.data]
    )

@router.post("/chats/{chat_id}/messages", response_model=Message)
async def create_message(
    chat_id: UUID,
    content: str = Form(...),
    image: Union[UploadFile, None] = None,
    current_user: Dict = Depends(get_current_user),
    db: Client = Depends(get_db),
    supabase_client: Client = Depends(get_supabase)
):
    """Create a new message and get AI response"""
    try:
        # Validate chat access
        chat = db.table('chats')\
            .select("*")\
            .eq('id', str(chat_id))\
            .eq('user_id', str(current_user['id']))\
            .single()\
            .execute()
        
        if not chat.data:
            raise HTTPException(status_code=404, detail="Chat not found")
            
        # Create message object
        message = MessageCreate(content=content)
        
        # Get recent chat history
        chat_history = db.table('messages')\
            .select("*")\
            .eq('chat_id', str(chat_id))\
            .order('created_at')\
            .limit(MAX_HISTORY_MESSAGES)\
            .execute()

        # Save user message
        user_message = db.table('messages')\
            .insert({
                'chat_id': str(chat_id),
                'role': 'user',
                'content': message.content,
                'created_at': datetime.utcnow().isoformat()
            })\
            .execute()
        
        # Process image if provided
        image_description = None
        image_tokens = 0
        image_base64 = None
        if image:
            try:
                contents = await image.read()
                image_base64 = base64.b64encode(contents).decode()
                
                # First vision call to get description for similarity search
                model_config = ai_models.get_model('vision_chat')
                vision_response = await get_openai_client().chat.completions.create(
                    model=model_config.model_id,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": message.content  # Using user's actual question
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{image_base64}",
                                        "detail": "high"
                                    }
                                }
                            ]
                        }
                    ],
                    temperature=model_config.temperature,
                    max_tokens=model_config.max_tokens
                )
                
                image_description = vision_response.choices[0].message.content
                image_tokens = vision_response.usage.total_tokens
                
                # Log vision tokens
                await ai_models.log_token_usage(
                    db=db,
                    user_id=str(current_user['id']),
                    organization_id=str(current_user['organization_id']),
                    model_key='vision_chat',
                    tokens_used=image_tokens,
                    operation_type=OperationType.CHAT,
                    chat_id=str(chat_id)
                )
                
                logger.info(f"Generated image description: {image_description}")
            except Exception as e:
                logger.error(f"Error processing image: {str(e)}")
                raise HTTPException(status_code=500, detail="Error processing image")
        
        # Combine text query with image context if available
        query_text = message.content
        if image_description:
            query_text = f"{message.content} Context from image: {image_description}"
        
        # Get embeddings for the question
        embeddings, embedding_tokens = await get_embeddings(query_text)
        
        # Log embedding tokens
        await ai_models.log_token_usage(
            db=db,
            user_id=str(current_user['id']),
            organization_id=str(current_user['organization_id']),
            model_key='text_embedding',
            tokens_used=embedding_tokens,
            operation_type=OperationType.CHAT,
            chat_id=str(chat_id)
        )
        
        # Get user's accessible locations
        locations = db.table('locations')\
            .select('id')\
            .eq('organization_id', str(current_user['organization_id']))\
            .execute()
        location_ids = [loc['id'] for loc in locations.data]
        
        # Search for similar content across all content types
        similar_content = supabase_client.rpc(
            'search_all_content_types',
            {
                'query_embedding': embeddings[0],
                'match_threshold': 0.2,
                'match_count': 5,
                'location_ids': location_ids
            }
        ).execute()
        
        # Format context for GPT
        context = "Here is relevant information from the documents:\n\n"
        for item in similar_content.data:
            if item['content_type'] == 'text':
                context += f"Text content: {item['content']}\n"
                if item['additional_info']:
                    context += f"(Document ID: {item['additional_info']['document_id']}, Page: {item['additional_info']['page_number']})\n"
            elif item['content_type'] == 'table':
                context += f"Table information: {item['content']}\n"
                if item['additional_info'] and item['additional_info'].get('html_content'):
                    context += f"Table structure: {item['additional_info']['html_content']}\n"
                if item['additional_info']:
                    context += f"(Document ID: {item['additional_info']['document_id']}, Page: {item['additional_info']['page_number']}, Table: {item['additional_info']['table_number']})\n"
            elif item['content_type'] == 'image':
                context += f"Image description: {item['content']}\n"
                if item['additional_info']:
                    context += f"(Document ID: {item['additional_info']['document_id']}, Page: {item['additional_info']['page_number']}, Image: {item['additional_info']['image_number']})\n"
            context += "\n"
        
        # Prepare messages for GPT with chat history
        messages = [
            {"role": "system", "content": "You are a helpful assistant. Use the provided context to answer questions accurately and concisely."}
        ]
        
        # Add chat history
        for msg in chat_history.data:
            messages.append({
                "role": msg['role'],
                "content": msg['content']
            })

        # Add context and current question with image if provided
        if image:
            messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"Context:\n{context}\n\nQuestion: {message.content}"
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}",
                            "detail": "high"
                        }
                    }
                ]
            })
        else:
            messages.append({
                "role": "user", 
                "content": f"Context:\n{context}\n\nQuestion: {message.content}"
            })
        
        # Get model config based on whether image is provided
        model_key = 'vision_chat' if image else 'default_chat'
        model_config = ai_models.get_model(model_key)
        
        print(messages)

        # Get AI response using model config
        response = await get_openai_client().chat.completions.create(
            model=model_config.model_id,
            messages=messages,
            temperature=model_config.temperature,
            max_tokens=model_config.max_tokens
        )

        # Save AI response
        message_data = {
            'chat_id': str(chat_id),
            'content': response.choices[0].message.content,
            'role': 'assistant',
            'created_at': datetime.utcnow().isoformat(),
            'sources': json.dumps([{
                'document_id': str(item['additional_info']['document_id']) if item['additional_info'] and 'document_id' in item['additional_info'] else None,
                'page_number': item['additional_info']['page_number'] if item['additional_info'] and 'page_number' in item['additional_info'] else None,
                'content': item['content'],
                'content_type': item['content_type'],
                'similarity_score': float(item['similarity']),
                'document_name': item['additional_info']['document_name'] if item['additional_info'] and 'document_name' in item['additional_info'] else None,
                'file_path': item['additional_info']['file_path'] if item['additional_info'] and 'file_path' in item['additional_info'] else None
            } for item in similar_content.data])
        }
        ai_message = db.table('messages').insert(message_data).execute()

        # Parse the sources JSON string back into a list for the response
        message_response = dict(ai_message.data[0])
        if message_response.get('sources'):
            message_response['sources'] = json.loads(message_response['sources'])

        # Update chat timestamp
        db.table('chats')\
            .update({'updated_at': datetime.utcnow().isoformat()})\
            .eq('id', str(chat_id))\
            .execute()

        # Log token usage
        await ai_models.log_token_usage(
            db=db,
            user_id=str(current_user['id']),
            organization_id=str(current_user['organization_id']),
            model_key=model_key,
            tokens_used=response.usage.total_tokens,
            operation_type=OperationType.CHAT,
            chat_id=str(chat_id)
        )

        return Message(**message_response)
        
    except Exception as e:
        logger.error(f"Error in create_message: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/chats/{chat_id}/messages/stream")
async def create_message_stream(
    chat_id: UUID,
    content: str = Form(...),
    image: Union[UploadFile, None] = None,
    current_user: Dict = Depends(get_current_user),
    db: Client = Depends(get_db),
    supabase_client: Client = Depends(get_supabase)
) -> StreamingMessageResponse:
    """Create a new message in the chat with streaming response
    
    Returns a stream of StreamingMessageResponse objects
    """
    try:
        # Check image size if provided
        if image:
            # Read a small chunk to get content length
            chunk = await image.read(1024)
            content_length = len(chunk)
            # Seek back to start
            await image.seek(0)
            
            if content_length > MAX_IMAGE_SIZE:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Image too large. Maximum size is {MAX_IMAGE_SIZE/1024/1024}MB"
                )

        # Check if chat exists and user has access
        chat = db.table('chats')\
            .select('*')\
            .eq('id', str(chat_id))\
            .eq('user_id', str(current_user['id']))\
            .single()\
            .execute()

        if not chat.data:
            raise HTTPException(status_code=404, detail="Chat not found")

        # Create MessageCreate instance from form data
        message = MessageCreate(content=content)
        
        # Save user message
        db.table('messages')\
            .insert({
                'chat_id': str(chat_id),
                'content': message.content,
                'role': 'user',
                'created_at': datetime.utcnow().isoformat()
            })\
            .execute()

        # Process image if provided
        image_description = None
        image_tokens = 0
        image_base64 = None
        if image:
            try:
                contents = await image.read()
                image_base64 = base64.b64encode(contents).decode()
                # First vision call to get description for similarity search
                model_config = ai_models.get_model('vision_chat')
                vision_response = await get_openai_client().chat.completions.create(
                    model=model_config.model_id,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": message.content
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{image_base64}",
                                        "detail": "high"
                                    }
                                }
                            ]
                        }
                    ],
                    temperature=model_config.temperature,
                    max_tokens=model_config.max_tokens
                )
                image_description = vision_response.choices[0].message.content
                image_tokens = vision_response.usage.total_tokens
                
                # Log vision tokens
                await ai_models.log_token_usage(
                    db=db,
                    user_id=str(current_user['id']),
                    organization_id=str(current_user['organization_id']),
                    model_key='vision_chat',
                    tokens_used=image_tokens,
                    operation_type=OperationType.CHAT,
                    chat_id=str(chat_id)
                )
                logger.info(f"Generated image description: {image_description}")
            except Exception as e:
                logger.error(f"Error processing image: {str(e)}")
                raise HTTPException(status_code=500, detail="Error processing image")

        # Prepare query for similarity search
        query_text = message.content
        if image_description:
            query_text = f"{message.content} Context from image: {image_description}"

        # Get embeddings for the question
        embeddings, embedding_tokens = await get_embeddings(query_text)
        
        # Log embedding tokens
        await ai_models.log_token_usage(
            db=db,
            user_id=str(current_user['id']),
            organization_id=str(current_user['organization_id']),
            model_key='text_embedding',
            tokens_used=embedding_tokens,
            operation_type=OperationType.CHAT,
            chat_id=str(chat_id)
        )
        
        # Get user's accessible locations
        locations = db.table('locations')\
            .select('id')\
            .eq('organization_id', str(current_user['organization_id']))\
            .execute()
        location_ids = [loc['id'] for loc in locations.data]
        
        # Search for similar content across all content types
        similar_content = supabase_client.rpc(
            'search_all_content_types',
            {
                'query_embedding': embeddings[0],
                'match_threshold': 0.2,
                'match_count': 5,
                'location_ids': location_ids
            }
        ).execute()

        # Get limited chat history
        chat_history = db.table('messages')\
            .select('content,role')\
            .eq('chat_id', str(chat_id))\
            .order('created_at', desc=True)\
            .limit(MAX_HISTORY_MESSAGES)\
            .execute()
        
        # Reverse to get chronological order
        chat_history.data.reverse()

        # Build context from similar content
        context = ""
        for item in similar_content.data:
            if item['content_type'] == 'text':
                context += f"Text content: {item['content']}\n"
                if item['additional_info']:
                    context += f"(Document ID: {item['additional_info']['document_id']}, Page: {item['additional_info']['page_number']})\n"
            elif item['content_type'] == 'table':
                context += f"Table information: {item['content']}\n"
                if item['additional_info'] and item['additional_info'].get('html_content'):
                    context += f"Table structure: {item['additional_info']['html_content']}\n"
                if item['additional_info']:
                    context += f"(Document ID: {item['additional_info']['document_id']}, Page: {item['additional_info']['page_number']}, Table: {item['additional_info']['table_number']})\n"
            elif item['content_type'] == 'image':
                context += f"Image description: {item['content']}\n"
                if item['additional_info']:
                    context += f"(Document ID: {item['additional_info']['document_id']}, Page: {item['additional_info']['page_number']}, Image: {item['additional_info']['image_number']})\n"
            context += "\n"

        # Get chat history
        messages_response = db.table('messages')\
            .select('*')\
            .eq('chat_id', str(chat_id))\
            .order('created_at')\
            .limit(10)\
            .execute()

        # Build messages array for OpenAI
        messages = [{"role": "system", "content": "You are a helpful assistant. Use the provided context to answer questions accurately and concisely."}]

        # Add chat history - only last 5 message pairs
        history = messages_response.data  # Get last 10 messages
        for msg in history[:-1]:  # Exclude the last message (current user message)
            messages.append({
                "role": msg['role'],
                "content": msg['content']
            })

        # Add context and current question with image if provided
        if image:
            messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"Context:\n{context}\n\nQuestion: {message.content}"
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}",
                            "detail": "high"
                        }
                    }
                ]
            })
        else:
            messages.append({
                "role": "user", 
                "content": f"Context:\n{context}\n\nQuestion: {message.content}"
            })

        # Add similar content to messages if any found
        if similar_content.data:
            messages.append({
                "role": "system",
                "content": "Here are some relevant documents I found:\n" + "\n".join([
                    f"- {item['content']} (Score: {item['similarity']:.2f}, Document: {item['additional_info']['document_name']})"
                    for item in similar_content.data
                ])
            })

        # Get model config based on whether image is provided
        model_key = 'vision_chat' if image else 'default_chat'
        model_config = ai_models.get_model(model_key)
        
        # Create streaming response
        stream = await get_openai_client().chat.completions.create(
            model=model_config.model_id,
            messages=messages,
            temperature=model_config.temperature,
            max_tokens=model_config.max_tokens,
            stream=True,
            stream_options={"include_usage": True}
        )

        response_content = []
        last_chunk = None
        async def generate():
            nonlocal last_chunk
            try:
                async for chunk in stream:
                    last_chunk = chunk
                    # Check if chunk has choices and delta content
                    if (hasattr(chunk, 'choices') and 
                        chunk.choices and 
                        hasattr(chunk.choices[0], 'delta') and 
                        hasattr(chunk.choices[0].delta, 'content') and 
                        chunk.choices[0].delta.content is not None):
                        content = chunk.choices[0].delta.content
                        response_content.append(content)
                        yield f"data: {json.dumps({'content': content})}\n\n"
                
                # Save complete message with sources
                complete_response = ''.join(response_content)
                message_data = {
                    'chat_id': str(chat_id),
                    'role': 'assistant',
                    'content': complete_response,
                    'created_at': datetime.utcnow().isoformat(),
                    'sources': json.dumps([{
                        'document_id': str(item['additional_info']['document_id']) if item['additional_info'] and 'document_id' in item['additional_info'] else None,
                        'page_number': item['additional_info']['page_number'] if item['additional_info'] and 'page_number' in item['additional_info'] else None,
                        'content': item['content'],
                        'content_type': item['content_type'],
                        'similarity_score': float(item['similarity']),
                        'document_name': item['additional_info']['document_name'] if item['additional_info'] and 'document_name' in item['additional_info'] else None,
                        'file_path': item['additional_info']['file_path'] if item['additional_info'] and 'file_path' in item['additional_info'] else None
                    } for item in similar_content.data])
                }
                
                # Insert message with sources
                message_response = db.table('messages')\
                    .insert(message_data)\
                    .execute()
                
                # Parse sources for the final message
                final_message = dict(message_response.data[0])
                if final_message.get('sources'):
                    final_message['sources'] = json.loads(final_message['sources'])
                
                # Update chat timestamp
                db.table('chats')\
                    .update({'updated_at': datetime.utcnow().isoformat()})\
                    .eq('id', str(chat_id))\
                    .execute()
                
                # Log token usage only if we have real usage data
                if last_chunk and hasattr(last_chunk, 'usage') and last_chunk.usage:
                    await ai_models.log_token_usage(
                        db=db,
                        user_id=str(current_user['id']),
                        organization_id=str(current_user['organization_id']),
                        model_key=model_key,
                        tokens_used=last_chunk.usage.total_tokens,
                        operation_type=OperationType.CHAT,
                        chat_id=str(chat_id)
                    )
                
                # Send the final message with sources
                yield f"data: {json.dumps({'content': complete_response, 'sources': final_message.get('sources')})}\n\n"
                yield f"data: [DONE]\n\n"
            except Exception as e:
                logger.error(f"Error in generate: {str(e)}")
                raise e

        return StreamingResponse(generate(), media_type="text/event-stream")
        
    except Exception as e:
        logger.error(f"Error in create_message_stream: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/chats/{chat_id}")
async def delete_chat(
    chat_id: UUID,
    current_user: Dict = Depends(get_current_user),
    db: Client = Depends(get_db),
    supabase_client: Client = Depends(get_supabase)
):
    """Delete a chat and all its messages"""
    # Verify chat exists and belongs to user
    chat = db.table('chats')\
        .select("*")\
        .eq('id', str(chat_id))\
        .eq('user_id', str(current_user['id']))\
        .single()\
        .execute()
    
    if not chat.data:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    # Delete chat (messages will be deleted by CASCADE)
    db.table('chats')\
        .delete()\
        .eq('id', str(chat_id))\
        .execute()
    
    return {"message": "Chat deleted successfully"}
