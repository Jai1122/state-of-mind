"""Tests for the safe serialization module."""

import dataclasses
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from uuid import UUID

from lgdebug.core.serialization import serialize_state


class Color(Enum):
    RED = "red"
    BLUE = "blue"


@dataclasses.dataclass
class Config:
    model: str = "gpt-4"
    temperature: float = 0.7


class TestSerializeState:
    def test_primitives(self):
        assert serialize_state(None) is None
        assert serialize_state(True) is True
        assert serialize_state(42) == 42
        assert serialize_state(3.14) == 3.14
        assert serialize_state("hello") == "hello"

    def test_dict(self):
        data = {"a": 1, "b": "two", "c": None}
        result = serialize_state(data)
        assert result == {"a": 1, "b": "two", "c": None}

    def test_nested_dict(self):
        data = {"outer": {"inner": {"deep": True}}}
        result = serialize_state(data)
        assert result == {"outer": {"inner": {"deep": True}}}

    def test_list(self):
        data = [1, "two", None, [3, 4]]
        result = serialize_state(data)
        assert result == [1, "two", None, [3, 4]]

    def test_enum(self):
        assert serialize_state(Color.RED) == "red"

    def test_datetime(self):
        dt = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        result = serialize_state(dt)
        assert "2025-01-15" in result

    def test_uuid(self):
        u = UUID("12345678-1234-5678-1234-567812345678")
        result = serialize_state(u)
        assert result == "12345678-1234-5678-1234-567812345678"

    def test_path(self):
        p = Path("/tmp/test.txt")
        result = serialize_state(p)
        assert result == "/tmp/test.txt"

    def test_set(self):
        result = serialize_state({3, 1, 2})
        assert result == [1, 2, 3]

    def test_bytes(self):
        result = serialize_state(b"hello")
        assert "bytes" in result
        assert "5" in result

    def test_dataclass(self):
        cfg = Config(model="claude", temperature=0.5)
        result = serialize_state(cfg)
        assert result == {"model": "claude", "temperature": 0.5}

    def test_circular_reference(self):
        data: dict = {"a": 1}
        data["self"] = data  # type: ignore[assignment]
        result = serialize_state(data)
        assert result["a"] == 1
        assert "circular" in str(result["self"]).lower()

    def test_unserializable_object(self):
        class Weird:
            def __repr__(self):
                return "WeirdObject()"

        result = serialize_state(Weird())
        assert "unserializable" in str(result).lower() or "Weird" in str(result)

    def test_complex_langgraph_state(self):
        """Simulate a realistic LangGraph state structure."""
        state = {
            "query": "What is LangGraph?",
            "messages": [
                {"role": "user", "content": "What is LangGraph?"},
                {"role": "assistant", "content": "LangGraph is..."},
            ],
            "intent": "research",
            "config": Config(model="gpt-4o"),
            "status": Color.BLUE,
            "metadata": {
                "created_at": datetime.now(timezone.utc),
                "tags": {"ai", "graph"},
            },
        }
        result = serialize_state(state)

        assert result["query"] == "What is LangGraph?"
        assert len(result["messages"]) == 2
        assert result["intent"] == "research"
        assert result["config"]["model"] == "gpt-4o"
        assert result["status"] == "blue"
        assert isinstance(result["metadata"]["tags"], list)
