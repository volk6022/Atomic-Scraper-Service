"""Unit tests for research graph nodes - TDD RED (expected to fail)"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import time


class TestClassifyNode:
    """Test classify_node transforms query to type"""

    @pytest.mark.asyncio
    async def test_classify_returns_query_type(self):
        """classify_node should return query type (factoid/comparative/exploratory/decomposable)"""
        from src.actions.research.nodes import classify_node
        from src.actions.research.state import ResearchState

        state: ResearchState = {
            "query": "What is Python?",
            "mode": "speed",
            "max_iters": 2,
            "token_budget": 30000,
            "tokens_used": 0,
            "deadline_ts": time.time() + 120,
            "iteration": 0,
            "gaps": [],
            "visited_urls": set(),
            "candidate_urls": [],
            "facts": [],
            "citations": [],
            "answer_draft": None,
            "beast_mode": False,
            "stall_counter": 0,
            "trace": [],
        }

        result = await classify_node(state)
        assert "query_type" in result
        assert result["query_type"] in [
            "factoid",
            "comparative",
            "exploratory",
            "decomposable",
        ]
        assert len(result["gaps"]) > 0


class TestPlanNode:
    """Test plan_node generates gaps from evidence"""

    @pytest.mark.asyncio
    async def test_plan_generates_gaps(self):
        """plan_node should generate open questions from current evidence"""
        from src.actions.research.nodes import plan_node
        from src.actions.research.state import ResearchState

        state: ResearchState = {
            "query": "What is AI?",
            "mode": "speed",
            "max_iters": 2,
            "token_budget": 30000,
            "tokens_used": 0,
            "deadline_ts": time.time() + 120,
            "iteration": 0,
            "gaps": [],
            "visited_urls": set(),
            "candidate_urls": [],
            "facts": [],
            "citations": [
                {
                    "url": "https://example.com",
                    "title": "AI Article",
                    "snippet": "AI is...",
                }
            ],
            "answer_draft": None,
            "beast_mode": False,
            "stall_counter": 0,
            "trace": [],
        }

        result = await plan_node(state)
        assert "gaps" in result
        assert len(result["gaps"]) > 0


class TestSearchNode:
    """Test search_node performs web search"""

    @pytest.mark.asyncio
    async def test_search_returns_candidates(self):
        """search_node should append candidate URLs from search"""
        from src.actions.research.nodes import search_node
        from src.actions.research.state import ResearchState

        state: ResearchState = {
            "query": "What is AI?",
            "mode": "speed",
            "max_iters": 2,
            "token_budget": 30000,
            "tokens_used": 0,
            "deadline_ts": time.time() + 120,
            "iteration": 0,
            "gaps": ["What is artificial intelligence?"],
            "visited_urls": set(),
            "candidate_urls": [],
            "facts": [],
            "citations": [],
            "answer_draft": None,
            "beast_mode": False,
            "stall_counter": 0,
            "trace": [],
        }

        result = await search_node(state)
        assert "candidate_urls" in result
        assert len(result["candidate_urls"]) > 0


class TestRankDedupeNode:
    """Test rank_dedupe_node filters and scores URLs"""

    @pytest.mark.asyncio
    async def test_dedupe_removes_visited(self):
        """rank_dedupe_node should remove already visited URLs"""
        from src.actions.research.nodes import rank_dedupe_node
        from src.actions.research.state import ResearchState

        state: ResearchState = {
            "query": "What is AI?",
            "mode": "speed",
            "max_iters": 2,
            "token_budget": 30000,
            "tokens_used": 0,
            "deadline_ts": time.time() + 120,
            "iteration": 0,
            "gaps": [],
            "visited_urls": {"https://visited.com"},
            "candidate_urls": [
                {"url": "https://visited.com", "title": "Visited", "score": 0.9},
                {"url": "https://new.com", "title": "New", "score": 0.8},
            ],
            "facts": [],
            "citations": [],
            "answer_draft": None,
            "beast_mode": False,
            "stall_counter": 0,
            "trace": [],
        }

        result = await rank_dedupe_node(state)
        urls = [c["url"] for c in result["candidate_urls"]]
        assert "https://visited.com" not in urls
        assert "https://new.com" in urls

    @pytest.mark.asyncio
    async def test_stall_counter_increments_on_zero_new(self):
        """rank_dedupe_node should increment stall_counter when no new URLs"""
        from src.actions.research.nodes import rank_dedupe_node
        from src.actions.research.state import ResearchState

        state: ResearchState = {
            "query": "What is AI?",
            "mode": "speed",
            "max_iters": 2,
            "token_budget": 30000,
            "tokens_used": 0,
            "deadline_ts": time.time() + 120,
            "iteration": 0,
            "gaps": [],
            "visited_urls": {"https://all-visited.com"},
            "candidate_urls": [
                {"url": "https://all-visited.com", "title": "Old", "score": 0.9},
            ],
            "facts": [],
            "citations": [],
            "answer_draft": None,
            "beast_mode": False,
            "stall_counter": 0,
            "trace": [],
        }

        result = await rank_dedupe_node(state)
        assert result["stall_counter"] == 1


class TestReflectNode:
    """Test reflect_node evaluates progress and triggers beast_mode"""

    @pytest.mark.asyncio
    async def test_beast_mode_at_85_percent_budget(self):
        """reflect_node should trigger beast_mode when tokens_used >= 85% token_budget"""
        from src.actions.research.nodes import reflect_node
        from src.actions.research.state import ResearchState

        state: ResearchState = {
            "query": "What is AI?",
            "mode": "balanced",
            "max_iters": 6,
            "token_budget": 100000,
            "tokens_used": 86000,
            "deadline_ts": time.time() + 300,
            "iteration": 3,
            "gaps": ["more questions"],
            "visited_urls": set(),
            "candidate_urls": [],
            "facts": [
                {"claim": "fact", "source_url": "https://x.com", "confidence": 0.9}
            ],
            "citations": [],
            "answer_draft": None,
            "beast_mode": False,
            "stall_counter": 0,
            "trace": [],
        }

        result = await reflect_node(state)
        assert result["beast_mode"] is True

    @pytest.mark.asyncio
    async def test_beast_mode_at_deadline(self):
        """reflect_node should trigger beast_mode when time > deadline_ts"""
        from src.actions.research.nodes import reflect_node
        from src.actions.research.state import ResearchState

        state: ResearchState = {
            "query": "What is AI?",
            "mode": "balanced",
            "max_iters": 6,
            "token_budget": 100000,
            "tokens_used": 10000,
            "deadline_ts": time.time() - 1,
            "iteration": 3,
            "gaps": ["more questions"],
            "visited_urls": set(),
            "candidate_urls": [],
            "facts": [],
            "citations": [],
            "answer_draft": None,
            "beast_mode": False,
            "stall_counter": 0,
            "trace": [],
        }

        result = await reflect_node(state)
        assert result["beast_mode"] is True

    @pytest.mark.asyncio
    async def test_beast_mode_at_stall_threshold(self):
        """reflect_node should trigger beast_mode when stall_counter >= 2"""
        from src.actions.research.nodes import reflect_node
        from src.actions.research.state import ResearchState

        state: ResearchState = {
            "query": "What is AI?",
            "mode": "balanced",
            "max_iters": 6,
            "token_budget": 100000,
            "tokens_used": 10000,
            "deadline_ts": time.time() + 300,
            "iteration": 3,
            "gaps": ["more questions"],
            "visited_urls": set(),
            "candidate_urls": [],
            "facts": [],
            "citations": [],
            "answer_draft": None,
            "beast_mode": False,
            "stall_counter": 2,
            "trace": [],
        }

        result = await reflect_node(state)
        assert result["beast_mode"] is True


class TestScrapeNode:
    """Test scrape_node fetches URLs"""

    @pytest.mark.asyncio
    async def test_scrape_marks_visited(self):
        """scrape_node should mark URLs as visited"""
        from src.actions.research.nodes import scrape_node
        from src.actions.research.state import ResearchState
        from unittest.mock import AsyncMock, patch

        state: ResearchState = {
            "query": "What is AI?",
            "mode": "speed",
            "max_iters": 2,
            "token_budget": 30000,
            "tokens_used": 0,
            "deadline_ts": time.time() + 120,
            "iteration": 0,
            "gaps": [],
            "visited_urls": set(),
            "candidate_urls": [
                {"url": "https://example.com", "title": "Example", "score": 0.9},
            ],
            "facts": [],
            "citations": [],
            "answer_draft": None,
            "beast_mode": False,
            "stall_counter": 0,
            "trace": [],
        }

        with patch("src.actions.research.tools.scrape_url") as mock_scrape:
            mock_scrape.ainvoke = AsyncMock(
                return_value={
                    "success": True,
                    "text": "Test content",
                    "url": "https://example.com",
                }
            )
            result = await scrape_node(state)

        assert "https://example.com" in result["visited_urls"]


class TestAnswerNode:
    """Test answer_node synthesizes final answer"""

    @pytest.mark.asyncio
    async def test_answer_always_produces_output(self):
        """answer_node should always produce an answer, even in beast_mode"""
        from src.actions.research.nodes import answer_node
        from src.actions.research.state import ResearchState

        state: ResearchState = {
            "query": "What is AI?",
            "mode": "speed",
            "max_iters": 2,
            "token_budget": 30000,
            "tokens_used": 26000,
            "deadline_ts": time.time() + 120,
            "iteration": 2,
            "gaps": [],
            "visited_urls": {"https://x.com"},
            "candidate_urls": [],
            "facts": [
                {
                    "claim": "AI is artificial intelligence",
                    "source_url": "https://x.com",
                    "confidence": 0.8,
                }
            ],
            "citations": [{"url": "https://x.com", "title": "X", "snippet": "AI"}],
            "answer_draft": None,
            "beast_mode": True,
            "stall_counter": 0,
            "trace": [],
        }

        result = await answer_node(state)
        assert "answer_draft" in result
        assert len(result["answer_draft"]) > 0
