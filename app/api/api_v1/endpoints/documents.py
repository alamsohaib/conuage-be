from typing import List, Dict, Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from postgrest import Client
from postgrest.exceptions import APIError
import json
import os
import logging
import mimetypes
import io
import pypdf
import pdfplumber
import urllib.request
from datetime import datetime
from typing import List
from urllib.parse import urlparse
from urllib.parse import urljoin
import fitz

from app.db.supabase import get_db, get_supabase
from app.schemas.base import (
    Folder, FolderCreate, FolderUpdate,
    Document, DocumentCreate, DocumentUpdate,
    User, DocumentEmbedding, DocumentProcessResponse,
    DocumentDeleteResponse, FolderDeleteResponse
)
from app.core.auth import get_current_user
from app.core.embeddings import get_embeddings
from app.core.document_processing import (
    extract_tables_from_pdf,
    extract_images_from_pdf,
    generate_table_description,
    generate_image_description,
    save_image_to_storage,
    extract_text
)
from app.core.ai_models import ai_models, TokenType, OperationType

# Set up logging
logger = logging.getLogger(__name__)

# Constants
MAX_FILE_SIZE = 40 * 1024 * 1024  # 40MB in bytes
ALLOWED_FILE_TYPES = {
    # Images
    'image/jpeg': '.jpg',
    'image/png': '.png',
    'image/gif': '.gif',
    'image/tiff': '.tiff',
    'image/bmp': '.bmp',
    'image/webp': '.webp',
    # PDFs
    'application/pdf': '.pdf',
}

class UUIDEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

router = APIRouter()

@router.post("/folders/", response_model=Folder)
async def create_folder(
    folder: FolderCreate,
    current_user: Dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """Create a new folder"""
    # Check if user has access to location
    location_access = db.table('user_locations')\
        .select("*")\
        .eq('user_id', str(current_user["id"]))\
        .eq('location_id', str(folder.location_id))\
        .execute()
        
    if not location_access.data:
        raise HTTPException(status_code=403, detail="No access to this location")
    
    # Check if user is org_admin or manager
    if current_user["role"] not in ['org_admin', 'manager']:
        raise HTTPException(status_code=403, detail="Only org admins and managers can create folders")
    
    # If parent_folder_id is provided, verify it exists and is in the same location
    if folder.parent_folder_id:
        parent_folder = db.table('folders')\
            .select("*")\
            .eq('id', str(folder.parent_folder_id))\
            .eq('location_id', str(folder.location_id))\
            .execute()
            
        if not parent_folder.data:
            raise HTTPException(status_code=404, detail="Parent folder not found or not in the same location")
    
    # Convert UUIDs to strings for JSON serialization
    folder_data = json.loads(json.dumps(folder.dict(), cls=UUIDEncoder))
    folder_data.update({
        'created_by': str(current_user["id"]),
        'created_at': datetime.utcnow().isoformat(),
        'updated_at': datetime.utcnow().isoformat()
    })
    
    try:
        result = db.table('folders').insert(folder_data).execute()
        return result.data[0]
    except APIError as e:
        logger.error(f"Error creating folder: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create folder")

@router.get("/folders/", response_model=List[Folder])
async def list_folders(
    location_id: UUID,
    parent_folder_id: UUID = None,
    current_user: Dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """List folders in a location"""
    # Check if user has access to location
    location_access = db.table('user_locations')\
        .select("*")\
        .eq('user_id', str(current_user["id"]))\
        .eq('location_id', str(location_id))\
        .execute()
        
    if not location_access.data:
        raise HTTPException(status_code=403, detail="No access to this location")
    
    query = db.table('folders')\
        .select("*")\
        .eq('location_id', str(location_id))
        
    if parent_folder_id:
        query = query.eq('parent_folder_id', str(parent_folder_id))
    else:
        query = query.is_('parent_folder_id', 'null')
        
    try:
        folders = query.execute()
        return folders.data
    except APIError as e:
        logger.error(f"Error listing folders: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to list folders")

@router.put("/folders/{folder_id}", response_model=Folder)
async def update_folder(
    folder_id: UUID,
    folder: FolderUpdate,
    current_user: Dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """Update a folder"""
    # Get folder details
    existing_folder = db.table('folders')\
        .select("*")\
        .eq('id', str(folder_id))\
        .single()\
        .execute()
        
    if not existing_folder.data:
        raise HTTPException(status_code=404, detail="Folder not found")
        
    # Check if user has access to location
    location_access = db.table('user_locations')\
        .select("*")\
        .eq('user_id', str(current_user["id"]))\
        .eq('location_id', str(existing_folder.data["location_id"]))\
        .execute()
        
    if not location_access.data:
        raise HTTPException(status_code=403, detail="No access to this location")
    
    # Check if user is org_admin or manager
    if current_user["role"] not in ['org_admin', 'manager']:
        raise HTTPException(status_code=403, detail="Only org admins and managers can update folders")
    
    folder_data = json.loads(json.dumps(folder.dict(exclude_unset=True), cls=UUIDEncoder))
    folder_data.update({
        'updated_at': datetime.utcnow().isoformat()
    })
    
    try:
        updated_folder = db.table('folders')\
            .update(folder_data)\
            .eq('id', str(folder_id))\
            .execute()
        return updated_folder.data[0]
    except APIError as e:
        logger.error(f"Error updating folder: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to update folder")

@router.post("/documents/", response_model=Document)
async def create_document(
    name: Annotated[str, Form()],
    folder_id: Annotated[UUID, Form()],
    file: UploadFile = File(...),
    current_user: Dict = Depends(get_current_user),
    db: Client = Depends(get_db),
    supabase_client: Client = Depends(get_supabase)
):
    """Upload a new document"""
    # Validate file type first
    content_type = file.content_type
    if content_type not in ALLOWED_FILE_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type. Allowed types are: {', '.join(ALLOWED_FILE_TYPES.values())}"
        )
    
    # Get file extension and create file path
    file_ext = ALLOWED_FILE_TYPES[content_type]
    file_path = f"documents/{folder_id}/{name}{file_ext}"
    
    # Read and validate file size
    file_content = await file.read()
    if len(file_content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size allowed is {MAX_FILE_SIZE/1024/1024}MB"
        )
    
    document = DocumentCreate(
        name=name,
        folder_id=folder_id,
        file_path=file_path,
        file_type=content_type,
        page_count=0,  # This will be updated after processing
        status="added"
    )
    
    # Check if user has access to folder
    folder = db.table('folders')\
        .select("*")\
        .eq('id', str(document.folder_id))\
        .single()\
        .execute()
        
    if not folder.data:
        raise HTTPException(status_code=404, detail="Folder not found")
        
    # Check if user has access to location
    location_access = db.table('user_locations')\
        .select("*")\
        .eq('user_id', str(current_user["id"]))\
        .eq('location_id', str(folder.data["location_id"]))\
        .execute()
        
    if not location_access.data:
        raise HTTPException(status_code=403, detail="No access to this location")
    
    # Check if user is org_admin or manager
    if current_user["role"] not in ['org_admin', 'manager']:
        raise HTTPException(status_code=403, detail="Only org admins and managers can upload documents")
    
    try:
        # Upload file to storage using bytes
        storage_response = supabase_client.storage.from_('documents').upload(
            file_path,
            file_content,
            {"content-type": content_type}
        )
        
        if not storage_response:
            raise HTTPException(status_code=500, detail="Failed to upload file to storage")
            
        # Get the public URL for the file
        file_url = supabase_client.storage.from_('documents').get_public_url(file_path)
        
        # Also store the relative path for easier access
        relative_path = file_path  # This is already in the format "documents/folder_id/filename.ext"
        
        # Convert document data to JSON-safe format
        document_data = json.loads(json.dumps(document.dict(), cls=UUIDEncoder))
        document_data.update({
            'created_by': str(current_user["id"]),
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat(),
            'file_path': relative_path  # Store the relative path instead of full URL
        })
        
        # Save document metadata to database
        try:
            result = db.table('documents')\
                .insert(document_data)\
                .execute()
            return result.data[0]
        except APIError as e:
            logger.error(f"Error creating document: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to create document")
        
    except Exception as e:
        # If anything fails, try to clean up the uploaded file
        try:
            supabase_client.storage.from_("documents").remove([file_path])
        except:
            pass
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/documents/", response_model=List[Document])
async def list_documents(
    folder_id: UUID,
    current_user: Dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """List documents in a folder"""
    # Get folder details
    folder = db.table('folders')\
        .select("*")\
        .eq('id', str(folder_id))\
        .single()\
        .execute()
        
    if not folder.data:
        raise HTTPException(status_code=404, detail="Folder not found")
        
    # Check if user has access to location
    location_access = db.table('user_locations')\
        .select("*")\
        .eq('user_id', str(current_user["id"]))\
        .eq('location_id', str(folder.data["location_id"]))\
        .execute()
        
    if not location_access.data:
        raise HTTPException(status_code=403, detail="No access to this location")
    
    try:
        documents = db.table('documents')\
            .select("*")\
            .eq('folder_id', str(folder_id))\
            .execute()
        return documents.data
    except APIError as e:
        logger.error(f"Error listing documents: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to list documents")

@router.put("/documents/{document_id}", response_model=Document)
async def update_document(
    document_id: UUID,
    document: DocumentUpdate,
    current_user: Dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """Update a document's metadata"""
    # Get document details
    existing_document = db.table('documents')\
        .select("*, folders!inner(*)")\
        .eq('id', str(document_id))\
        .single()\
        .execute()
        
    if not existing_document.data:
        raise HTTPException(status_code=404, detail="Document not found")
        
    # Check if user has access to location
    location_access = db.table('user_locations')\
        .select("*")\
        .eq('user_id', str(current_user["id"]))\
        .eq('location_id', str(existing_document.data["folders"]["location_id"]))\
        .execute()
        
    if not location_access.data:
        raise HTTPException(status_code=403, detail="No access to this location")
    
    # Check if user is org_admin or manager
    if current_user["role"] not in ['org_admin', 'manager']:
        raise HTTPException(status_code=403, detail="Only org admins and managers can update documents")
    
    # Convert document data to JSON-safe format
    document_data = json.loads(json.dumps(document.dict(exclude_unset=True), cls=UUIDEncoder))
    document_data.update({
        'updated_at': datetime.utcnow().isoformat()
    })
    
    try:
        updated_document = db.table('documents')\
            .update(document_data)\
            .eq('id', str(document_id))\
            .execute()
        return updated_document.data[0]
    except APIError as e:
        logger.error(f"Error updating document: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to update document")

@router.post("/documents/process/{document_id}", response_model=DocumentProcessResponse)
async def process_document(
    document_id: UUID,
    background_tasks: BackgroundTasks,
    current_user: Dict = Depends(get_current_user),
    db: Client = Depends(get_db),
    supabase_client: Client = Depends(get_supabase)
):
    """Process a document to generate embeddings"""
    try:
        # Get document metadata
        document = db.table('documents')\
            .select("*")\
            .eq('id', str(document_id))\
            .single()\
            .execute()
            
        if not document.data:
            raise HTTPException(status_code=404, detail="Document not found")
            
        # Check if document status is valid for processing
        if document.data['status'] != 'added':
            raise HTTPException(
                status_code=400, 
                detail=f"Document cannot be processed. Current status: {document.data['status']}. Only documents with 'added' status can be processed."
            )
        
        # Get folder to check permissions
        folder = db.table('folders')\
            .select("*")\
            .eq('id', str(document.data['folder_id']))\
            .single()\
            .execute()
            
        if not folder.data:
            raise HTTPException(status_code=404, detail="Folder not found")
        
        # Check if user has access to location
        location_access = db.table('user_locations')\
            .select("*")\
            .eq('user_id', str(current_user["id"]))\
            .eq('location_id', str(folder.data['location_id']))\
            .execute()
            
        if not location_access.data:
            raise HTTPException(status_code=403, detail="No access to this location")
        
        # Check user's daily token usage
        user_tokens = db.table('users')\
            .select(
                "daily_chat_tokens_used",
                "daily_document_processing_tokens_used",
                "daily_token_limit"
            )\
            .eq('id', str(current_user["id"]))\
            .single()\
            .execute()
            
        if not user_tokens.data:
            raise HTTPException(status_code=404, detail="User token information not found")
            
        total_daily_tokens = user_tokens.data['daily_chat_tokens_used'] + user_tokens.data['daily_document_processing_tokens_used']
        daily_limit = user_tokens.data['daily_token_limit']
        
        if total_daily_tokens >= daily_limit:
            raise HTTPException(
                status_code=429,  # Too Many Requests
                detail=f"Daily token limit reached. Used {total_daily_tokens} out of {daily_limit} tokens. Please try again tomorrow."
            )
        
        # Check if user is org_admin or manager
        if current_user["role"] not in ['org_admin', 'manager']:
            raise HTTPException(status_code=403, detail="Only org admins and managers can process documents")
        
        # Update document status to 'processing'
        try:
            db.table('documents')\
                .update({'status': 'processing', 'updated_at': 'NOW()'})\
                .eq('id', str(document_id))\
                .execute()
        except APIError as e:
            logger.error(f"Error updating document status to processing: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to update document status")
        
        # Add to background tasks
        background_tasks.add_task(
            process_document_background,
            document_id=document_id,
            document=document.data,
            folder=folder.data,
            current_user=current_user,
            db=db,
            supabase_client=supabase_client
        )
        
        return {
            "message": "Document processing started",
            "document_id": document_id,
            "total_pages_processed": 0  # Initial value since processing hasn't started yet
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting document processing: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

async def process_document_background(
    document_id: UUID,
    document: Dict,
    folder: Dict,
    current_user: Dict,
    db: Client,
    supabase_client: Client
):
    """Background task to process document"""
    temp_bucket = 'temp-processing'
    temp_file_path = None
    
    try:
        # Delete existing embeddings and content before reprocessing
        try:
            db.table('document_embeddings')\
                .delete()\
                .eq('document_id', str(document_id))\
                .execute()
                
            db.table('document_tables')\
                .delete()\
                .eq('document_id', str(document_id))\
                .execute()
                
            db.table('document_images')\
                .delete()\
                .eq('document_id', str(document_id))\
                .execute()
        except APIError as e:
            logger.error(f"Error cleaning up existing content: {str(e)}")
        
        # Get document from storage and copy to temp bucket
        try:
            # Generate a unique temp file path
            temp_file_path = f"temp/{document_id}/{os.path.basename(document['file_path'])}"
            
            # Download from documents bucket
            file_data = supabase_client.storage.from_('documents').download(document['file_path'])
            
            # Upload to temp bucket
            supabase_client.storage.from_(temp_bucket).upload(
                temp_file_path,
                file_data,
                {"content-type": document['file_type']}
            )
            
            # Get the signed URL that will work with external libraries
            temp_url = supabase_client.storage.from_(temp_bucket).create_signed_url(
                temp_file_path,
                60 * 15  # 15 minutes expiry
            )
            
        except Exception as e:
            raise Exception(f"Error preparing document for processing: {str(e)}")
        
        # Process the PDF using the signed URL
        try:
            # Download PDF content
            response = urllib.request.urlopen(temp_url['signedURL'])
            pdf_bytes = io.BytesIO(response.read())
            
            # Open with pdfplumber for text and table extraction
            plumber_pdf = pdfplumber.open(pdf_bytes)
            
            # Open with PyMuPDF for image extraction
            pdf_bytes.seek(0)  # Reset buffer position
            fitz_pdf = fitz.open(stream=pdf_bytes, filetype="pdf")
            
            logger.debug(f"Successfully opened PDF with {len(plumber_pdf.pages)} pages")
            
        except Exception as e:
            raise Exception(f"Error reading PDF file: {str(e)}")
        
        # Process each page
        total_text_tokens = 0
        total_table_tokens = 0
        total_image_tokens = 0
        total_vision_tokens = 0
        
        for page_number, plumber_page in enumerate(plumber_pdf.pages, start=1):
            try:
                # Get corresponding PyMuPDF page
                fitz_page = fitz_pdf[page_number - 1]
                
                # Extract and process text using pdfplumber
                text_content = extract_text(plumber_page)
                
                if text_content and text_content.strip():
                    text_embeddings, text_tokens = await get_embeddings(text_content)
                    total_text_tokens += text_tokens
                    
                    # Save text embeddings
                    try:
                        db.table('document_embeddings')\
                            .insert({
                                'document_id': str(document_id),
                                'content': text_content,
                                'embedding': text_embeddings[0],
                                'page_number': page_number,
                                'content_type': 'text',
                                'location_id': str(folder['location_id'])
                            })\
                            .execute()
                    except APIError as e:
                        logger.error(f"Error saving text embedding: {str(e)}")
                
                # Extract and process tables using pdfplumber
                tables = extract_tables_from_pdf(plumber_page)
                
                # Extract and process images using PyMuPDF
                images = extract_images_from_pdf(fitz_page)
                
                # Process tables
                for table in tables:
                    try:
                        description, table_tokens = await generate_table_description(table)
                        total_table_tokens += table_tokens
                        
                        if description and description.strip():
                            table_embedding, embedding_tokens = await get_embeddings(description)
                            total_table_tokens += embedding_tokens
                            
                            try:
                                db.table('document_tables')\
                                    .insert({
                                        'document_id': str(document_id),
                                        'page_number': page_number,
                                        'table_number': table['table_number'],
                                        'content': table['content'],
                                        'html_content': table['html_content'],
                                        'description': description,
                                        'embedding': table_embedding[0],
                                        'location_id': str(folder['location_id'])
                                    })\
                                    .execute()
                            except APIError as e:
                                logger.error(f"Error saving table: {str(e)}")
                    except Exception as e:
                        logger.error(f"Error processing table: {str(e)}")
                        continue
                
                # Process images
                for image in images:
                    try:
                        # Generate image description
                        description, vision_tokens = await generate_image_description(
                            image['image_data'],
                            image.get('ocr_text', '')
                        )
                        total_vision_tokens += vision_tokens
                        
                        if description and description.strip():
                            # Save image to storage
                            storage_path = await save_image_to_storage(
                                image['image_data'],
                                document_id,
                                page_number,
                                image['image_number'],
                                supabase_client
                            )
                            
                            # Get embedding for the description
                            image_embedding, image_tokens = await get_embeddings(description)
                            total_image_tokens += image_tokens
                            
                            try:
                                db.table('document_images')\
                                    .insert({
                                        'document_id': str(document_id),
                                        'page_number': page_number,
                                        'image_number': image['image_number'],
                                        'storage_path': storage_path,
                                        'description': description,
                                        'embedding': image_embedding[0],
                                        'location_id': str(folder['location_id'])
                                    })\
                                    .execute()
                            except APIError as e:
                                logger.error(f"Error saving image: {str(e)}")
                    except Exception as e:
                        logger.error(f"Error processing image: {str(e)}")
                        continue
                    
            except Exception as e:
                logger.error(f"Error processing page {page_number}: {str(e)}")
                continue
        
        # Log tokens using ai_models
        if total_text_tokens > 0:
            await ai_models.log_token_usage(
                db=db,
                user_id=str(current_user['id']),
                organization_id=str(current_user['organization_id']),
                model_key='text_embedding',
                tokens_used=total_text_tokens,
                operation_type=OperationType.DOCUMENT_PROCESSING,
                document_id=str(document_id)
            )
            
        if total_table_tokens > 0:
            await ai_models.log_token_usage(
                db=db,
                user_id=str(current_user['id']),
                organization_id=str(current_user['organization_id']),
                model_key='table_embedding',
                tokens_used=total_table_tokens,
                operation_type=OperationType.DOCUMENT_PROCESSING,
                document_id=str(document_id)
            )
            
        if total_image_tokens > 0:
            await ai_models.log_token_usage(
                db=db,
                user_id=str(current_user['id']),
                organization_id=str(current_user['organization_id']),
                model_key='image_embedding',
                tokens_used=total_image_tokens,
                operation_type=OperationType.DOCUMENT_PROCESSING,
                document_id=str(document_id)
            )
            
        if total_vision_tokens > 0:
            await ai_models.log_token_usage(
                db=db,
                user_id=str(current_user['id']),
                organization_id=str(current_user['organization_id']),
                model_key='vision_chat',
                tokens_used=total_vision_tokens,
                operation_type=OperationType.DOCUMENT_PROCESSING,
                document_id=str(document_id)
            )
        
        # Update document status and page count
        try:
            db.table('documents')\
                .update({
                    'status': 'processed',
                    'updated_at': 'NOW()',
                    'page_count': len(plumber_pdf.pages)
                })\
                .eq('id', str(document_id))\
                .execute()
        except APIError as e:
            logger.error(f"Error updating document status: {str(e)}")
            raise Exception("Failed to update document status")
            
    except Exception as e:
        logger.error(f"Error in background processing: {str(e)}")
        try:
            # Update document status to error
            db.table('documents')\
                .update({
                    'status': 'error',
                    'updated_at': 'NOW()'
                })\
                .eq('id', str(document_id))\
                .execute()
        except:
            pass
    finally:
        # Cleanup temp file from Supabase storage
        if temp_file_path:
            try:
                supabase_client.storage.from_(temp_bucket).remove([temp_file_path])
            except Exception as e:
                logger.error(f"Error cleaning up temp file: {str(e)}")
        
        # Close pdfplumber file if it was opened
        try:
            if 'plumber_pdf' in locals():
                plumber_pdf.close()
        except:
            pass

@router.delete("/documents/{document_id}", response_model=DocumentDeleteResponse)
async def delete_document(
    document_id: UUID,
    current_user: Dict = Depends(get_current_user),
    db: Client = Depends(get_db),
    supabase_client: Client = Depends(get_supabase)
):
    """Delete a document and its associated files"""
    # Get document details
    document = db.table('documents')\
        .select("*")\
        .eq('id', str(document_id))\
        .single()\
        .execute()
        
    if not document.data:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Get folder to check location access
    folder = db.table('folders')\
        .select("*")\
        .eq('id', document.data['folder_id'])\
        .single()\
        .execute()
        
    if not folder.data:
        raise HTTPException(status_code=404, detail="Folder not found")

    # Check if user has access to location
    location_access = db.table('user_locations')\
        .select("*")\
        .eq('user_id', str(current_user["id"]))\
        .eq('location_id', str(folder.data["location_id"]))\
        .execute()
        
    if not location_access.data:
        raise HTTPException(status_code=403, detail="No access to this location")
    
    # Check if user is creator or has admin/manager role
    if str(document.data['created_by']) != str(current_user['id']) and current_user['role'] not in ['org_admin', 'manager']:
        raise HTTPException(status_code=403, detail="Only document creator, org admins, and managers can delete documents")

    # Delete file from storage
    try:
        file_path = document.data['file_path']
        supabase_client.storage.from_('documents').remove([file_path])
    except Exception as e:
        logger.error(f"Error deleting file from storage: {str(e)}")
        # Continue with deletion even if file removal fails
        pass

    # Delete document from database (this will cascade delete embeddings)
    try:
        db.table('documents')\
            .delete()\
            .eq('id', str(document_id))\
            .execute()
    except APIError as e:
        logger.error(f"Error deleting document: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to delete document")

    return DocumentDeleteResponse(
        message="Document deleted successfully",
        id=document_id,
        file_path=document.data['file_path'],
        folder_id=UUID(document.data['folder_id'])
    )

@router.delete("/folders/{folder_id}", response_model=FolderDeleteResponse)
async def delete_folder(
    folder_id: UUID,
    current_user: Dict = Depends(get_current_user),
    db: Client = Depends(get_db),
    supabase_client: Client = Depends(get_supabase)
):
    """Delete a folder and all its contents (documents and subfolders)"""
    # Get folder details
    folder = db.table('folders')\
        .select("*")\
        .eq('id', str(folder_id))\
        .single()\
        .execute()
        
    if not folder.data:
        raise HTTPException(status_code=404, detail="Folder not found")

    # Check if user has access to location
    location_access = db.table('user_locations')\
        .select("*")\
        .eq('user_id', str(current_user["id"]))\
        .eq('location_id', str(folder.data["location_id"]))\
        .execute()
        
    if not location_access.data:
        raise HTTPException(status_code=403, detail="No access to this location")
    
    # Check if user is creator or has admin/manager role
    if str(folder.data['created_by']) != str(current_user['id']) and current_user['role'] not in ['org_admin', 'manager']:
        raise HTTPException(status_code=403, detail="Only folder creator, org admins, and managers can delete folders")

    # Get all documents in this folder and its subfolders
    documents = db.table('documents')\
        .select("*")\
        .eq('folder_id', str(folder_id))\
        .execute()

    # Delete files from storage
    for doc in documents.data:
        try:
            file_path = doc['file_path']
            supabase_client.storage.from_('documents').remove([file_path])
        except Exception as e:
            logger.error(f"Error deleting file from storage: {str(e)}")
            # Continue with deletion even if file removal fails
            continue

    # Count subfolders (will be deleted by CASCADE)
    subfolders = db.table('folders')\
        .select("id")\
        .eq('parent_folder_id', str(folder_id))\
        .execute()

    # Delete folder from database (this will cascade delete all subfolders and documents)
    try:
        db.table('folders')\
            .delete()\
            .eq('id', str(folder_id))\
            .execute()
    except APIError as e:
        logger.error(f"Error deleting folder: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to delete folder")

    return FolderDeleteResponse(
        message="Folder and its contents deleted successfully",
        id=folder_id,
        location_id=UUID(folder.data['location_id']),
        documents_deleted=len(documents.data),
        subfolders_deleted=len(subfolders.data)
    )
