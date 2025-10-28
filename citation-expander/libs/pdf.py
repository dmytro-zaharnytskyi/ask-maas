"""PDF content parser using PyMuPDF."""

import io
import logging
from typing import Dict, Any

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    logging.warning("PyMuPDF not available, PDF parsing will be limited")

logger = logging.getLogger(__name__)


class PDFParser:
    """Parse PDF documents to extract text content."""
    
    def __init__(self):
        if not PYMUPDF_AVAILABLE:
            raise ImportError("PyMuPDF is required for PDF parsing. Install with: pip install PyMuPDF")
    
    def parse(self, content: bytes) -> Dict[str, Any]:
        """Parse PDF content and extract text."""
        try:
            # Create PDF document from bytes
            pdf_file = io.BytesIO(content)
            doc = fitz.open(stream=pdf_file, filetype="pdf")
            
            # Extract metadata
            metadata = doc.metadata
            title = metadata.get("title", None)
            author = metadata.get("author", None)
            
            # Extract text from all pages
            text_pages = []
            for page_num in range(min(len(doc), 50)):  # Limit to first 50 pages
                page = doc[page_num]
                text = page.get_text()
                if text.strip():
                    text_pages.append(text)
            
            doc.close()
            
            # Combine text
            full_text = "\n\n".join(text_pages)
            
            return {
                "text": full_text,
                "title": title,
                "metadata": {
                    "author": author,
                    "pages": len(doc),
                    "extracted_pages": len(text_pages)
                }
            }
        
        except Exception as e:
            logger.error(f"Failed to parse PDF: {e}")
            return {
                "text": "",
                "title": None,
                "error": str(e)
            }


class SimplePDFParser:
    """Simple fallback PDF parser without PyMuPDF."""
    
    def parse(self, content: bytes) -> Dict[str, Any]:
        """Basic PDF text extraction (very limited)."""
        try:
            # Convert bytes to string and look for text between stream markers
            text = content.decode("latin-1", errors="ignore")
            
            # Extract basic text (this is very rudimentary)
            extracted = []
            lines = text.split('\n')
            
            in_text = False
            for line in lines:
                if "stream" in line:
                    in_text = True
                    continue
                elif "endstream" in line:
                    in_text = False
                    continue
                
                if in_text and line.strip():
                    # Try to filter out binary data
                    if not any(ord(c) < 32 or ord(c) > 126 for c in line[:10]):
                        extracted.append(line)
            
            return {
                "text": "\n".join(extracted),
                "title": None,
                "metadata": {
                    "parser": "simple",
                    "warning": "Limited extraction without PyMuPDF"
                }
            }
        
        except Exception as e:
            logger.error(f"Failed to parse PDF with simple parser: {e}")
            return {
                "text": "",
                "title": None,
                "error": str(e)
            }
