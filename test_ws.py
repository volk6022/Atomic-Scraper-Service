import asyncio
import websockets
import json
import httpx

API_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000/ws"
API_KEY = "default_internal_key"


async def test_websocket_session():
    # 1. Create a session
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_URL}/sessions", headers={"X-API-Key": API_KEY}
        )
        session_id = response.json()["session_id"]
        print(f"Session created: {session_id}")

    # 2. Connect via WebSocket
    async with websockets.connect(f"{WS_URL}/{session_id}") as websocket:
        print(f"Connected to session: {session_id}")

        # 3. Send GOTO command
        await websocket.send(
            json.dumps({"type": "goto", "params": {"url": "https://example.com"}})
        )

        # 4. Wait for response
        response = await websocket.recv()
        print(f"GOTO response: {response}")

        # 5. Send SCREENSHOT command
        await websocket.send(json.dumps({"type": "screenshot", "params": {}}))

        # 6. Wait for response
        response = json.loads(await websocket.recv())
        print(f"SCREENSHOT response status: {response['status']}")
        if response["status"] == "success":
            print(
                "Screenshot received (base64 length:",
                len(response.get("data", "")),
                ")",
            )

        # 7. Close session manually
        async with httpx.AsyncClient() as client:
            await client.delete(
                f"{API_URL}/sessions/{session_id}", headers={"X-API-Key": API_KEY}
            )
            print(f"Session {session_id} deleted")


if __name__ == "__main__":
    asyncio.run(test_websocket_session())
