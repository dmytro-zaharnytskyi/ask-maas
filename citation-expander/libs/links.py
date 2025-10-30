"""Link extraction and filtering utilities."""

import os
import re
import logging
from typing import List, Set
from urllib.parse import urlparse, urljoin

import yaml

logger = logging.getLogger(__name__)

# Load allowlist patterns from environment or config
ALLOWLIST_PATTERNS = None


def load_allowlist_patterns() -> List[re.Pattern]:
    """Load URL allowlist patterns from ConfigMap or environment."""
    global ALLOWLIST_PATTERNS
    
    if ALLOWLIST_PATTERNS is not None:
        return ALLOWLIST_PATTERNS
    
    patterns = []
    
    # Try loading from ConfigMap file
    config_file = os.getenv("ALLOWLIST_CONFIG", "/config/allowlist.yaml")
    if os.path.exists(config_file):
        try:
            with open(config_file, "r") as f:
                config = yaml.safe_load(f)
                for pattern in config.get("patterns", []):
                    patterns.append(re.compile(pattern, re.IGNORECASE))
            logger.info(f"Loaded {len(patterns)} allowlist patterns from {config_file}")
        except Exception as e:
            logger.error(f"Failed to load allowlist config: {e}")
    
    # Default patterns if no config
    if not patterns:
        default_patterns = [
            r"^https?://(www\.)?github\.com/",
            r"^https?://(www\.)?gitlab\.com/",
            r"^https?://(www\.)?bitbucket\.org/",
            r"^https?://(www\.)?docs\.",
            r"^https?://docs\.",  # Catch all docs.* domains
            r"^https?://.*\.github\.io/",  # GitHub Pages sites
            r"^https?://(www\.)?kserve\.github\.io/",  # KServe docs
            r"^https?://(www\.)?docs\.kuadrant\.io/",  # Kuadrant docs
            r"^https?://(www\.)?.*\.readthedocs\.",
            r"^https?://(www\.)?arxiv\.org/",
            r"^https?://(www\.)?medium\.com/",
            r"^https?://(www\.)?dev\.to/",
            r"^https?://(www\.)?stackoverflow\.com/",
            r"^https?://(www\.)?reddit\.com/r/(programming|machinelearning|kubernetes)",
            r"^https?://(www\.)?kubernetes\.io/",
            r"^https?://(www\.)?openshift\.com/",
            r"^https?://(www\.)?redhat\.com/",
            r"^https?://docs\.redhat\.com/",  # Red Hat documentation
            r"^https?://(www\.)?cloud\.google\.com/",
            r"^https?://(www\.)?aws\.amazon\.com/",
            r"^https?://(www\.)?azure\.microsoft\.com/",
            r"^https?://(www\.)?huggingface\.co/",
            r"^https?://(www\.)?pytorch\.org/",
            r"^https?://(www\.)?tensorflow\.org/",
        ]
        
        for pattern_str in default_patterns:
            patterns.append(re.compile(pattern_str, re.IGNORECASE))
        
        logger.info(f"Using {len(patterns)} default allowlist patterns")
    
    ALLOWLIST_PATTERNS = patterns
    return patterns


def is_url_allowed(url: str) -> bool:
    """Check if URL matches allowlist patterns."""
    patterns = load_allowlist_patterns()
    
    # If no patterns configured, allow all
    if not patterns:
        return True
    
    # Check if URL matches any pattern
    for pattern in patterns:
        if pattern.search(url):
            return True
    
    return False


def extract_links(text: str, base_url: str) -> List[str]:
    """Extract unique links from text content."""
    if not text:
        return []
    
    links: Set[str] = set()
    
    # Regex patterns for different link formats
    patterns = [
        # Standard URLs
        r'https?://[^\s<>"{}|\\^`\[\]]+',
        # Markdown links
        r'\[([^\]]+)\]\(([^)]+)\)',
        # HTML links
        r'href=["\']([^"\']+)["\']',
        # Plain domain references
        r'(?:www\.)?[a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?:/[^\s<>"{}|\\^`\[\]]*)?'
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            # Handle tuple results from markdown pattern
            if isinstance(match, tuple):
                match = match[1] if len(match) > 1 else match[0]
            
            # Clean and validate URL
            url = match.strip().rstrip(".,;:'\"")
            
            # Add protocol if missing
            if not url.startswith(("http://", "https://", "//")):
                if url.startswith("www."):
                    url = f"https://{url}"
                elif "." in url and not url.startswith("/"):
                    url = f"https://{url}"
            
            # Make relative URLs absolute
            if url.startswith("/"):
                url = urljoin(base_url, url)
            
            # Validate URL
            try:
                parsed = urlparse(url)
                if parsed.scheme in ["http", "https"] and parsed.netloc:
                    # Check if allowed
                    if is_url_allowed(url):
                        links.add(url)
            except Exception:
                continue
    
    # Filter out the base URL itself
    links.discard(base_url)
    
    # Sort for consistency
    return sorted(list(links))[:50]  # Limit to 50 links


def extract_github_repo_info(url: str) -> dict:
    """Extract GitHub repository information from URL."""
    github_pattern = re.compile(
        r"github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)(?:/(?P<path>.*))?",
        re.IGNORECASE
    )
    
    match = github_pattern.search(url)
    if match:
        return {
            "owner": match.group("owner"),
            "repo": match.group("repo"),
            "path": match.group("path") or "",
            "type": "github"
        }
    
    return None


def extract_domain(url: str) -> str:
    """Extract domain from URL for display."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.replace("www.", "")
        return domain
    except Exception:
        return "unknown"
