import json
from datetime import datetime
from pathlib import Path

import pytest

# Will import from review_app.ingest once it's implemented
# from review_app.ingest import detect_format, parse_local, parse_atomic, to_row


@pytest.fixture
def sample_local_json():
    """Load the local format sample fixture."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "sample_local.json"
    with open(fixture_path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def sample_atomic_json():
    """Load the atomic format sample fixture."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "sample_atomic.json"
    with open(fixture_path, encoding="utf-8") as f:
        return json.load(f)


class TestDetectFormat:
    def test_detect_format_local(self, sample_local_json):
        """Test that detect_format correctly identifies local format."""
        from review_app.ingest import detect_format

        result = detect_format(sample_local_json)
        assert result == "local"

    def test_detect_format_atomic(self, sample_atomic_json):
        """Test that detect_format correctly identifies atomic format."""
        from review_app.ingest import detect_format

        result = detect_format(sample_atomic_json)
        assert result == "atomic"

    def test_detect_format_empty_dict(self):
        """Test that detect_format returns 'unknown' for empty dict."""
        from review_app.ingest import detect_format

        result = detect_format({})
        assert result == "unknown"

    def test_detect_format_unrelated_dict(self):
        """Test that detect_format returns 'unknown' for unrelated dict."""
        from review_app.ingest import detect_format

        result = detect_format({"foo": 1, "bar": "baz"})
        assert result == "unknown"


class TestParseLocal:
    def test_parse_local_basic(self, sample_local_json):
        """Test basic local format parsing with key column assertions."""
        from review_app.ingest import parse_local

        mtime = datetime(2026, 5, 30, 10, 0, 0)
        source_file = Path("test_data/1000341388__local.json")

        result = parse_local(sample_local_json, source_file, mtime)

        assert result["model_key"] == "local"
        assert result["oid"] == "1000341388"
        assert result["name"] == "Адвокат Фремм"
        assert isinstance(result["categories"], list)
        assert len(result["categories"]) > 0
        assert result["critic_score"] == 9.0
        assert result["critic_verdict"] == "pass"
        assert result["turns"] == 12
        assert result["tokens_total"] == 78792
        assert result["forced_submit"] is False
        assert result["card"] == sample_local_json["submitted_card"]
        assert isinstance(result["trace"], (dict, list))
        assert len(result["trace"]) > 0

    def test_parse_local_forced_submit(self):
        """Test parsing local format with forced_submit flag."""
        from review_app.ingest import parse_local

        payload = {
            "oid": "test123",
            "anchor": {
                "name": "Test Org",
                "address": "Test Address",
                "categories": ["Cat1", "Cat2"]
            },
            "elapsed_s": 100.0,
            "turns": 5,
            "compactions": 0,
            "submit_attempts": 1,
            "critic_events": [
                {
                    "score": 8.5,
                    "verdict": "pass",
                    "missing": [],
                    "wrong": [],
                    "feedback": "Good"
                }
            ],
            "tokens": {"grand_total": 50000},
            "submitted_card": {"_force_submit": True, "data": "test"},
            "trace": [],
            "queries_history": [],
            "visited_urls": [],
            "tool_call_counts": {}
        }

        mtime = datetime(2026, 5, 30, 10, 0, 0)
        source_file = Path("test_data/test123__local.json")

        result = parse_local(payload, source_file, mtime)

        assert result["forced_submit"] is True

    def test_parse_local_empty_critic_events(self):
        """Test parsing local format with empty critic_events."""
        from review_app.ingest import parse_local

        payload = {
            "oid": "test456",
            "anchor": {
                "name": "Test Org",
                "address": "Test Address",
                "categories": ["Cat1"]
            },
            "elapsed_s": 50.0,
            "turns": 3,
            "compactions": 0,
            "submit_attempts": 0,
            "critic_events": [],
            "tokens": {"grand_total": 30000},
            "submitted_card": {"data": "test"},
            "trace": [],
            "queries_history": [],
            "visited_urls": [],
            "tool_call_counts": {}
        }

        mtime = datetime(2026, 5, 30, 10, 0, 0)
        source_file = Path("test_data/test456__local.json")

        result = parse_local(payload, source_file, mtime)

        assert result["critic_score"] is None
        assert result["critic_verdict"] is None


class TestParseAtomic:
    def test_parse_atomic_basic(self, sample_atomic_json):
        """Test basic atomic format parsing with key column assertions."""
        from review_app.ingest import parse_atomic

        mtime = datetime(2026, 5, 30, 10, 4, 45)
        source_file = Path("test_data/1000341388__atomic.json")

        result = parse_atomic(sample_atomic_json, source_file, mtime)

        assert result["model_key"] == "atomic"
        assert result["oid"] == "1000341388"
        assert result["name"] == "Адвокат Фремм"
        assert result["address"] is None
        assert result["categories"] == []
        assert result["critic_score"] == 9.0
        assert result["critic_verdict"] == "pass"
        assert result["turns"] == 8
        assert result["tokens_total"] == 53000
        assert result["compactions"] == 0
        assert result["card"]["what_they_do"] == "Юридическая фирма"
        assert result["tokens"]["grand_total"] == 53000
        assert isinstance(result["critic_events"], list)
        assert len(result["critic_events"]) == 1
        assert result["critic_events"][0]["score"] == 9.0

    def test_parse_atomic_missing_grand_total(self):
        """Test parse_atomic when grand_total is missing (sum prompt + completion)."""
        from review_app.ingest import parse_atomic

        payload = {
            "oid": "test789",
            "title": "Test Company",
            "result": {
                "structured_output": {"what_they_do": "Test"},
                "critic": {
                    "score": 7.0,
                    "verdict": "pass",
                    "missing": [],
                    "wrong": [],
                    "feedback": "OK"
                },
                "stats": {
                    "turns": 5,
                    "elapsed_seconds": 100.0,
                    "compactions": 0,
                    "submit_attempts": 1,
                    "tokens": {
                        "prompt": 20000,
                        "completion": 1000
                    },
                    "tool_calls": {}
                },
                "trace_summary": {}
            }
        }

        mtime = datetime(2026, 5, 30, 10, 0, 0)
        source_file = Path("test_data/test789__atomic.json")

        result = parse_atomic(payload, source_file, mtime)

        assert result["tokens_total"] == 21000  # 20000 + 1000

    def test_parse_atomic_queries_and_urls_empty(self, sample_atomic_json):
        """Test that atomic format has empty queries_history and visited_urls."""
        from review_app.ingest import parse_atomic

        mtime = datetime(2026, 5, 30, 10, 4, 45)
        source_file = Path("test_data/1000341388__atomic.json")

        result = parse_atomic(sample_atomic_json, source_file, mtime)

        assert result["queries_history"] == []
        assert result["visited_urls"] == []


class TestToRow:
    def test_to_row_dispatches_local(self, sample_local_json):
        """Test that to_row correctly dispatches to parse_local."""
        from review_app.ingest import to_row

        mtime = datetime(2026, 5, 30, 10, 0, 0)
        source_file = Path("test_data/1000341388__local.json")

        result = to_row(sample_local_json, source_file, mtime)

        assert result["model_key"] == "local"
        assert result["oid"] == "1000341388"

    def test_to_row_dispatches_atomic(self, sample_atomic_json):
        """Test that to_row correctly dispatches to parse_atomic."""
        from review_app.ingest import to_row

        mtime = datetime(2026, 5, 30, 10, 4, 45)
        source_file = Path("test_data/1000341388__atomic.json")

        result = to_row(sample_atomic_json, source_file, mtime)

        assert result["model_key"] == "atomic"
        assert result["oid"] == "1000341388"

    def test_to_row_unknown_format(self):
        """Test that to_row handles unknown format gracefully."""
        from review_app.ingest import to_row

        payload = {"unknown": "format"}
        mtime = datetime(2026, 5, 30, 10, 0, 0)
        source_file = Path("test_data/unknown.json")

        # Should either raise an error or return a dict with model_key="unknown"
        # depending on implementation; test documents the expected behavior
        try:
            result = to_row(payload, source_file, mtime)
            assert result.get("model_key") == "unknown"
        except ValueError:
            # Also acceptable to raise ValueError for unknown format
            pass
