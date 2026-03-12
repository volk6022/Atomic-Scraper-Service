"""
LLM Facade - единая точка входа для всех AI операций.

Фасад объединяет OpenAI и Jina клиентов, предоставляя
простой интерфейс для Actions.
"""
import logging
import base64
from typing import Dict, Any, Optional, List

from infrastructure.llm.openai_client import OpenAIClient
from infrastructure.llm.jina_client import JinaClient

logger = logging.getLogger(__name__)


class LLMFacade:
    """
    Фасад для LLM операций.
    
    Предоставляет унифицированный интерфейс для:
    - Преобразования HTML в Markdown (Jina)
    - Извлечения структурированных данных (OpenAI / Jina)
    - Анализа изображений (Omni-Parser через OpenAI Vision)
    - Принятия решений о навигации (OpenAI)
    """
    
    def __init__(self):
        """Инициализировать все LLM клиенты"""
        self.openai = OpenAIClient()
        self.jina = JinaClient()
        logger.info("LLMFacade initialized")
    
    async def get_jina_markdown(
        self,
        html: Optional[str] = None,
        url: Optional[str] = None,
        extract_schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Получить Markdown из HTML или URL через Jina.
        
        Args:
            html: HTML контент (опционально)
            url: URL для скрапинга (опционально)
            extract_schema: JSON Schema для структурированного извлечения
        
        Returns:
            Dict с результатом
        """
        if url and extract_schema:
            # Структурированное извлечение с URL
            return await self.jina.extract_structured(url, extract_schema)
        
        elif url:
            # Получение Markdown с URL
            return await self.jina.get_markdown(url)
        
        elif html:
            # Конвертация HTML в Markdown
            return await self.jina.html_to_markdown(html)
        
        else:
            return {
                "success": False,
                "data": None,
                "error": "Either html or url must be provided",
            }
    
    async def get_omni_coordinates(
        self,
        base64_image: str,
        target: str,
    ) -> Dict[str, Any]:
        """
        Найти координаты элемента на скриншоте через Omni-Parser.
        
        Использует OpenAI Vision для анализа изображения и поиска
        целевого элемента.
        
        Args:
            base64_image: Base64 кодированное изображение
            target: Описание цели (например, "Login button")
        
        Returns:
            Dict с координатами:
            {
                "success": bool,
                "data": {"x": int, "y": int, "confidence": float},
                "error": str или None
            }
        """
        system_prompt = """Ты Omni-Parser для веб-автоматизации.
Проанализируй скриншот веб-страницы и найди координаты целевого элемента.

Отвечай ТОЛЬКО в формате JSON:
{
    "x": число,
    "y": число,
    "confidence": число_от_0_до_1,
    "description": "что найдено"
}"""

        user_prompt = f"Найди на скриншоте: {target}"
        
        try:
            # Используем OpenAI Vision API
            response = await self.openai.client.chat.completions.create(
                model="gpt-4o-mini",  # Или другая vision-модель
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}"
                                },
                            },
                        ],
                    },
                ],
                response_format={"type": "json_object"},
                max_tokens=300,
            )
            
            import json
            result = json.loads(response.choices[0].message.content)
            
            return {
                "success": True,
                "data": {
                    "x": result.get("x", 0),
                    "y": result.get("y", 0),
                    "confidence": result.get("confidence", 0.5),
                    "description": result.get("description", target),
                },
                "error": None,
            }
            
        except Exception as e:
            logger.error(f"Omni-Parser error: {e}")
            return {
                "success": False,
                "data": None,
                "error": str(e),
            }
    
    async def decide_next_action(
        self,
        dom_tree: str,
        objective: str,
        available_actions: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Принять решение о следующем действии.
        
        Args:
            dom_tree: Упрощённое DOM дерево
            objective: Цель навигации
            available_actions: Список доступных действий
        
        Returns:
            Dict с решением
        """
        return await self.openai.decide_next_action(
            dom_tree,
            objective,
            available_actions,
        )
    
    async def extract_structured_data(
        self,
        content: str,
        schema: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Извлечь структурированные данные.
        
        Args:
            content: HTML или текст
            schema: JSON Schema
        
        Returns:
            Dict с извлечёнными данными
        """
        return await self.openai.extract_structured_data(content, schema)
