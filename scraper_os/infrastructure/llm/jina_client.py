"""
Jina Client - клиент для Jina Reader API.

Jina Reader преобразует HTML в Markdown и может извлекать
структурированные данные.
"""
import logging
from typing import Dict, Any, Optional
import httpx

from core.config import settings

logger = logging.getLogger(__name__)


class JinaClient:
    """
    Клиент для Jina Reader API.
    
    Использует Jina AI Reader для преобразования HTML в Markdown
    и извлечения структурированных данных.
    
    API: https://r.jina.ai/
    """
    
    def __init__(self):
        """Инициализировать Jina клиент"""
        self.base_url = "https://r.jina.ai"
        self.headers = {
            "Content-Type": "application/json",
            "X-Return-Format": "markdown",  # или 'html', 'text'
        }
        
        if settings.JINA_API_KEY:
            self.headers["Authorization"] = f"Bearer {settings.JINA_API_KEY}"
        
        self.timeout = httpx.Timeout(settings.REQUEST_TIMEOUT_SECONDS)
    
    async def get_markdown(self, url: str) -> Dict[str, Any]:
        """
        Получить Markdown версию URL.
        
        Args:
            url: URL для преобразования
        
        Returns:
            Dict с результатом:
            {
                "success": bool,
                "data": {"markdown": str, "title": str, "url": str},
                "error": str или None
            }
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                # Jina Reader API
                response = await client.get(
                    f"{self.base_url}/{url}",
                    headers={
                        "X-Return-Format": "markdown",
                        "X-With-Generated-Alt": "true",  # Генерировать alt для изображений
                    },
                )
                response.raise_for_status()
                
                # Парсинг заголовков из ответа
                title = response.headers.get("X-Title", "")
                
                return {
                    "success": True,
                    "data": {
                        "markdown": response.text,
                        "title": title,
                        "url": url,
                    },
                    "error": None,
                }
                
            except httpx.HTTPStatusError as e:
                logger.error(f"Jina HTTP error for {url}: {e}")
                return {
                    "success": False,
                    "data": None,
                    "error": f"HTTP {e.response.status_code}",
                }
                
            except Exception as e:
                logger.error(f"Jina error for {url}: {e}")
                return {
                    "success": False,
                    "data": None,
                    "error": str(e),
                }
    
    async def html_to_markdown(self, html: str) -> Dict[str, Any]:
        """
        Преобразовать HTML в Markdown.
        
        Args:
            html: HTML контент
        
        Returns:
            Dict с Markdown
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/",
                    content=html,
                    headers={
                        "Content-Type": "text/html",
                        "X-Return-Format": "markdown",
                    },
                )
                response.raise_for_status()
                
                return {
                    "success": True,
                    "data": {
                        "markdown": response.text,
                    },
                    "error": None,
                }
                
            except Exception as e:
                logger.error(f"Jina HTML-to-markdown error: {e}")
                return {
                    "success": False,
                    "data": None,
                    "error": str(e),
                }
    
    async def extract_structured(
        self,
        url: str,
        schema: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Извлечь структурированные данные с URL.
        
        Args:
            url: URL для скрапинга
            schema: JSON Schema для извлечения
        
        Returns:
            Dict с извлечёнными данными
        """
        import json
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/{url}",
                    headers={
                        "X-Return-Format": "json",
                        "X-Json-Response": json.dumps(schema),
                    },
                )
                response.raise_for_status()
                
                return {
                    "success": True,
                    "data": response.json(),
                    "error": None,
                }
                
            except Exception as e:
                logger.error(f"Jina structured extraction error: {e}")
                return {
                    "success": False,
                    "data": None,
                    "error": str(e),
                }
