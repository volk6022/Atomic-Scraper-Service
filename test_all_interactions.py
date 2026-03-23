import asyncio
import json
import httpx
import websockets
import time

BASE_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000/ws"
API_KEY = "your_internal_key"
HEADERS = {"X-API-Key": API_KEY}


async def test_all():
    async with httpx.AsyncClient(timeout=30.0) as client:
        print("\n--- 1. Testing /scraper ---")
        try:
            resp = await client.post(
                f"{BASE_URL}/scraper",
                headers=HEADERS,
                json={"url": "https://example.com"},
            )
            print(f"Status: {resp.status_code}")
            data = resp.json()
            print(f"Content Length: {len(data.get('content', ''))}")
            print(f"Task Status: {data.get('status')}")
        except Exception as e:
            print(f"Error /scraper: {e}")

        print("\n--- 2. Testing /serper ---")
        try:
            resp = await client.post(
                f"{BASE_URL}/serper", headers=HEADERS, json={"q": "taskiq"}
            )
            print(f"Status: {resp.status_code}")
            data = resp.json()
            print(f"Results Count: {len(data.get('organic', []))}")
            if data.get("organic"):
                print(f"First Result: {data['organic'][0]['title']}")
        except Exception as e:
            print(f"Error /serper: {e}")

        print("\n--- 3. Testing /omni-parse ---")
        try:
            resp = await client.post(
                f"{BASE_URL}/omni-parse",
                headers=HEADERS,
                json={"base64_image": "placeholder", "prompt": "test"},
            )
            print(f"Status: {resp.status_code}")
            print(f"Result: {resp.json()}")
        except Exception as e:
            print(f"Error /omni-parse: {e}")

        print("\n--- 4. Testing /jina-extract ---")
        try:
            resp = await client.post(
                f"{BASE_URL}/jina-extract",
                headers=HEADERS,
                json={
                    "html": "<html><body>Price: $100</body></html>",
                    "extraction_schema": {"price": "number"},
                },
            )
            print(f"Status: {resp.status_code}")
            print(f"Result: {resp.json()}")
        except Exception as e:
            print(f"Error /jina-extract: {e}")

        print("\n--- 5. Testing /sessions (Create) ---")
        session_id = None
        try:
            resp = await client.post(f"{BASE_URL}/sessions", headers=HEADERS)
            print(f"Status: {resp.status_code}")
            session_id = resp.json().get("session_id")
            print(f"Session ID: {session_id}")
        except Exception as e:
            print(f"Error /sessions: {e}")

        if session_id:
            print(f"\n--- 6. Testing WebSocket for Session {session_id} ---")
            try:
                # Wait for the session actor to start in the background
                await asyncio.sleep(2)
                async with websockets.connect(f"{WS_URL}/{session_id}") as ws:
                    print("Connected to WebSocket.")

                    # Command: GOTO
                    print("Sending GOTO...")
                    await ws.send(
                        json.dumps(
                            {"type": "goto", "params": {"url": "https://example.com"}}
                        )
                    )
                    res = await ws.recv()
                    print(f"GOTO Result: {res}")

                    # Command: SCREENSHOT
                    print("Sending SCREENSHOT...")
                    await ws.send(json.dumps({"type": "screenshot", "params": {}}))
                    res_json = json.loads(await ws.recv())
                    print(f"SCREENSHOT Status: {res_json.get('status')}")
                    if res_json.get("data"):
                        print(f"Screenshot Data Length: {len(res_json['data'])}")

            except Exception as e:
                print(f"Error WebSocket: {e}")

            print(f"\n--- 7. Testing /sessions/{session_id} (Delete) ---")
            try:
                resp = await client.delete(
                    f"{BASE_URL}/sessions/{session_id}", headers=HEADERS
                )
                print(f"Status: {resp.status_code}")
                print(f"Result: {resp.json()}")
            except Exception as e:
                print(f"Error session delete: {e}")


if __name__ == "__main__":
    asyncio.run(test_all())
