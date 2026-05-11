"""Unit tests for research graph state transitions - TDD RED (expected to fail)"""

import pytest
import time


class TestShouldContinueRouter:
    """Test the should_continue router function truth table"""

    def test_continue_when_gaps_remain_and_not_beast_mode(self):
        """Should continue to plan when gaps remain and not in beast_mode"""
        from src.actions.research.graph import should_continue

        state = {
            "gaps": ["question 1", "question 2"],
            "beast_mode": False,
            "iteration": 2,
            "max_iters": 6,
            "stall_counter": 0,
        }

        result = should_continue(state)
        assert result == "plan"

    def test_stop_when_gaps_empty(self):
        """Should stop when gaps are empty"""
        from src.actions.research.graph import should_continue

        state = {
            "gaps": [],
            "beast_mode": False,
            "iteration": 2,
            "max_iters": 6,
            "stall_counter": 0,
        }

        result = should_continue(state)
        assert result == "answer"

    def test_stop_when_beast_mode_true(self):
        """Should stop when beast_mode is triggered"""
        from src.actions.research.graph import should_continue

        state = {
            "gaps": ["question 1"],
            "beast_mode": True,
            "iteration": 2,
            "max_iters": 6,
            "stall_counter": 0,
        }

        result = should_continue(state)
        assert result == "answer"

    def test_stop_at_max_iterations(self):
        """Should stop when iteration >= max_iters"""
        from src.actions.research.graph import should_continue

        state = {
            "gaps": ["question 1"],
            "beast_mode": False,
            "iteration": 6,
            "max_iters": 6,
            "stall_counter": 0,
        }

        result = should_continue(state)
        assert result == "answer"

    def test_stop_at_stall_threshold(self):
        """Should stop when stall_counter >= 2"""
        from src.actions.research.graph import should_continue

        state = {
            "gaps": ["question 1"],
            "beast_mode": False,
            "iteration": 2,
            "max_iters": 6,
            "stall_counter": 2,
        }

        result = should_continue(state)
        assert result == "answer"


class TestAnswerToWriterEdge:
    """Test edge from answer to writer"""

    def test_answer_node_transitions_to_writer(self):
        """answer_node should always transition to writer"""
        from src.actions.research.graph import ANSWER_TO_WRITER

        assert ANSWER_TO_WRITER == "writer"


class TestGraphStructure:
    """Test the compiled graph has correct structure"""

    def test_graph_compiles_for_speed_mode(self):
        """Graph should compile successfully for speed mode"""
        from src.actions.research.graph import build_graph

        graph = build_graph("speed")
        assert graph is not None

    def test_graph_compiles_for_balanced_mode(self):
        """Graph should compile successfully for balanced mode"""
        from src.actions.research.graph import build_graph

        graph = build_graph("balanced")
        assert graph is not None

    def test_graph_compiles_for_quality_mode(self):
        """Graph should compile successfully for quality mode"""
        from src.actions.research.graph import build_graph

        graph = build_graph("quality")
        assert graph is not None

    def test_graph_has_correct_nodes(self):
        """Graph should have all required nodes"""
        from src.actions.research.graph import build_graph, REQUIRED_NODES

        graph = build_graph("speed")
        for node in REQUIRED_NODES:
            assert node in graph.nodes or node in ["__start__", "__end__"]
