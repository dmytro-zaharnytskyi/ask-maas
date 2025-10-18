"""
Data models for chat functionality
"""
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Chat request model"""
    query: str = Field(..., min_length=1, max_length=500)
    page_url: str = Field(...)
    session_id: Optional[str] = None
    stream: bool = True


class Citation(BaseModel):
    """Citation model for referenced content"""
    text: str
    url: str
    title: Optional[str] = None
    score: float = 0.0
    line_numbers: Optional[str] = None  # e.g., "42-55"
    

class ChatResponse(BaseModel):
    """Chat response model"""
    id: str
    answer: str
    citations: List[Citation]
    metadata: Dict
    

class StreamEvent(BaseModel):
    """SSE stream event"""
    id: str
    type: str  # "start", "text", "citation", "error", "done"
    content: Optional[str] = None
    citations: Optional[List[Citation]] = None
    metadata: Optional[Dict] = None


class Chunk(BaseModel):
    """Document chunk model"""
    id: str
    text: str
    embedding: Optional[List[float]] = None
    metadata: Dict = Field(default_factory=dict)
    score: float = 0.0
    url: Optional[str] = None
    title: Optional[str] = None
    headings: Optional[List[str]] = None
    source: str = "article"  # "article" or "github"
