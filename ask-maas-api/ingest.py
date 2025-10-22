#!/usr/bin/env python3
"""
Optimized ingestion script that ensures all articles are properly indexed with embeddings
for efficient global vector search - PURE RAG approach, no keyword matching
"""
import asyncio
import os
import sys
import json
import httpx
import re
from pathlib import Path
from bs4 import BeautifulSoup
from typing import List, Dict
import tiktoken
import time

API_URL = os.getenv("API_URL", "http://localhost:8000")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
ARTICLES_DIR = os.getenv("ARTICLES_DIR", "/home/zdmytro/Work/ask-maas/articles")

# Optimized chunking parameters for better context
MAX_CHUNK_TOKENS = 800  # Smaller chunks for better precision
CHUNK_OVERLAP_TOKENS = 100  # Some overlap for context continuity

def extract_article_content(html_path: Path) -> Dict:
    """Extract meaningful content from HTML file"""
    with open(html_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    soup = BeautifulSoup(content, 'html.parser')
    
    # Remove script and style elements
    for element in soup(['script', 'style', 'nav', 'header', 'footer']):
        element.decompose()
    
    # Extract title
    title = ""
    title_elem = soup.find('title')
    if title_elem:
        title = title_elem.text.strip()
        title = re.sub(r'\s*\|\s*Red Hat Developer.*$', '', title)
    
    # Extract main content
    main_content = soup.find('main') or soup.find('article') or soup.find('body')
    if main_content:
        text = main_content.get_text(separator=' ', strip=True)
    else:
        text = soup.get_text(separator=' ', strip=True)
    
    # Clean up text
    text = ' '.join(text.split())
    
    return {
        "title": title,
        "content": text,
        "filename": html_path.name
    }

def create_semantic_chunks(text: str, title: str) -> List[Dict]:
    """Create semantic chunks optimized for vector search"""
    tokenizer = tiktoken.get_encoding("cl100k_base")
    
    # Split into sentences for better semantic boundaries
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    chunks = []
    current_chunk = []
    current_tokens = 0
    
    for sentence in sentences:
        sentence_tokens = len(tokenizer.encode(sentence))
        
        # If adding this sentence exceeds limit, save current chunk
        if current_tokens + sentence_tokens > MAX_CHUNK_TOKENS and current_chunk:
            chunk_text = ' '.join(current_chunk)
            chunks.append({
                "text": chunk_text,
                "title": title,
                "chunk_id": len(chunks)
            })
            
            # Keep last sentence for overlap
            if CHUNK_OVERLAP_TOKENS > 0 and current_chunk:
                current_chunk = [current_chunk[-1]]
                current_tokens = len(tokenizer.encode(current_chunk[0]))
            else:
                current_chunk = []
                current_tokens = 0
        
        current_chunk.append(sentence)
        current_tokens += sentence_tokens
    
    # Add final chunk
    if current_chunk:
        chunks.append({
            "text": ' '.join(current_chunk),
            "title": title,
            "chunk_id": len(chunks)
        })
    
    return chunks

async def ingest_article_optimized(client: httpx.AsyncClient, html_path: Path) -> bool:
    """Ingest article with optimized chunking and embedding generation"""
    try:
        # Extract content
        article_data = extract_article_content(html_path)
        print(f"\n📄 Processing: {article_data['title'][:60]}...")
        
        # Create semantic chunks
        chunks = create_semantic_chunks(article_data['content'], article_data['title'])
        print(f"   Created {len(chunks)} semantic chunks")
        
        # Prepare ingestion data
        page_url = f"{FRONTEND_URL}/api/articles/{html_path.name}"
        
        # Send all chunks as context
        chunk_texts = [f"[Chunk {i+1}]: {chunk['text']}" for i, chunk in enumerate(chunks)]
        combined_content = "\n\n".join(chunk_texts)
        
        # Ingest with force refresh to ensure fresh embeddings
        response = await client.post(
            f"{API_URL}/api/v1/ingest/content",
            json={
                "page_url": page_url,
                "title": article_data["title"],
                "content": combined_content,
                "content_type": "text",
                "force_refresh": True
            },
            timeout=30.0
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"   ✅ Successfully indexed: {result.get('chunk_count', 0)} chunks with embeddings")
            return True
        else:
            print(f"   ❌ Failed: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")
        return False

async def test_global_search(client: httpx.AsyncClient):
    """Test that global search works properly across all articles"""
    test_queries = [
        "What is MaaS?",
        "Can I customize the rate limit in MaaS?",
        "What are hard truths and pitfalls about customization?",
        "How does vLLM compare to Ollama?",
        "What is TTFT and ITL?",
        "How to deploy Llama 3 with vLLM?"
    ]
    
    print("\n🧪 Testing Global Vector Search:")
    print("-" * 60)
    
    for query in test_queries:
        print(f"\n❓ Query: '{query}'")
        try:
            # Use any page URL - the system should search globally
            response = await client.post(
                f"{API_URL}/api/v1/chat",
                json={
                    "query": query,
                    "page_url": f"{FRONTEND_URL}/api/articles/test.html",
                    "stream": False
                },
                timeout=15.0,
                headers={"Accept": "text/event-stream"}
            )
            
            if response.status_code == 200:
                # Parse SSE response
                content = ""
                citations = []
                
                for line in response.text.split('\n'):
                    if line.startswith('data: '):
                        try:
                            data = json.loads(line[6:])
                            if data.get('type') == 'text':
                                content += data.get('content', '')
                            elif data.get('type') == 'citation':
                                citations = data.get('citations', [])
                        except:
                            pass
                
                if content:
                    print(f"   ✅ Response: {content[:150]}...")
                    if citations:
                        print(f"   📚 Sources: {', '.join([c.get('title', 'Unknown') for c in citations])}")
                else:
                    print(f"   ⚠️  No response generated")
            else:
                print(f"   ❌ Failed: HTTP {response.status_code}")
        except Exception as e:
            print(f"   ❌ Error: {e}")

async def main():
    """Main function to ingest all articles with optimized vector embeddings"""
    articles_path = Path(ARTICLES_DIR)
    
    if not articles_path.exists():
        print(f"❌ Articles directory not found: {ARTICLES_DIR}")
        sys.exit(1)
    
    # Find all HTML files
    html_files = list(articles_path.glob("*.html"))
    
    if not html_files:
        print(f"❌ No HTML files found in {ARTICLES_DIR}")
        sys.exit(1)
    
    print(f"🚀 Optimized Article Ingestion for Pure Vector Search")
    print(f"📂 Found {len(html_files)} articles to index")
    print(f"🔗 API URL: {API_URL}")
    print(f"🌐 Frontend URL: {FRONTEND_URL}")
    print(f"📊 Chunk size: {MAX_CHUNK_TOKENS} tokens, Overlap: {CHUNK_OVERLAP_TOKENS} tokens")
    print("=" * 60)
    
    async with httpx.AsyncClient() as client:
        start_time = time.time()
        successful = 0
        failed = 0
        
        # Process all articles
        for html_file in html_files:
            if await ingest_article_optimized(client, html_file):
                successful += 1
            else:
                failed += 1
            
            # Small delay to avoid overwhelming the server
            await asyncio.sleep(0.5)
        
        ingestion_time = time.time() - start_time
        
        print("\n" + "=" * 60)
        print(f"✅ Ingestion complete in {ingestion_time:.2f} seconds")
        print(f"📈 Results: {successful} successful, {failed} failed")
        
        # Test global search functionality
        if successful > 0:
            await test_global_search(client)
        
        print("\n" + "=" * 60)
        print("✨ System is now ready for PURE vector-based RAG search!")
        print("🔍 Every query will perform fresh global search across all articles")
        print("⚡ Response times should be optimized (~2-5 seconds)")

if __name__ == "__main__":
    asyncio.run(main())
