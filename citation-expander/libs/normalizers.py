"""Content normalization utilities for different formats."""

import re
import logging
from typing import Dict, Any, Optional
from urllib.parse import urlparse

import trafilatura
from bs4 import BeautifulSoup
import markdown

from libs.github import GitHubFetcher
from libs.pdf import PDFParser

logger = logging.getLogger(__name__)


def clean_text(text: str) -> str:
    """Clean and normalize text content."""
    if not text:
        return ""
    
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)
    
    # Remove special characters but keep punctuation
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
    
    # Normalize quotes
    text = text.replace('"', '"').replace('"', '"')
    text = text.replace(''', "'").replace(''', "'")
    
    # Remove duplicate spaces
    text = re.sub(r' +', ' ', text)
    
    return text.strip()


def normalize_html(content: bytes, url: str) -> Dict[str, Any]:
    """Normalize HTML content using trafilatura for readability."""
    try:
        # Decode content
        text_content = content.decode('utf-8', errors='ignore')
        
        # Extract main content with trafilatura
        extracted = trafilatura.extract(
            text_content,
            include_comments=False,
            include_tables=True,
            include_links=True,
            deduplicate=True,
            url=url
        )
        
        if not extracted:
            # Fallback to BeautifulSoup
            soup = BeautifulSoup(text_content, 'html.parser')
            
            # Remove script and style elements
            for element in soup(['script', 'style', 'meta', 'link']):
                element.decompose()
            
            # Get title
            title = soup.find('title')
            title_text = title.get_text() if title else None
            
            # Get text
            text = soup.get_text(separator=' ', strip=True)
        else:
            text = extracted
            
            # Try to get title from HTML
            soup = BeautifulSoup(text_content, 'html.parser')
            title = soup.find('title')
            title_text = title.get_text() if title else None
        
        # Clean text
        text = clean_text(text)
        
        return {
            "text": text,
            "title": title_text,
            "content_type": "text/html",
            "source_url": url
        }
    
    except Exception as e:
        logger.error(f"Failed to normalize HTML: {e}")
        return {
            "text": "",
            "title": None,
            "content_type": "text/html",
            "error": str(e)
        }


def normalize_markdown(content: bytes, url: str) -> Dict[str, Any]:
    """Normalize Markdown content to plain text."""
    try:
        # Decode content
        text_content = content.decode('utf-8', errors='ignore')
        
        # Extract title from first H1
        title = None
        lines = text_content.split('\n')
        for line in lines[:10]:  # Check first 10 lines
            if line.startswith('# '):
                title = line[2:].strip()
                break
        
        # Convert markdown to HTML then to text
        html = markdown.markdown(
            text_content,
            extensions=['extra', 'codehilite', 'tables']
        )
        
        # Parse HTML to get clean text
        soup = BeautifulSoup(html, 'html.parser')
        text = soup.get_text(separator=' ', strip=True)
        
        # Clean text
        text = clean_text(text)
        
        return {
            "text": text,
            "title": title,
            "content_type": "text/markdown",
            "source_url": url
        }
    
    except Exception as e:
        logger.error(f"Failed to normalize Markdown: {e}")
        return {
            "text": "",
            "title": None,
            "content_type": "text/markdown",
            "error": str(e)
        }


def normalize_text(content: bytes, url: str) -> Dict[str, Any]:
    """Normalize plain text content."""
    try:
        # Decode content
        text = content.decode('utf-8', errors='ignore')
        
        # Clean text
        text = clean_text(text)
        
        # Try to extract title from first line
        lines = text.split('\n')
        title = lines[0][:100] if lines else None
        
        return {
            "text": text,
            "title": title,
            "content_type": "text/plain",
            "source_url": url
        }
    
    except Exception as e:
        logger.error(f"Failed to normalize text: {e}")
        return {
            "text": "",
            "title": None,
            "content_type": "text/plain",
            "error": str(e)
        }


def normalize_pdf(content: bytes, url: str) -> Dict[str, Any]:
    """Normalize PDF content using PyMuPDF."""
    try:
        parser = PDFParser()
        result = parser.parse(content)
        
        return {
            "text": clean_text(result["text"]),
            "title": result.get("title"),
            "content_type": "application/pdf",
            "source_url": url,
            "metadata": result.get("metadata", {})
        }
    
    except Exception as e:
        logger.error(f"Failed to normalize PDF: {e}")
        return {
            "text": "",
            "title": None,
            "content_type": "application/pdf",
            "error": str(e)
        }


def normalize_github(content: bytes, url: str) -> Dict[str, Any]:
    """Normalize GitHub repository content."""
    try:
        from libs.links import extract_github_repo_info
        
        repo_info = extract_github_repo_info(url)
        if not repo_info:
            # Fallback to HTML normalization
            return normalize_html(content, url)
        
        fetcher = GitHubFetcher()
        result = fetcher.fetch_repo_docs(
            repo_info["owner"],
            repo_info["repo"],
            repo_info.get("path", "")
        )
        
        return {
            "text": clean_text(result["text"]),
            "title": result.get("title"),
            "content_type": "text/markdown",  # GitHub docs are usually markdown
            "source_url": url,
            "metadata": {
                "repo": f"{repo_info['owner']}/{repo_info['repo']}",
                "files": result.get("files", [])
            }
        }
    
    except Exception as e:
        logger.error(f"Failed to normalize GitHub content: {e}")
        # Fallback to HTML normalization
        return normalize_html(content, url)


def normalize_content(content: bytes, content_type: str, url: str) -> Dict[str, Any]:
    """Main function to normalize content based on type and URL."""
    if not content:
        return {
            "text": "",
            "title": None,
            "content_type": content_type,
            "source_url": url
        }
    
    # Check if it's a GitHub URL
    if "github.com" in url:
        return normalize_github(content, url)
    
    # Normalize based on content type
    content_type_lower = content_type.lower()
    
    if "html" in content_type_lower or "xml" in content_type_lower:
        return normalize_html(content, url)
    elif "pdf" in content_type_lower:
        return normalize_pdf(content, url)
    elif "markdown" in content_type_lower or url.endswith(".md"):
        return normalize_markdown(content, url)
    elif "text" in content_type_lower:
        return normalize_text(content, url)
    else:
        # Default to text normalization
        return normalize_text(content, url)
