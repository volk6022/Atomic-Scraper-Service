"""Integration tests for research graph - TDD RED (expected to fail)"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from langchain_core.messages import HumanMessage, AIMessage
import time


TEST_CONFIG = {"configurable": {"thread_id": "test-thread"}}


class TestGraphCompilation:
    """Test graph compiles and runs correctly"""

    @pytest.mark.asyncio
    async def test_graph_terminates_within_max_iters(self):
        """Graph should terminate within mode's max_iters"""
        from src.actions.research.graph import build_graph
        from src.actions.research.state import create_initial_state

        graph = build_graph("speed")

        initial_state = create_initial_state(
            query="What is Python?",
            mode="speed",
            max_iters_override=2,
        )

        result = await graph.ainvoke(initial_state, config=TEST_CONFIG)

        assert result["iteration"] <= 2

    @pytest.mark.asyncio
    async def test_graph_emits_valid_research_report(self):
        """Graph should emit valid ResearchReport with at least 1 citation"""
        from src.actions.research.graph import build_graph
        from src.actions.research.state import create_initial_state

        graph = build_graph("balanced")

        initial_state = create_initial_state(
            query="What is machine learning?",
            mode="balanced",
        )

        result = await graph.ainvoke(initial_state, config=TEST_CONFIG)

        assert "answer_draft" in result
        assert len(result.get("citations", [])) >= 1

    @pytest.mark.asyncio
    async def test_beast_mode_still_produces_answer(self):
        """Tiny token_budget should trigger beast_mode but still produce answer"""
        from src.actions.research.graph import build_graph
        from src.actions.research.state import create_initial_state

        graph = build_graph("speed")

        initial_state = create_initial_state(
            query="What is AI?",
            mode="speed",
            max_tokens_override=1000,
        )

        result = await graph.ainvoke(initial_state, config=TEST_CONFIG)

        assert result["beast_mode"] is True
        assert "answer_draft" in result
        assert len(result["answer_draft"]) > 0


class TestNodeEventEmission:
    """Test SSE event emission during graph traversal (US4)"""

    @pytest.mark.asyncio
    async def test_events_emitted_in_order(self):
        """Graph traversal should emit node events in expected order"""
        from src.actions.research.graph import build_graph
        from src.actions.research.state import create_initial_state

        graph = build_graph("speed")

        initial_state = create_initial_state(
            query="What is Python?",
            mode="speed",
        )

        events = []
        with patch("src.actions.research.nodes.emit_node_event") as mock_emit:
            mock_emit.side_effect = lambda e: events.append(e)

            result = await graph.ainvoke(initial_state, config=TEST_CONFIG)

        node_names = [e.get("node") for e in events if e.get("type") == "node_entered"]

        expected_order = ["classify", "plan", "search", "rank_dedupe"]
        for expected in expected_order:
            if expected in node_names:
                idx = node_names.index(expected)
                for later in expected_order[idx + 1 :]:
                    if later in node_names:
                        assert node_names.index(later) > idx

    @pytest.mark.asyncio
    async def test_completed_event_emitted(self):
        """Graph should emit completed event when finished"""
        from src.actions.research.graph import build_graph
        from src.actions.research.state import create_initial_state

        graph = build_graph("speed")

        initial_state = create_initial_state(
            query="test",
            mode="speed",
        )

        with patch("src.actions.research.nodes.emit_node_event") as mock_emit:
            await graph.ainvoke(initial_state, config=TEST_CONFIG)

        completed_events = [
            e for e in mock_emit.call_args_list if e[0][0].get("type") == "completed"
        ]
        assert len(completed_events) >= 1


class TestFakeChatModelIntegration:
    """Test graph with FakeChatModel for deterministic testing"""

    @pytest.mark.asyncio
    async def test_graph_with_fake_llm_terminates(self):
        """Graph with FakeChatModel should still terminate"""
        from langchain_core.outputs import ChatGeneration, ChatResult
        from langchain_core.messages import AIMessage

        class FakeChatModel:
            def __init__(self):
                self.call_count = 0

            def bind_tools(self, tools):
                return self

            async def invoke(self, messages):
                self.call_count += 1
                return AIMessage(content=f"Fake response {self.call_count}")

            async def ainvoke(self, messages):
                return await self.invoke(messages)

        fake_llm = FakeChatModel()

        from src.actions.research import nodes
        from src.actions.research.graph import build_graph

        with patch.object(nodes, "get_extraction_client") as mock_client:
            mock_facade = MagicMock()
            mock_facade.extract = AsyncMock(
                return_value={"type": "exploratory", "gaps": ["test gap"]}
            )
            mock_client.return_value = mock_facade

            graph = build_graph("speed")
            initial_state = create_initial_state("test", "speed")

            result = await graph.ainvoke(initial_state, config=TEST_CONFIG)

        assert result is not None


def create_initial_state(query: str, mode: str, **kwargs):
    """Helper to create initial state for tests"""
    from src.actions.research.state import create_initial_state

    return create_initial_state(query=query, mode=mode, **kwargs)
