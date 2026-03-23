import httpx
import asyncio


async def test():
    async with httpx.AsyncClient() as client:
        for key in ["your_internal_key", "default_internal_key"]:
            try:
                resp = await client.post(
                    "http://localhost:8000/serper",
                    headers={"X-API-Key": key},
                    json={"q": "test"},
                )
                print(f"Key '{key}' Status: {resp.status_code}")
            except Exception as e:
                print(f"Key '{key}' Error: {e}")


if __name__ == "__main__":
    asyncio.run(test())
