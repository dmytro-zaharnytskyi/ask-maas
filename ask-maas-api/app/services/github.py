"""
GitHub service for fetching repository files
"""
import base64
from typing import List, Dict, Optional
import httpx
import structlog

from app.services.config import Settings

logger = structlog.get_logger()


class GitHubService:
    """Service for interacting with GitHub API"""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Ask MaaS Bot/1.0"
        }
        
        if settings.GITHUB_TOKEN:
            headers["Authorization"] = f"token {settings.GITHUB_TOKEN}"
        
        self.http_client = httpx.AsyncClient(
            timeout=30.0,
            headers=headers
        )
    
    async def resolve_ref(self, repo: str, ref: Optional[str] = None) -> str:
        """
        Resolve a ref (branch/tag) to a commit SHA
        """
        try:
            if not ref:
                ref = "main"  # Default branch
            
            # Check if it's already a SHA
            if len(ref) == 40 and all(c in '0123456789abcdef' for c in ref.lower()):
                return ref
            
            # Get the ref details
            response = await self.http_client.get(
                f"https://api.github.com/repos/{repo}/git/ref/heads/{ref}"
            )
            
            if response.status_code == 404:
                # Try as a tag
                response = await self.http_client.get(
                    f"https://api.github.com/repos/{repo}/git/ref/tags/{ref}"
                )
            
            if response.status_code == 200:
                data = response.json()
                return data["object"]["sha"]
            
            # Fallback: try to get default branch
            response = await self.http_client.get(
                f"https://api.github.com/repos/{repo}"
            )
            
            if response.status_code == 200:
                default_branch = response.json().get("default_branch", "main")
                
                response = await self.http_client.get(
                    f"https://api.github.com/repos/{repo}/git/ref/heads/{default_branch}"
                )
                
                if response.status_code == 200:
                    return response.json()["object"]["sha"]
            
            logger.error(f"Failed to resolve ref: {ref} for repo: {repo}")
            return ref
            
        except Exception as e:
            logger.error(f"Error resolving ref: {e}")
            return ref or "main"
    
    async def fetch_files(
        self,
        repo: str,
        path: str,
        sha: str
    ) -> List[Dict[str, str]]:
        """
        Fetch files from a GitHub repository
        """
        files = []
        
        try:
            # Get the tree for the commit
            response = await self.http_client.get(
                f"https://api.github.com/repos/{repo}/git/trees/{sha}",
                params={"recursive": "true"}
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to get tree for {repo}@{sha}")
                return []
            
            tree = response.json()
            
            # Filter files based on path
            for item in tree.get("tree", []):
                if item["type"] != "blob":
                    continue
                
                item_path = item["path"]
                
                # Check if path matches
                if path and not item_path.startswith(path):
                    continue
                
                # Check if file is allowed
                if not self._is_allowed_file(item_path):
                    continue
                
                # Fetch file content
                file_content = await self._fetch_file_content(
                    repo, item_path, sha
                )
                
                if file_content:
                    files.append({
                        "path": item_path,
                        "content": file_content,
                        "sha": item["sha"]
                    })
                
                # Limit number of files
                if len(files) >= 10:
                    break
            
            return files
            
        except Exception as e:
            logger.error(f"Error fetching files: {e}")
            return []
    
    async def _fetch_file_content(
        self,
        repo: str,
        file_path: str,
        ref: str
    ) -> Optional[str]:
        """
        Fetch the content of a single file
        """
        try:
            response = await self.http_client.get(
                f"https://api.github.com/repos/{repo}/contents/{file_path}",
                params={"ref": ref}
            )
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            
            # Decode base64 content
            if data.get("encoding") == "base64":
                content = base64.b64decode(data["content"]).decode("utf-8")
                return content
            
            return data.get("content", "")
            
        except Exception as e:
            logger.error(f"Error fetching file content: {e}")
            return None
    
    def _is_allowed_file(self, file_path: str) -> bool:
        """
        Check if a file path is allowed based on settings
        """
        for allowed_path in self.settings.GITHUB_ALLOWED_PATHS:
            if allowed_path.endswith("/"):
                # Directory pattern
                if file_path.startswith(allowed_path):
                    return True
            else:
                # File pattern
                if file_path == allowed_path or file_path.endswith(f"/{allowed_path}"):
                    return True
                # Also check for extensions
                if "." in allowed_path and file_path.endswith(allowed_path):
                    return True
        
        # Check for common documentation and config files
        common_patterns = [
            "README", ".md", ".yaml", ".yml", ".json",
            "Dockerfile", "docker-compose", ".sh", ".py"
        ]
        
        return any(pattern in file_path for pattern in common_patterns)
    
    async def close(self):
        """Clean up resources"""
        await self.http_client.aclose()
