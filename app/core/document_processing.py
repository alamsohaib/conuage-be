from typing import List, Dict, Tuple, Optional
import pdfplumber
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
logger = logging.getLogger(__name__)

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
    """Extract actual embedded images from a PDF page using pdfplumber."""
    try:
        extracted_images = []
        image_number = 1
        
        # Get page bounds for size comparison
        page_width = page.width
        page_height = page.height
        
        # Extract images from the page
        for image in page.images:
            try:
                # Skip if image is too large (likely a background or full page)
                if image['width'] > page_width * 0.9 or image['height'] > page_height * 0.9:
                    logger.debug(f"Skipping large image (likely full page or background)")
                    continue
                
                # Get image bytes and format info
                img_bytes = image['stream'].get_data()
                img_format = image.get('format', '').lower()
                
                # Try to detect format from stream if not in metadata
                if not img_format:
                    if img_bytes[:2] == b'\xFF\xD8':
                        img_format = 'jpeg'
                    elif img_bytes[:8] == b'\x89PNG\r\n\x1a\n':
                        img_format = 'png'
                    elif img_bytes[:2] == b'BM':
                        img_format = 'bmp'
                    elif img_bytes[:4] == b'%PDF':
                        continue  # Skip embedded PDFs
                    elif img_bytes[:4] == b'GIF8':
                        img_format = 'gif'
                
                # Create BytesIO with image data
                bio = BytesIO(img_bytes)
                
                # Try different approaches to open the image
                try:
                    img = Image.open(bio)
                except:
                    # If direct open fails, try forcing the format
                    if img_format:
                        bio.seek(0)
                        img = Image.open(bio, formats=[img_format])
                    else:
                        # Try common formats
                        for fmt in ['jpeg', 'png', 'tiff', 'bmp', 'gif']:
                            try:
                                bio.seek(0)
                                img = Image.open(bio, formats=[fmt])
                                break
                            except:
                                continue
                        else:
                            logger.debug("Could not identify image format")
                            continue
                
                # Convert to RGB if necessary
                if img.mode not in ('RGB', 'RGBA'):
                    img = img.convert('RGB')
                
                # Extract text using OCR
                ocr_text = pytesseract.image_to_string(img)
                
                # Convert image to base64
                output_bio = BytesIO()
                img.save(output_bio, format='JPEG', quality=95)
                image_data = base64.b64encode(output_bio.getvalue()).decode()
                
                # Check if image is significant:
                # 1. Has OCR text, or
                # 2. Is between 5% and 90% of page size
                min_size = min(page_width, page_height) * 0.05
                is_significant = (
                    ocr_text.strip() or 
                    (min_size < image['width'] < page_width * 0.9 and 
                     min_size < image['height'] < page_height * 0.9)
                )
                
                if is_significant:
                    extracted_images.append({
                        'image_number': image_number,
                        'image_data': image_data,
                        'ocr_text': ocr_text
                    })
                    image_number += 1
            
            except Exception as img_error:
                logger.debug(f"Could not process embedded image: {str(img_error)}")
                continue
        
        return extracted_images
    except Exception as e:
        logger.error(f"Error extracting images: {str(e)}")
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
