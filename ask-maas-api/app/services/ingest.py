"""
Ingest service for processing articles and building indexes
"""
import hashlib
import re
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
import markdown
import tiktoken
import numpy as np
import faiss
import httpx
import structlog

from app.services.config import Settings
# from app.services.vectordb import VectorDBService  # Disabled for now

logger = structlog.get_logger()


class IngestService:
    """Service for document ingestion and indexing"""
    
    def __init__(self, cache_service, settings: Settings):
        self.cache_service = cache_service
        self.settings = settings
        self.http_client = httpx.AsyncClient(timeout=30.0)
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
        # self.vectordb = VectorDBService(url=settings.QDRANT_URL)  # Disabled for now
    
    async def fetch_page(self, page_url: str) -> Optional[Dict]:
        """
        Fetch page content from URL - optimized for Red Hat Developer
        """
        try:
            # Use a more comprehensive user agent to avoid 403 errors
            # Convert external URLs to internal service URLs for cluster access
            fetch_url = page_url
            if "ask-maas-frontend.apps." in page_url:
                # Replace external route with internal service
                # This dynamically handles any cluster domain
                import re
                pattern = r'https://ask-maas-frontend\.apps\.[^/]+'
                internal_url = "http://ghost-article-site-service.ask-maas-frontend.svc.cluster.local:3000"
                fetch_url = re.sub(pattern, internal_url, page_url)
                logger.info(f"Using internal URL for fetch: {fetch_url}")
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
                "Cache-Control": "max-age=0",
            }
            
            response = await self.http_client.get(fetch_url, headers=headers)
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract title - try multiple strategies
            title = ""
            # Try meta og:title first (common in Red Hat Developer)
            og_title = soup.find("meta", property="og:title")
            if og_title:
                title = og_title.get("content", "")
            else:
                # Try article title
                article_title = soup.find("h1", class_=["article-title", "page-title", "rhd-c-article__title"])
                if article_title:
                    title = article_title.get_text().strip()
                else:
                    # Fall back to regular title tag
                    title_tag = soup.find("title")
                    if title_tag:
                        title = title_tag.text.strip()
                        # Remove site name from title if present
                        title = title.split(" | ")[0].strip()
            
            # Extract main content
            content = self._extract_content(soup)
            
            # Convert to markdown for better structure
            content = self._html_to_markdown(content)
            
            # Extract metadata
            metadata = {}
            # Try to get author
            author_meta = soup.find("meta", {"name": "author"})
            if author_meta:
                metadata["author"] = author_meta.get("content", "")
            
            # Try to get publication date
            date_meta = soup.find("meta", property="article:published_time")
            if date_meta:
                metadata["published"] = date_meta.get("content", "")
            
            return {
                "url": page_url,
                "title": title,
                "content": content,
                "etag": response.headers.get("etag", hashlib.md5(response.text.encode()).hexdigest()),
                "html": response.text,
                "metadata": metadata
            }
            
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching page: {e.response.status_code}", url=page_url)
            return None
        except Exception as e:
            logger.error("Failed to fetch page", url=page_url, error=str(e))
            return None
    
    async def get_page_etag(self, page_url: str) -> str:
        """
        Get ETag for a page without fetching full content
        """
        try:
            response = await self.http_client.head(page_url)
            return response.headers.get("etag", "")
        except Exception:
            return ""
    
    async def process_page(self, page_url: str, page_content: Dict) -> List[Dict]:
        """
        Process page content into chunks
        """
        content = page_content.get("content", "")
        title = page_content.get("title", "")
        
        # Convert HTML to markdown for better structure
        if "<" in content and ">" in content:
            content = self._html_to_markdown(content)
        
        # Extract sections
        sections = self._extract_sections(content)
        
        # Chunk sections
        chunks = []
        for section in sections:
            section_chunks = self._chunk_text(
                section["text"],
                section["headings"],
                page_url,
                title
            )
            chunks.extend(section_chunks)
        
        return chunks
    
    def _extract_content(self, soup: BeautifulSoup) -> str:
        """
        Extract main content from HTML - optimized for Red Hat Developer articles
        """
        # Remove script and style elements
        for script in soup(["script", "style", "noscript"]):
            script.decompose()
        
        # Also remove navigation, header, footer elements
        for elem in soup(["nav", "header", "footer"]):
            elem.decompose()
        
        # Remove elements with specific classes common in Red Hat Developer
        for elem in soup.find_all(class_=["site-header", "site-footer", "sidebar", 
                                         "navigation", "breadcrumb", "pf-c-nav"]):
            elem.decompose()
        
        # Look for main content areas - Red Hat Developer specific selectors first
        main_content = (
            soup.find(class_="rhd-c-article") or  # Red Hat Developer article class
            soup.find(class_="article-content") or
            soup.find(class_="pf-c-content") or   # PatternFly content class
            soup.find(class_="main-content") or
            soup.find("main") or
            soup.find("article") or
            soup.find(class_="content") or
            soup.find(id="content") or
            soup.find(role="main") or
            soup.find("body")
        )
        
        if main_content:
            # Extract text with better formatting
            text = main_content.get_text(separator="\n", strip=True)
            # Remove excessive blank lines
            text = "\n".join(line for line in text.split("\n") if line.strip())
            return text
        
        return soup.get_text(separator="\n", strip=True)
    
    def _html_to_markdown(self, html_content: str) -> str:
        """
        Convert HTML to markdown - enhanced for Red Hat Developer articles
        """
        try:
            if "<" not in html_content:
                # Already plain text
                return html_content
                
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Convert headers
            for i in range(1, 7):
                for header in soup.find_all(f"h{i}"):
                    header.string = f"\n{'#' * i} {header.get_text().strip()}\n"
            
            # Convert code blocks with language detection
            for pre in soup.find_all("pre"):
                code = pre.find("code")
                if code:
                    # Try to detect language from class
                    lang = ""
                    if code.get("class"):
                        classes = code.get("class")
                        for cls in classes:
                            if cls.startswith("language-"):
                                lang = cls.replace("language-", "")
                                break
                    
                    code_text = code.get_text().strip()
                    pre.string = f"\n```{lang}\n{code_text}\n```\n"
            
            # Convert inline code
            for code in soup.find_all("code"):
                if code.parent.name != "pre":
                    code.string = f"`{code.get_text().strip()}`"
            
            # Convert lists
            for ul in soup.find_all("ul"):
                items = ul.find_all("li")
                list_text = "\n".join([f"- {item.get_text().strip()}" for item in items])
                ul.string = f"\n{list_text}\n"
            
            for ol in soup.find_all("ol"):
                items = ol.find_all("li")
                list_text = "\n".join([f"{i+1}. {item.get_text().strip()}" 
                                       for i, item in enumerate(items)])
                ol.string = f"\n{list_text}\n"
            
            # Convert links
            for link in soup.find_all("a"):
                href = link.get("href", "")
                text = link.get_text().strip()
                if href and text:
                    link.string = f"[{text}]({href})"
            
            # Convert paragraphs
            for p in soup.find_all("p"):
                p.string = f"\n{p.get_text().strip()}\n"
            
            result = soup.get_text(separator="")
            # Clean up excessive newlines
            result = re.sub(r'\n{3,}', '\n\n', result)
            return result.strip()
            
        except Exception as e:
            logger.warning(f"Error converting HTML to markdown: {e}")
            return html_content
    
    def _extract_sections(self, content: str) -> List[Dict]:
        """
        Extract sections with their headings
        """
        sections = []
        current_headings = []
        current_text = []
        
        lines = content.split("\n")
        
        for line in lines:
            # Check if it's a heading
            heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
            
            if heading_match:
                # Save previous section if exists
                if current_text:
                    sections.append({
                        "headings": current_headings.copy(),
                        "text": "\n".join(current_text).strip()
                    })
                
                # Update heading hierarchy
                level = len(heading_match.group(1))
                heading_text = heading_match.group(2)
                
                # Update current headings based on level
                current_headings = current_headings[:level-1]
                current_headings.append(heading_text)
                
                current_text = []
            else:
                current_text.append(line)
        
        # Add last section
        if current_text:
            sections.append({
                "headings": current_headings.copy(),
                "text": "\n".join(current_text).strip()
            })
        
        return sections if sections else [{"headings": [], "text": content}]
    
    def _chunk_text(
        self,
        text: str,
        headings: List[str],
        page_url: str,
        title: str
    ) -> List[Dict]:
        """
        Chunk text into smaller pieces
        """
        chunks = []
        
        # Tokenize text
        tokens = self.tokenizer.encode(text)
        
        # Calculate chunk parameters
        chunk_size = self.settings.CHUNK_SIZE
        overlap = self.settings.CHUNK_OVERLAP
        
        # Create chunks with overlap
        start = 0
        chunk_id = 0
        
        while start < len(tokens):
            end = min(start + chunk_size, len(tokens))
            chunk_tokens = tokens[start:end]
            
            # Decode chunk
            chunk_text = self.tokenizer.decode(chunk_tokens)
            
            # Create anchor for this chunk
            anchor = f"#chunk-{chunk_id}"
            if headings:
                anchor = f"#{'-'.join(headings).lower().replace(' ', '-')}"
            
            chunks.append({
                "id": f"{hashlib.md5(page_url.encode()).hexdigest()}-{chunk_id}",
                "text": chunk_text,
                "headings": headings,
                "url": f"{page_url}{anchor}",
                "title": title,
                "source": "article",
                "metadata": {
                    "chunk_size": len(chunk_tokens),
                    "position": chunk_id
                }
            })
            
            chunk_id += 1
            start = end - overlap if end < len(tokens) else end
        
        return chunks
    
    async def generate_embeddings(self, chunks: List[Dict]) -> np.ndarray:
        """
        Generate embeddings for chunks - optimized for batch processing
        """
        embeddings = []
        batch_size = 10  # Process in batches for better performance
        
        # Process chunks in batches
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i+batch_size]
            batch_texts = [chunk["text"] for chunk in batch]
            
            try:
                # Send batch request
                response = await self.http_client.post(
                    f"{self.settings.TEI_EMBEDDINGS_URL}/embed",
                    json={"inputs": batch_texts},
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if result and len(result) == len(batch_texts):
                        embeddings.extend(result)
                    else:
                        # Fallback for this batch
                        embeddings.extend([[0.0] * 768 for _ in batch])
                        logger.warning(f"Embedding batch size mismatch: expected {len(batch_texts)}, got {len(result) if result else 0}")
                else:
                    embeddings.extend([[0.0] * 768 for _ in batch])
                    logger.error(f"Failed to generate embeddings batch: HTTP {response.status_code}")
                    
            except Exception as e:
                logger.error(f"Failed to generate embedding batch: {str(e)}")
                embeddings.extend([[0.0] * 768 for _ in batch])
        
        # Store embeddings in chunks for later retrieval
        for chunk, embedding in zip(chunks, embeddings):
            chunk["embedding"] = embedding
        
        return np.array(embeddings, dtype=np.float32)
    
    async def build_index(
        self,
        chunks: List[Dict],
        embeddings: np.ndarray
    ) -> faiss.Index:
        """
        Build FAISS index from embeddings
        """
        # Create FAISS index
        dimension = embeddings.shape[1]
        index = faiss.IndexFlatL2(dimension)
        
        # Add embeddings to index
        index.add(embeddings)
        
        return index
    
    async def extract_github_links(self, page_content: Dict) -> List[str]:
        """
        Extract GitHub links from page content
        """
        links = []
        pattern = r'https://github\.com/[^\s\'"<>]+'
        
        content = page_content.get("html", "") or page_content.get("content", "")
        matches = re.findall(pattern, content)
        
        # Filter for allowed paths
        for link in matches:
            if any(allowed in link for allowed in self.settings.GITHUB_ALLOWED_PATHS):
                links.append(link)
        
        return list(set(links))  # Remove duplicates
    
    async def process_github_file(
        self,
        content: str,
        file_path: str,
        repo: str,
        sha: str
    ) -> List[Dict]:
        """
        Process GitHub file into chunks
        """
        chunks = self._chunk_text(
            text=content,
            headings=[repo, file_path],
            page_url=f"https://github.com/{repo}/blob/{sha}/{file_path}",
            title=f"{repo}/{file_path}"
        )
        
        # Mark as GitHub source
        for chunk in chunks:
            chunk["source"] = "github"
        
        return chunks
    
    async def add_to_page_index(
        self,
        page_url: str,
        new_chunks: List[Dict],
        new_embeddings: np.ndarray
    ):
        """
        Add new chunks to existing page index
        """
        # Get existing index
        page_index = await self.cache_service.get_page_index(page_url)
        
        if page_index:
            # Get existing data
            existing_chunks = page_index.get("chunks", [])
            existing_index = page_index.get("index")
            
            # Combine chunks
            all_chunks = existing_chunks + new_chunks
            
            # Rebuild index with all embeddings
            if existing_index:
                # Extract existing embeddings
                existing_embeddings = np.zeros(
                    (len(existing_chunks), new_embeddings.shape[1]),
                    dtype=np.float32
                )
                for i in range(len(existing_chunks)):
                    existing_index.reconstruct(i, existing_embeddings[i:i+1])
                
                # Combine embeddings
                all_embeddings = np.vstack([existing_embeddings, new_embeddings])
            else:
                all_embeddings = new_embeddings
            
            # Build new index
            new_index = await self.build_index(all_chunks, all_embeddings)
            
            # Update cache
            await self.cache_service.store_page_index(
                page_url=page_url,
                etag=page_index.get("etag", ""),
                index=new_index,
                chunks=all_chunks,
                metadata=page_index.get("metadata", {})
            )
    
    async def close(self):
        """Clean up resources"""
        await self.http_client.aclose()
