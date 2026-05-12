"""
Integration tests for research graph.

Tests graph building and basic structure.
Full execution tests require real LLM and are covered by other test suites.
"""

import pytest


class TestGraphBuilding:
    """Test graph can be built for different modes"""

    def test_build_speed_graph(self):
        """Should build speed mode graph without errors"""
        from src.actions.research.graph import build_graph

        graph = build_graph("speed")
        assert graph is not None

    def test_build_balanced_graph(self):
        """Should build balanced mode graph without errors"""
        from src.actions.research.graph import build_graph

        graph = build_graph("balanced")
        assert graph is not None

    def test_build_quality_graph(self):
        """Should build quality mode graph without errors"""
        from src.actions.research.graph import build_graph

        graph = build_graph("quality")
        assert graph is not None


class TestResearchState:
    """Test research state creation"""

    def test_create_initial_state(self):
        """Should create valid initial research state"""
        from src.actions.research.state import create_initial_state

        state = create_initial_state(query="test query", mode="speed")
        assert state["query"] == "test query"
        assert state["mode"] == "speed"
        assert "iteration" in state
