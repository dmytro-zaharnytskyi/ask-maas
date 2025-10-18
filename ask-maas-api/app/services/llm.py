"""
LLM service for generating responses using vLLM
"""
import asyncio
import json
from typing import AsyncGenerator, Optional
import httpx
import structlog

from app.services.config import Settings

logger = structlog.get_logger()


class LLMService:
    """Service for LLM generation with vLLM"""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.http_client = httpx.AsyncClient(timeout=60.0)
    
    async def generate_stream(
        self,
        query: str,
        context: str,
        max_tokens: Optional[int] = None
    ) -> AsyncGenerator[str, None]:
        """
        Generate streaming response from LLM
        """
        max_tokens = max_tokens or self.settings.MAX_TOKENS
        
        # Construct prompt
        prompt = self._build_prompt(query, context)
        
        # Prepare request payload for chat format
        payload = {
            "model": self.settings.MODEL_NAME,
            "messages": [
                {"role": "system", "content": self.settings.SYSTEM_PROMPT},
                {"role": "user", "content": f"Context from the article and related resources:\n\n{context}\n\n---\n\nQuestion: {query}"}
            ],
            "max_tokens": max_tokens,
            "temperature": self.settings.TEMPERATURE,
            "top_p": self.settings.TOP_P,
            "stream": True
        }
        
        try:
            # Stream from vLLM
            async with self.http_client.stream(
                "POST",
                f"{self.settings.VLLM_URL}/v1/chat/completions",
                json=payload,
                timeout=self.settings.STREAM_TIMEOUT
            ) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        
                        try:
                            chunk = json.loads(data)
                            if "choices" in chunk and len(chunk["choices"]) > 0:
                                # Handle chat completion format
                                delta = chunk["choices"][0].get("delta", {})
                                text = delta.get("content", "")
                                if text:
                                    yield text
                        except json.JSONDecodeError:
                            continue
                        
        except httpx.HTTPStatusError as e:
            logger.error(
                "LLM request failed",
                status=e.response.status_code,
                error=str(e)
            )
            yield "I encountered an error generating a response. Please try again."
            
        except Exception as e:
            logger.error("LLM generation failed", error=str(e), exc_info=True)
            yield "An error occurred while generating the response."
    
    async def generate(
        self,
        query: str,
        context: str,
        max_tokens: Optional[int] = None
    ) -> str:
        """
        Generate complete response from LLM (non-streaming)
        """
        max_tokens = max_tokens or self.settings.MAX_TOKENS
        
        # Construct prompt
        prompt = self._build_prompt(query, context)
        
        # Prepare request payload for chat format
        payload = {
            "model": self.settings.MODEL_NAME,
            "messages": [
                {"role": "system", "content": self.settings.SYSTEM_PROMPT},
                {"role": "user", "content": f"Context from the article and related resources:\n\n{context}\n\n---\n\nQuestion: {query}"}
            ],
            "max_tokens": max_tokens,
            "temperature": self.settings.TEMPERATURE,
            "top_p": self.settings.TOP_P,
            "stream": False
        }
        
        try:
            response = await self.http_client.post(
                f"{self.settings.VLLM_URL}/v1/chat/completions",
                json=payload,
                timeout=self.settings.REQUEST_TIMEOUT
            )
            response.raise_for_status()
            
            result = response.json()
            if "choices" in result and len(result["choices"]) > 0:
                # Handle chat completion format
                message = result["choices"][0].get("message", {})
                return message.get("content", "").strip()
            
            return "No response generated."
            
        except Exception as e:
            logger.error("LLM generation failed", error=str(e), exc_info=True)
            return "An error occurred while generating the response."
    
    def _build_prompt(self, query: str, context: str) -> str:
        """
        Build prompt for the LLM
        """
        prompt = f"""{self.settings.SYSTEM_PROMPT}

Context from the article and related resources:

{context}

---

Question: {query}

Answer: Based on the provided context, """
        
        return prompt
    
    async def close(self):
        """Clean up resources"""
        await self.http_client.aclose()
