from typing import List, Dict, Tuple, Optional
import pdfplumber  # For table extraction
import fitz  # PyMuPDF for image extraction
import pytesseract
from PIL import Image
import base64
from io import BytesIO
import os
from uuid import UUID
from app.core.config import settings
from app.core.embeddings import get_embeddings
from app.core.clients import get_openai_client
from app.core.ai_models import ai_models, OperationType
import logging

# Configure Tesseract path
pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_PATH

# Set up logging
logger = logging.getLogger('app.core.document_processing')

def extract_text(page) -> str:
    """Extract text from a PDF page using pdfplumber."""
    try:
        text = page.extract_text()
        return text if text else ""
    except Exception as e:
        print(f"Error extracting text: {str(e)}")
        return ""

def extract_tables_from_pdf(page) -> List[Dict]:
    """Extract tables from a PDF page using pdfplumber."""
    try:
        tables = page.extract_tables()
        
        extracted_tables = []
        for idx, table in enumerate(tables, start=1):
            # Convert table to structured format
            table_data = []
            for row in table:
                # Clean None values and strip whitespace
                cleaned_row = [str(cell).strip() if cell is not None else "" for cell in row]
                table_data.append(cleaned_row)
            
            # Generate HTML representation
            html_content = _table_to_html(table_data)
            
            extracted_tables.append({
                'table_number': idx,
                'content': table_data,
                'html_content': html_content
            })
        
        return extracted_tables
    except Exception as e:
        logger.error(f"Error extracting tables: {str(e)}")
        return []

def _table_to_html(table_data: List[List[str]]) -> str:
    """Convert table data to HTML format."""
    html = ['<table border="1">']
    
    # Assume first row is header
    html.append('<thead><tr>')
    for header in table_data[0]:
        html.append(f'<th>{header}</th>')
    html.append('</tr></thead>')
    
    # Add remaining rows
    html.append('<tbody>')
    for row in table_data[1:]:
        html.append('<tr>')
        for cell in row:
            html.append(f'<td>{cell}</td>')
        html.append('</tr>')
    html.append('</tbody>')
    
    html.append('</table>')
    return ''.join(html)

def extract_images_from_pdf(page) -> List[Dict]:
    """Extract images from a PDF page using PyMuPDF."""
    try:
        extracted_images = []
        image_number = 1
        
        # Get list of images on the page
        image_list = page.get_images(full=True)
        logger.debug(f"Found {len(image_list)} raw images on page")
        
        for img_idx, img_info in enumerate(image_list, start=1):
            try:
                xref = img_info[0]  # Cross-reference number
                base_image = page.parent.extract_image(xref)
                
                if base_image is None:
                    logger.debug(f"Could not extract image {img_idx} - no data returned")
                    continue
                
                # Get image data and format
                img_bytes = base_image["image"]
                
                # Create PIL Image for processing
                bio = BytesIO(img_bytes)
                try:
                    img = Image.open(bio)
                    
                    # Convert to RGB if necessary
                    if img.mode not in ('RGB', 'RGBA'):
                        img = img.convert('RGB')
                    
                    # Convert to JPEG format and base64 encode
                    output_bio = BytesIO()
                    img.save(output_bio, format='JPEG', quality=95)
                    img_base64 = base64.b64encode(output_bio.getvalue()).decode('utf-8')
                    
                    # Extract text using OCR if enabled
                    ocr_text = ""
                    try:
                        if settings.ENABLE_OCR:
                            ocr_text = pytesseract.image_to_string(img)
                            if ocr_text.strip():
                                logger.debug(f"OCR text found in image {img_idx}")
                    except Exception as ocr_err:
                        logger.warning(f"OCR failed for image {img_idx}: {str(ocr_err)}")
                    
                    # Add to extracted images
                    extracted_images.append({
                        'image_number': image_number,
                        'image_data': img_base64,
                        'ocr_text': ocr_text.strip() if ocr_text else ""
                    })
                    
                    logger.debug(f"Successfully extracted image {img_idx}")
                    image_number += 1
                    
                except Exception as pil_err:
                    logger.error(f"Error processing image {img_idx} with PIL: {str(pil_err)}")
                    continue
                    
            except Exception as img_err:
                logger.error(f"Error extracting image {img_idx}: {str(img_err)}")
                continue
        
        logger.info(f"Successfully extracted {len(extracted_images)} images from page")
        return extracted_images
        
    except Exception as e:
        logger.error(f"Error in image extraction: {str(e)}", exc_info=True)
        return []

async def generate_table_description(table_data: List[List[str]]) -> Tuple[str, int]:
    """Generate a description of a table using OpenAI."""
    try:
        # Convert table data to a string representation
        table_str = "\n".join(["\t".join(row) for row in table_data])
        
        client = get_openai_client()
        model_config = ai_models.get_model('default_chat')
        
        response = await client.chat.completions.create(
            model=model_config.model_id,
            messages=[
                {
                    "role": "user",
                    "content": f"Please describe this table data in natural language, focusing on the key information and relationships:\n\n{table_str}"
                }
            ],
            temperature=model_config.temperature,
            max_tokens=model_config.max_tokens
        )
        
        description = response.choices[0].message.content
        tokens_used = response.usage.total_tokens
        
        return description, tokens_used
        
    except Exception as e:
        logger.error(f"Error generating table description: {str(e)}")  
        return "Table description unavailable", 0

async def generate_image_description(image_data: str, ocr_text: str = None) -> Tuple[str, int]:
    """Generate a description of an image using OpenAI's Vision model."""
    try:
        client = get_openai_client()
        model_config = ai_models.get_model('vision_chat')
        
        # Prepare the message with image and context
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Please describe this image in detail. If there is text in the image, mention it."
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_data}"
                        }
                    }
                ]
            }
        ]
        
        # Add OCR text if available
        if ocr_text and ocr_text.strip():
            messages[0]["content"][0]["text"] += f"\nOCR detected text: {ocr_text}"
        
        # Generate description using Vision model
        response = await client.chat.completions.create(
            model=model_config.model_id,
            messages=messages,
            temperature=model_config.temperature,
            max_tokens=model_config.max_tokens
        )
        
        description = response.choices[0].message.content
        tokens_used = response.usage.total_tokens
        
        return description, tokens_used
        
    except Exception as e:
        logger.error(f"Error generating image description: {str(e)}")
        return "Unable to generate image description due to API limitations. OCR text: " + (ocr_text if ocr_text else ""), 0

async def save_image_to_storage(image_data: str, document_id: UUID, page_number: int, image_number: int, supabase_client) -> str:
    """Save base64 image data to Supabase storage and return the public URL."""
    try:
        # Generate storage path
        storage_path = f"documents/{document_id}/images/page_{page_number}_image_{image_number}.jpg"
        
        # Decode base64 image
        image_bytes = base64.b64decode(image_data)
        
        # Upload to Supabase storage
        result = supabase_client.storage.from_('documents').upload(
            path=storage_path,
            file=image_bytes,
            file_options={"content-type": "image/jpeg"}
        )
        
        # Get public URL
        public_url = supabase_client.storage.from_('documents').get_public_url(storage_path)
        
        logger.info(f"Saved image to Supabase storage: {storage_path}")
        return public_url
        
    except Exception as e:
        logger.error(f"Error saving image to Supabase storage: {str(e)}")
        raise
