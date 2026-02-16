"""Tests for the structural diff engine."""

from lgdebug.core.diff import apply_diff, compute_diff


class TestComputeDiff:
    def test_no_changes(self):
        before = {"a": 1, "b": "hello"}
        after = {"a": 1, "b": "hello"}
        diff = compute_diff(before, after)
        assert diff.is_empty

    def test_value_change(self):
        before = {"intent": "research"}
        after = {"intent": "summarize"}
        diff = compute_diff(before, after)
        assert len(diff.changed) == 1
        assert diff.changed[0]["path"] == "intent"
        assert diff.changed[0]["old_value"] == "research"
        assert diff.changed[0]["new_value"] == "summarize"

    def test_key_added(self):
        before = {"a": 1}
        after = {"a": 1, "b": 2}
        diff = compute_diff(before, after)
        assert len(diff.added) == 1
        assert diff.added[0]["path"] == "b"
        assert diff.added[0]["value"] == 2

    def test_key_removed(self):
        before = {"a": 1, "b": 2}
        after = {"a": 1}
        diff = compute_diff(before, after)
        assert len(diff.removed) == 1
        assert diff.removed[0]["path"] == "b"

    def test_nested_change(self):
        before = {"config": {"model": "gpt-4", "temperature": 0.7}}
        after = {"config": {"model": "gpt-4o", "temperature": 0.7}}
        diff = compute_diff(before, after)
        assert len(diff.changed) == 1
        assert diff.changed[0]["path"] == "config.model"

    def test_list_append(self):
        before = {"messages": [{"role": "user", "content": "hello"}]}
        after = {
            "messages": [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi"},
            ]
        }
        diff = compute_diff(before, after)
        # Should have an added entry for messages[1] and a length change.
        added_paths = {e["path"] for e in diff.added}
        assert "messages[1]" in added_paths
        changed_paths = {e["path"] for e in diff.changed}
        assert "messages.length" in changed_paths

    def test_list_element_change(self):
        before = {"scores": [1, 2, 3]}
        after = {"scores": [1, 99, 3]}
        diff = compute_diff(before, after)
        assert any(e["path"] == "scores[1]" for e in diff.changed)

    def test_ignore_keys(self):
        before = {"data": 1, "timestamp": "old"}
        after = {"data": 2, "timestamp": "new"}
        diff = compute_diff(before, after, ignore_keys=frozenset({"timestamp"}))
        assert len(diff.changed) == 1
        assert diff.changed[0]["path"] == "data"

    def test_deeply_nested(self):
        before = {"a": {"b": {"c": {"d": 1}}}}
        after = {"a": {"b": {"c": {"d": 2}}}}
        diff = compute_diff(before, after)
        assert diff.changed[0]["path"] == "a.b.c.d"


class TestApplyDiff:
    def test_apply_value_change(self):
        state = {"intent": "research", "step": 1}
        diff = compute_diff(state, {"intent": "summarize", "step": 1})
        result = apply_diff(state, diff)
        assert result["intent"] == "summarize"
        assert result["step"] == 1

    def test_apply_addition(self):
        state = {"a": 1}
        diff = compute_diff(state, {"a": 1, "b": 2})
        result = apply_diff(state, diff)
        assert result == {"a": 1, "b": 2}

    def test_apply_removal(self):
        state = {"a": 1, "b": 2}
        diff = compute_diff(state, {"a": 1})
        result = apply_diff(state, diff)
        assert result == {"a": 1}

    def test_apply_does_not_mutate_original(self):
        state = {"a": 1, "nested": {"x": 10}}
        diff = compute_diff(state, {"a": 2, "nested": {"x": 20}})
        result = apply_diff(state, diff)
        assert state["a"] == 1
        assert state["nested"]["x"] == 10
        assert result["a"] == 2
        assert result["nested"]["x"] == 20

    def test_roundtrip_complex(self):
        """Apply a sequence of diffs and verify final state matches."""
        s0 = {"query": "hello", "messages": [], "step": 0}
        s1 = {
            "query": "hello",
            "messages": [{"role": "user", "content": "hello"}],
            "step": 1,
            "intent": "greet",
        }
        s2 = {
            "query": "hello",
            "messages": [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi there"},
            ],
            "step": 2,
            "intent": "greet",
            "response": "hi there",
        }

        d1 = compute_diff(s0, s1)
        d2 = compute_diff(s1, s2)

        reconstructed = apply_diff(apply_diff(s0, d1), d2)
        assert reconstructed == s2
