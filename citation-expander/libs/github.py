"""GitHub repository content fetcher."""

import os
import re
import base64
import logging
from typing import Dict, Any, List, Optional

import requests

logger = logging.getLogger(__name__)

# GitHub API configuration
GITHUB_API_URL = "https://api.github.com"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")  # Optional, for rate limit


class GitHubFetcher:
    """Fetch and process GitHub repository documentation."""
    
    def __init__(self, token: Optional[str] = GITHUB_TOKEN):
        self.token = token
        self.session = requests.Session()
        
        if token:
            self.session.headers.update({
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json"
            })
        else:
            self.session.headers.update({
                "Accept": "application/vnd.github.v3+json"
            })
    
    def fetch_repo_docs(
        self,
        owner: str,
        repo: str,
        path: str = ""
    ) -> Dict[str, Any]:
        """Fetch README and documentation from GitHub repository."""
        docs = []
        title = f"{owner}/{repo}"
        
        try:
            # Fetch repository info
            repo_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}"
            repo_response = self.session.get(repo_url, timeout=10)
            
            if repo_response.status_code == 200:
                repo_data = repo_response.json()
                title = repo_data.get("name", title)
                description = repo_data.get("description", "")
                if description:
                    docs.append(f"# {title}\n\n{description}\n\n")
            
            # If specific path provided, fetch that file
            if path:
                file_content = self._fetch_file(owner, repo, path)
                if file_content:
                    docs.append(file_content)
            else:
                # Fetch README
                readme_content = self._fetch_readme(owner, repo)
                if readme_content:
                    docs.append(readme_content)
                
                # Fetch docs directory
                docs_content = self._fetch_docs_directory(owner, repo)
                docs.extend(docs_content)
            
            # Combine all documentation
            combined_text = "\n\n---\n\n".join(docs) if docs else ""
            
            return {
                "text": combined_text,
                "title": title,
                "files": len(docs),
                "source": f"github.com/{owner}/{repo}"
            }
        
        except Exception as e:
            logger.error(f"Failed to fetch GitHub docs for {owner}/{repo}: {e}")
            return {
                "text": "",
                "title": title,
                "error": str(e)
            }
    
    def _fetch_readme(self, owner: str, repo: str) -> Optional[str]:
        """Fetch repository README."""
        readme_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/readme"
        
        try:
            response = self.session.get(readme_url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                content = base64.b64decode(data["content"]).decode("utf-8")
                return content
        except Exception as e:
            logger.debug(f"No README found for {owner}/{repo}: {e}")
        
        return None
    
    def _fetch_file(self, owner: str, repo: str, path: str) -> Optional[str]:
        """Fetch specific file from repository."""
        file_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/contents/{path}"
        
        try:
            response = self.session.get(file_url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                
                if data.get("type") == "file":
                    content = base64.b64decode(data["content"]).decode("utf-8")
                    return f"# File: {path}\n\n{content}"
        except Exception as e:
            logger.debug(f"Failed to fetch file {path} from {owner}/{repo}: {e}")
        
        return None
    
    def _fetch_docs_directory(self, owner: str, repo: str) -> List[str]:
        """Fetch documentation from docs directory."""
        docs = []
        docs_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/contents/docs"
        
        try:
            response = self.session.get(docs_url, timeout=10)
            if response.status_code == 200:
                files = response.json()
                
                # Filter for markdown and text files
                doc_files = [
                    f for f in files
                    if f.get("type") == "file" and
                    (f["name"].endswith(".md") or f["name"].endswith(".txt"))
                ]
                
                # Fetch up to 5 doc files
                for file_info in doc_files[:5]:
                    try:
                        file_response = self.session.get(file_info["url"], timeout=10)
                        if file_response.status_code == 200:
                            file_data = file_response.json()
                            content = base64.b64decode(file_data["content"]).decode("utf-8")
                            docs.append(f"# {file_info['name']}\n\n{content}")
                    except Exception as e:
                        logger.debug(f"Failed to fetch doc file {file_info['name']}: {e}")
        
        except Exception as e:
            logger.debug(f"No docs directory found for {owner}/{repo}: {e}")
        
        return docs
    
    def close(self):
        """Close session."""
        self.session.close()
