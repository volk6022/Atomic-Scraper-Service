import pytest
from src.infrastructure.queue.session_actor import SessionActor


@pytest.mark.asyncio
async def test_session_actor_browser():
    actor = SessionActor(session_id="test-session")
    await actor.start()
    result = await actor.execute(
        {"type": "goto", "params": {"url": "https://example.com"}}
    )
    assert result["status"] == "success"
    await actor.stop()
