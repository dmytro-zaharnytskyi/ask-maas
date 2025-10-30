"""
Ingest endpoints for processing articles and GitHub resources
"""
import asyncio
import hashlib
import os
import time
from typing import Dict, List, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field, HttpUrl
import structlog

from app.services.ingest import IngestService
from app.services.github import GitHubService
# Cache service removed - using Qdrant only
# from app.services.vectordb import VectorDBService  # Disabled for now

logger = structlog.get_logger()
router = APIRouter(tags=["ingest"])


class PageIngestRequest(BaseModel):
    """Request model for page ingestion"""
    page_url: HttpUrl = Field(..., description="URL of the article to ingest")
    force_refresh: bool = Field(default=False, description="Force re-indexing even if cached")
    include_linked_resources: bool = Field(default=True, description="Also ingest linked GitHub resources")


class PageIngestResponse(BaseModel):
    """Response model for page ingestion"""
    page_url: str
    etag: str
    chunk_count: int
    linked_resources: List[Dict]
    cache_hit: bool
    processing_time: float


class ContentIngestRequest(BaseModel):
    """Request model for direct content ingestion"""
    page_url: str = Field(..., description="URL identifier for the content")
    title: str = Field(..., description="Title of the content")
    content: str = Field(..., description="Content to ingest (markdown, html, or plain text)")
    content_type: str = Field(default="markdown", description="Type of content: markdown, html, or text")
    force_refresh: bool = Field(default=False, description="Force re-indexing even if cached")

class GitHubIngestRequest(BaseModel):
    """Request model for GitHub resource ingestion"""
    repo: str = Field(..., description="Repository (owner/name)")
    path: str = Field(..., description="File or directory path")
    ref: Optional[str] = Field(default=None, description="Git ref (branch/tag/commit)")
    page_url: HttpUrl = Field(..., description="Associated article URL")


class GitHubIngestResponse(BaseModel):
    """Response model for GitHub ingestion"""
    repo: str
    path: str
    sha: str
    files_processed: int
    chunk_count: int
    processing_time: float


@router.post("/ingest/page", response_model=PageIngestResponse)
async def ingest_page(
    request: PageIngestRequest,
    req: Request,
    background_tasks: BackgroundTasks
):
    """
    Ingest an article and optionally its linked resources
    """
    start_time = time.time()
    
    logger.info(
        "Page ingest request",
        page_url=str(request.page_url),
        force_refresh=request.force_refresh
    )
    
    # Get services from app state
    app = req.app
    settings = app.state.settings
    
    # Initialize ingest service (no cache service)
    ingest_service = IngestService(None, settings)
    
    try:
        # Check if page is already cached (unless force refresh)
        page_url = str(request.page_url)
        cache_hit = False
        
        if not request.force_refresh:
            # No caching - always fresh from Qdrant
            existing_index = None
            if False:
                etag = existing_index.get("etag", "")
                chunk_count = existing_index.get("chunk_count", 0)
                
                # Check if the page has been updated
                current_etag = await ingest_service.get_page_etag(page_url)
                
                if etag == current_etag:
                    cache_hit = True
                    logger.info(
                        "Using cached page index",
                        page_url=page_url,
                        etag=etag,
                        chunk_count=chunk_count
                    )
                    
                    return PageIngestResponse(
                        page_url=page_url,
                        etag=etag,
                        chunk_count=chunk_count,
                        linked_resources=[],
                        cache_hit=True,
                        processing_time=time.time() - start_time
                    )
        
        # Fetch and process the page
        logger.info("Fetching page content", page_url=page_url)
        page_content = await ingest_service.fetch_page(page_url)
        
        if not page_content:
            raise HTTPException(status_code=404, detail="Failed to fetch page content")
        
        # Parse and chunk the content
        logger.info("Processing page content", page_url=page_url)
        chunks = await ingest_service.process_page(page_url, page_content)
        
        if not chunks:
            raise HTTPException(status_code=422, detail="No content extracted from page")
        
        # Generate embeddings
        logger.info("Generating embeddings", page_url=page_url, chunk_count=len(chunks))
        embeddings = await ingest_service.generate_embeddings(chunks)
        
        # Build FAISS index
        logger.info("Building FAISS index", page_url=page_url)
        index = await ingest_service.build_index(chunks, embeddings)
        
        # Calculate ETag
        etag = hashlib.md5(page_content.get("content", "").encode()).hexdigest()
        
        # Cache removed - storing directly in Qdrant
        # await cache_service.store_page_index(
        #     page_url=page_url,
        #     etag=etag,
        #     index=index,
        #     chunks=chunks,
        #     metadata={
        #         "chunk_count": len(chunks),
        #         "indexed_at": time.time(),
        #         "title": page_content.get("title", "")
        #     }
        # )
        
        # Vector database disabled for now
        # vectordb = VectorDBService(url=settings.QDRANT_URL)
        # try:
        #     # Store chunks with embeddings in vector DB
        #     await vectordb.index_chunks(
        #         chunks=[{
        #             "text": chunk.get("text", ""),
        #             "embedding": embeddings[i] if i < len(embeddings) else None,
        #             "metadata": chunk.get("metadata", {})
        #         } for i, chunk in enumerate(chunks)],
        #         page_url=page_url,
        #         title=page_content.get("title", ""),
        #         force_refresh=True
        #     )
        #     logger.info("Stored chunks in vector database", page_url=page_url, count=len(chunks))
        # finally:
        #     await vectordb.close()
        
        linked_resources = []
        
        # Process linked GitHub resources if requested
        if request.include_linked_resources:
            logger.info("Processing linked resources", page_url=page_url)
            
            # Extract GitHub links from the page
            github_links = await ingest_service.extract_github_links(page_content)
            
            # Process each link in the background
            for link in github_links:
                try:
                    # Parse GitHub URL
                    parsed = parse_github_url(link)
                    if parsed:
                        # Add to background tasks
                        background_tasks.add_task(
                            process_github_resource,
                            repo=parsed["repo"],
                            path=parsed["path"],
                            ref=parsed["ref"],
                            page_url=page_url,
                            cache_service=cache_service,
                            settings=settings
                        )
                        
                        linked_resources.append({
                            "url": link,
                            "repo": parsed["repo"],
                            "path": parsed["path"],
                            "status": "queued"
                        })
                        
                except Exception as e:
                    logger.error(
                        "Failed to process GitHub link",
                        link=link,
                        error=str(e)
                    )
        
        processing_time = time.time() - start_time
        
        logger.info(
            "Page ingestion completed",
            page_url=page_url,
            chunk_count=len(chunks),
            linked_resources=len(linked_resources),
            processing_time=processing_time
        )
        
        return PageIngestResponse(
            page_url=page_url,
            etag=etag,
            chunk_count=len(chunks),
            linked_resources=linked_resources,
            cache_hit=cache_hit,
            processing_time=processing_time
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Page ingestion failed",
            page_url=str(request.page_url),
            error=str(e),
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")


@router.post("/ingest/content", response_model=PageIngestResponse)
async def ingest_content(
    request: ContentIngestRequest,
    req: Request
):
    """
    Ingest content directly (for local articles in the frontend)
    """
    start_time = time.time()
    
    logger.info(
        "Content ingest request",
        page_url=request.page_url,
        title=request.title,
        content_type=request.content_type,
        content_length=len(request.content),
        force_refresh=request.force_refresh
    )
    
    # Get services from app state
    app = req.app
    settings = app.state.settings
    
    # Initialize ingest service (no cache service)
    ingest_service = IngestService(None, settings)
    
    try:
        # Check if content is already cached (unless force refresh)
        cache_hit = False
        
        if not request.force_refresh:
            existing_index = await cache_service.get_page_index(request.page_url)
            if existing_index:
                etag = existing_index.get("etag", "")
                chunk_count = existing_index.get("chunk_count", 0)
                
                # Calculate current content hash
                current_etag = hashlib.md5(request.content.encode()).hexdigest()
                
                if etag == current_etag:
                    cache_hit = True
                    logger.info(
                        "Using cached content index",
                        page_url=request.page_url,
                        etag=etag,
                        chunk_count=chunk_count
                    )
                    
                    return PageIngestResponse(
                        page_url=request.page_url,
                        etag=etag,
                        chunk_count=chunk_count,
                        linked_resources=[],
                        cache_hit=True,
                        processing_time=time.time() - start_time
                    )
        
        # Process content into smaller chunks for better context management
        logger.info("Processing content into chunks", page_url=request.page_url)
        
        # Split content into manageable chunks (2000 chars with 200 char overlap)
        chunk_size = 2000
        overlap = 200
        chunks = []
        
        content = request.content[:500000]  # Increased limit to 500k chars for larger documents
        
        for i in range(0, len(content), chunk_size - overlap):
            chunk_text = content[i:i + chunk_size]
            if len(chunk_text.strip()) > 100:  # Skip very small chunks
                chunks.append({
                    "id": str(len(chunks)),
                    "text": chunk_text,
                    "url": request.page_url,
                    "title": request.title,
                    "chunk_id": len(chunks),
                    "metadata": {
                        "content_type": request.content_type,
                        "chunk_position": len(chunks),
                        "total_chunks": -1  # Will update after
                    }
                })
        
        # Update total chunks count
        for chunk in chunks:
            chunk["metadata"]["total_chunks"] = len(chunks)
        
        logger.info(f"Created {len(chunks)} chunks", page_url=request.page_url)
        
        # Generate embeddings for each chunk for vector retrieval
        logger.info("Generating embeddings for chunks", page_url=request.page_url)
        
        # Initialize HTTP client for embeddings
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as http_client:
            for chunk in chunks:
                try:
                    # Generate embedding for this chunk
                    response = await http_client.post(
                        f"{settings.TEI_EMBEDDINGS_URL}/embed",
                        json={"inputs": [chunk["text"][:1000]]}  # Limit text length
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        if result and len(result) > 0:
                            chunk["embedding"] = result[0]
                        else:
                            # Use zero vector as fallback
                            chunk["embedding"] = [0.0] * 1024
                    else:
                        logger.warning(f"Failed to generate embedding: {response.status_code}")
                        chunk["embedding"] = [0.0] * 1024
                except Exception as e:
                    logger.error(f"Error generating embedding: {e}")
                    chunk["embedding"] = [0.0] * 1024
        
        index = None  # We don't need FAISS index for vector retrieval
        
        # Calculate ETag
        etag = hashlib.md5(request.content.encode()).hexdigest()
        
        # Cache removed - storing directly in Qdrant
        # await cache_service.store_page_index(
            page_url=request.page_url,
            etag=etag,
            index=index,
            chunks=chunks,
            metadata={
                "chunk_count": len(chunks),
                "indexed_at": time.time(),
                "title": request.title,
                "content_type": request.content_type,
                "simplified": True
            }
        )
        
        # Vector database disabled for now
        # vectordb = VectorDBService(url=settings.QDRANT_URL)
        # try:
        #     # Store chunks with embeddings in vector DB (simplified version without embeddings)
        #     await vectordb.index_chunks(
        #         chunks=[{
        #             "text": chunk.get("text", ""),
        #             "embedding": None,  # Will be generated by the vectordb service
        #             "metadata": chunk.get("metadata", {})
        #         } for chunk in chunks],
        #         page_url=request.page_url,
        #         title=request.title,
        #         force_refresh=True
        #     )
        #     logger.info("Stored chunks in vector database", page_url=request.page_url, count=len(chunks))
        # finally:
        #     await vectordb.close()
        
        # Extract and enqueue links for citation expansion
        try:
            import re
            import httpx
            
            # Extract HTTP/HTTPS links from content
            url_pattern = r'https?://[^\s<>"\'{}|\\^`\[\]]+[^\s<>"\'{}|\\^`\[\].,;:!?)]'
            links = re.findall(url_pattern, request.content)
            
            # Filter out unwanted links (images, css, js, etc.)
            useful_links = [
                link for link in set(links)
                if not any(link.lower().endswith(ext) for ext in ['.jpg', '.png', '.gif', '.css', '.js', '.ico', '.svg', '.woff'])
                and len(link) > 20  # Filter out very short URLs
            ][:20]  # Limit to 20 links per article
            
            if useful_links:
                logger.info(f"Found {len(useful_links)} links to process for citations", page_url=request.page_url)
                
                # Enqueue each link to citation expander
                citation_api_url = os.getenv("CITATION_API_URL", "http://citation-expander.ask-maas.svc.cluster.local:8000")
                
                async with httpx.AsyncClient(timeout=5.0) as client:
                    enqueued = 0
                    for link in useful_links:
                        try:
                            # Enqueue with first chunk as parent
                            parent_chunk_id = chunks[0]["id"] if chunks else "unknown"
                            response = await client.post(
                                f"{citation_api_url}/enqueue",
                                params={
                                    "url": link,
                                    "parent_doc_id": request.page_url,
                                    "parent_chunk_id": parent_chunk_id,
                                    "depth": 0
                                },
                                timeout=2.0
                            )
                            if response.status_code == 200:
                                enqueued += 1
                        except Exception as e:
                            logger.debug(f"Failed to enqueue link {link}: {e}")
                    
                    if enqueued > 0:
                        logger.info(f"Enqueued {enqueued} links for citation processing", page_url=request.page_url)
        except Exception as e:
            logger.warning(f"Link extraction failed: {e}")
        
        processing_time = time.time() - start_time
        
        logger.info(
            "Content ingestion completed",
            page_url=request.page_url,
            chunk_count=len(chunks),
            processing_time=processing_time
        )
        
        return PageIngestResponse(
            page_url=request.page_url,
            etag=etag,
            chunk_count=len(chunks),
            linked_resources=[],
            cache_hit=cache_hit,
            processing_time=processing_time
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Content ingestion failed",
            page_url=request.page_url,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"Content ingestion failed: {str(e)}")


@router.post("/ingest/github", response_model=GitHubIngestResponse)
async def ingest_github(
    request: GitHubIngestRequest,
    req: Request
):
    """
    Ingest GitHub resources (files from a repository)
    """
    start_time = time.time()
    
    logger.info(
        "GitHub ingest request",
        repo=request.repo,
        path=request.path,
        ref=request.ref,
        page_url=str(request.page_url)
    )
    
    # Get services from app state
    app = req.app
    cache_service: CacheService = app.state.cache_service
    settings = app.state.settings
    
    # Initialize services
    github_service = GitHubService(settings)
    ingest_service = IngestService(cache_service, settings)
    
    try:
        # Resolve ref to commit SHA for stable citations
        sha = await github_service.resolve_ref(request.repo, request.ref)
        
        logger.info(
            "Resolved Git ref to SHA",
            repo=request.repo,
            ref=request.ref,
            sha=sha
        )
        
        # Fetch file(s) from GitHub
        files = await github_service.fetch_files(
            repo=request.repo,
            path=request.path,
            sha=sha
        )
        
        if not files:
            raise HTTPException(status_code=404, detail="No files found at specified path")
        
        all_chunks = []
        
        # Process each file
        for file_info in files:
            try:
                # Check if file is allowed
                if not is_allowed_file(file_info["path"], settings.GITHUB_ALLOWED_PATHS):
                    logger.debug(
                        "Skipping disallowed file",
                        path=file_info["path"]
                    )
                    continue
                
                # Process file content
                chunks = await ingest_service.process_github_file(
                    content=file_info["content"],
                    file_path=file_info["path"],
                    repo=request.repo,
                    sha=sha
                )
                
                all_chunks.extend(chunks)
                
            except Exception as e:
                logger.error(
                    "Failed to process GitHub file",
                    path=file_info["path"],
                    error=str(e)
                )
        
        if not all_chunks:
            raise HTTPException(status_code=422, detail="No content extracted from GitHub files")
        
        # Generate embeddings for all chunks
        logger.info("Generating embeddings for GitHub content", chunk_count=len(all_chunks))
        embeddings = await ingest_service.generate_embeddings(all_chunks)
        
        # Add to existing page index
        page_url = str(request.page_url)
        await ingest_service.add_to_page_index(
            page_url=page_url,
            new_chunks=all_chunks,
            new_embeddings=embeddings
        )
        
        processing_time = time.time() - start_time
        
        logger.info(
            "GitHub ingestion completed",
            repo=request.repo,
            path=request.path,
            sha=sha,
            files_processed=len(files),
            chunk_count=len(all_chunks),
            processing_time=processing_time
        )
        
        return GitHubIngestResponse(
            repo=request.repo,
            path=request.path,
            sha=sha,
            files_processed=len(files),
            chunk_count=len(all_chunks),
            processing_time=processing_time
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "GitHub ingestion failed",
            repo=request.repo,
            path=request.path,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"GitHub ingestion failed: {str(e)}")


def parse_github_url(url: str) -> Optional[Dict[str, str]]:
    """
    Parse GitHub URL to extract repo, path, and ref
    Example: https://github.com/owner/repo/blob/main/path/to/file.md
    """
    try:
        parsed = urlparse(url)
        if parsed.netloc != "github.com":
            return None
        
        parts = parsed.path.strip("/").split("/")
        
        if len(parts) < 4:
            return None
        
        owner = parts[0]
        repo_name = parts[1]
        action = parts[2]  # blob, tree, raw, etc.
        ref = parts[3]
        path = "/".join(parts[4:]) if len(parts) > 4 else ""
        
        return {
            "repo": f"{owner}/{repo_name}",
            "ref": ref,
            "path": path,
            "action": action
        }
        
    except Exception as e:
        logger.error(f"Failed to parse GitHub URL: {url}", error=str(e))
        return None


def is_allowed_file(file_path: str, allowed_paths: List[str]) -> bool:
    """
    Check if a file path matches allowed patterns
    """
    for pattern in allowed_paths:
        if pattern.endswith("/"):
            # Directory pattern
            if file_path.startswith(pattern):
                return True
        else:
            # File pattern
            if file_path == pattern or file_path.endswith(f"/{pattern}"):
                return True
    return False


async def process_github_resource(
    repo: str,
    path: str,
    ref: Optional[str],
    page_url: str,
    cache_service: CacheService,
    settings
):
    """
    Background task to process GitHub resources
    """
    try:
        logger.info(
            "Processing GitHub resource in background",
            repo=repo,
            path=path,
            ref=ref,
            page_url=page_url
        )
        
        github_service = GitHubService(settings)
        ingest_service = IngestService(cache_service, settings)
        
        # Process the GitHub resource
        sha = await github_service.resolve_ref(repo, ref)
        files = await github_service.fetch_files(repo, path, sha)
        
        all_chunks = []
        for file_info in files:
            if is_allowed_file(file_info["path"], settings.GITHUB_ALLOWED_PATHS):
                chunks = await ingest_service.process_github_file(
                    content=file_info["content"],
                    file_path=file_info["path"],
                    repo=repo,
                    sha=sha
                )
                all_chunks.extend(chunks)
        
        if all_chunks:
            embeddings = await ingest_service.generate_embeddings(all_chunks)
            await ingest_service.add_to_page_index(page_url, all_chunks, embeddings)
        
        logger.info(
            "Background GitHub processing completed",
            repo=repo,
            path=path,
            chunk_count=len(all_chunks)
        )
        
    except Exception as e:
        logger.error(
            "Background GitHub processing failed",
            repo=repo,
            path=path,
            error=str(e),
            exc_info=True
        )
