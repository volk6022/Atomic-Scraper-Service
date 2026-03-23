from openai import AsyncOpenAI
from typing import Any, Dict, Optional
from src.infrastructure.external_api.facade import LLMFacade


class OpenAICompatibleClient(LLMFacade):
    def __init__(self, base_url: str, api_key: str, model_name: str):
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self.model_name = model_name

    async def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = await self.client.chat.completions.create(
            model=self.model_name, messages=messages
        )
        content = response.choices[0].message.content
        if content is None:
            return ""
        return content

    async def extract(self, content: str, schema: Dict[str, Any]) -> Dict[str, Any]:
        # Simple extraction logic using the model
        prompt = f"Extract structured data from the following content based on this schema: {schema}\n\nContent:\n{content}"
        response_text = await self.generate(prompt)
        # In a real scenario, you'd want robust JSON parsing here
        import json

        try:
            return json.loads(response_text)
        except:
            return {"raw_response": response_text}
