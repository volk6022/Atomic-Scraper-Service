"""Unit tests for research mode presets - TDD RED (expected to fail)"""

import pytest


class TestResearchModePresets:
    """Test mode preset values for speed/balanced/quality"""

    def test_speed_mode_has_correct_max_iterations(self):
        """Speed mode should have 2 iterations"""
        from src.actions.research.modes import get_mode_preset

        preset = get_mode_preset("speed")
        assert preset.max_iters == 2

    def test_balanced_mode_has_correct_max_iterations(self):
        """Balanced mode should have 6 iterations"""
        from src.actions.research.modes import get_mode_preset

        preset = get_mode_preset("balanced")
        assert preset.max_iters == 6

    def test_quality_mode_has_correct_max_iterations(self):
        """Quality mode should have 25 iterations"""
        from src.actions.research.modes import get_mode_preset

        preset = get_mode_preset("quality")
        assert preset.max_iters == 25

    def test_speed_mode_search_k(self):
        """Speed mode should have search_k of 3"""
        from src.actions.research.modes import get_mode_preset

        preset = get_mode_preset("speed")
        assert preset.search_k == 3

    def test_balanced_mode_search_k(self):
        """Balanced mode should have search_k of 5"""
        from src.actions.research.modes import get_mode_preset

        preset = get_mode_preset("balanced")
        assert preset.search_k == 5

    def test_quality_mode_search_k(self):
        """Quality mode should have search_k of 8"""
        from src.actions.research.modes import get_mode_preset

        preset = get_mode_preset("quality")
        assert preset.search_k == 8


class TestModeStateInitialization:
    """Test mode-to-state initialization"""

    def test_speed_mode_initializes_correct_state(self):
        """Speed mode should initialize state with correct defaults"""
        from src.actions.research.state import create_initial_state

        state = create_initial_state("What is AI?", "speed")

        assert state["mode"] == "speed"
        assert state["max_iters"] == 2
        assert state["max_tokens"] == 30000
        assert state["deadline_ts"] > 0

    def test_balanced_mode_initializes_correct_state(self):
        """Balanced mode should initialize state with correct defaults"""
        from src.actions.research.state import create_initial_state

        state = create_initial_state("Compare ML frameworks", "balanced")

        assert state["mode"] == "balanced"
        assert state["max_iters"] == 6

    def test_quality_mode_initializes_correct_state(self):
        """Quality mode should initialize state with correct defaults"""
        from src.actions.research.state import create_initial_state

        state = create_initial_state("Deep research on quantum computing", "quality")

        assert state["mode"] == "quality"
        assert state["max_iters"] == 25


class TestUserOverrides:
    """Test that user-supplied overrides take precedence over mode defaults"""

    def test_user_max_iterations_override(self):
        """User-provided max_iterations should override mode preset"""
        from src.actions.research.state import create_initial_state

        state = create_initial_state("test query", "balanced", max_iters_override=10)

        assert state["max_iters"] == 10

    def test_user_max_tokens_override(self):
        """User-provided max_tokens should override mode preset"""
        from src.actions.research.state import create_initial_state

        state = create_initial_state("test query", "speed", max_tokens_override=25000)

        assert state["max_tokens"] == 25000

    def test_override_respects_bounds(self):
        """Overrides should be validated against bounds"""
        from src.actions.research.state import create_initial_state

        with pytest.raises(ValueError):
            create_initial_state("test", "balanced", max_iters_override=100)

        with pytest.raises(ValueError):
            create_initial_state("test", "balanced", max_tokens_override=500)
