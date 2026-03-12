"""
OpenAI Client - клиент для OpenAI API (Structured Output).
"""
import logging
from typing import Dict, Any, Optional, List
from openai import AsyncOpenAI

from core.config import settings

logger = logging.getLogger(__name__)


class OpenAIClient:
    """
    Клиент для OpenAI API.
    
    Поддерживает:
    - Structured Output (JSON mode)
    - Анализ DOM дерева для принятия решений
    - Генерацию следующих действий
    """
    
    def __init__(self):
        """Инициализировать OpenAI клиент"""
        self.client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
        )
        self.model = settings.OPENAI_MODEL
    
    async def decide_next_action(
        self,
        dom_tree: str,
        objective: str,
        available_actions: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Принять решение о следующем действии на основе DOM и цели.
        
        Args:
            dom_tree: Упрощённое представление DOM дерева
            objective: Цель навигации (например, "найти кнопку входа")
            available_actions: Список доступных действий
        
        Returns:
            Dict с решением:
            {
                "action": "click",
                "selector": "#login-btn",
                "reason": "Found login button matching objective"
            }
        """
        actions_list = available_actions or [
            "click",
            "type",
            "scroll",
            "go_back",
            "go_forward",
            "extract",
        ]
        
        system_prompt = """Ты ассистент для автоматизации веб-навигации.
Твоя задача - анализировать DOM дерево и определять следующее действие.

Отвечай ТОЛЬКО в формате JSON:
{
    "action": "название_действия",
    "selector": "css_селектор_или_null",
    "value": "значение_для_ввода_или_null",
    "reason": "объяснение решения"
}"""

        user_prompt = f"""Цель: {objective}

Доступные действия: {', '.join(actions_list)}

DOM дерево:
{dom_tree[:10000]}  # Ограничиваем размер

Какое следующее действие?"""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=500,
            )
            
            result = response.choices[0].message.content
            import json
            return json.loads(result)
            
        except Exception as e:
            logger.error(f"OpenAI decision error: {e}")
            return {
                "action": "none",
                "selector": None,
                "reason": f"Error: {str(e)}",
            }
    
    async def extract_structured_data(
        self,
        content: str,
        schema: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Извлечь структурированные данные из контента.
        
        Args:
            content: HTML или текст для анализа
            schema: JSON Schema ожидаемых данных
        
        Returns:
            Dict с извлечёнными данными согласно схеме
        """
        import json
        
        system_prompt = """Ты ассистент для извлечения структурированных данных.
Извлеки данные из контента согласно JSON Schema.
Отвечай ТОЛЬКО валидным JSON согласно схеме."""

        user_prompt = f"""Schema:
{json.dumps(schema, indent=2)}

Контент:
{content[:15000]}

Извлеки данные согласно схеме:"""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=1000,
            )
            
            result = response.choices[0].message.content
            return json.loads(result)
            
        except Exception as e:
            logger.error(f"OpenAI extraction error: {e}")
            return {"error": str(e)}
