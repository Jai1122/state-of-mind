"""Structural diff engine for nested state objects.

Computes a minimal, human-readable diff between two serialized state snapshots.

Algorithm:
    Recursive descent through both trees simultaneously.
    - Dict keys: compute set difference for added/removed, recurse for shared.
    - Lists: element-wise comparison up to min length, then added/removed tail.
    - Scalars: direct equality check.

The output is a StateDiff containing three lists:
    changed: [{path, old_value, new_value}]
    added:   [{path, value}]
    removed: [{path, value}]

Paths use dot notation with bracket indexing for lists:
    "messages[2].content"
    "config.model_name"

Performance: O(n) where n = total number of leaf values across both trees.
For typical LangGraph state (< 100 keys), this runs in < 1ms.
"""

from __future__ import annotations

from typing import Any

from lgdebug.core.models import StateDiff


def compute_diff(
    before: dict[str, Any],
    after: dict[str, Any],
    *,
    ignore_keys: frozenset[str] | None = None,
) -> StateDiff:
    """Compute a structural diff between two state dicts.

    Args:
        before: Serialized state before node execution.
        after: Serialized state after node execution.
        ignore_keys: Top-level keys to exclude from diff computation.

    Returns:
        A StateDiff with changed, added, and removed entries.
    """
    if ignore_keys is None:
        ignore_keys = frozenset()

    diff = StateDiff()
    _diff_dicts(before, after, path="", diff=diff, ignore_keys=ignore_keys)
    return diff


def _diff_dicts(
    before: dict[str, Any],
    after: dict[str, Any],
    *,
    path: str,
    diff: StateDiff,
    ignore_keys: frozenset[str],
) -> None:
    """Compare two dicts recursively."""
    before_keys = set(before.keys())
    after_keys = set(after.keys())

    # Filter ignored keys only at the top level (path == "").
    if not path:
        before_keys -= ignore_keys
        after_keys -= ignore_keys

    # Added keys.
    for key in sorted(after_keys - before_keys):
        full_path = _join_path(path, key)
        diff.added.append({"path": full_path, "value": after[key]})

    # Removed keys.
    for key in sorted(before_keys - after_keys):
        full_path = _join_path(path, key)
        diff.removed.append({"path": full_path, "value": before[key]})

    # Shared keys — recurse.
    for key in sorted(before_keys & after_keys):
        full_path = _join_path(path, key)
        _diff_values(before[key], after[key], path=full_path, diff=diff, ignore_keys=ignore_keys)


def _diff_values(
    before: Any,
    after: Any,
    *,
    path: str,
    diff: StateDiff,
    ignore_keys: frozenset[str],
) -> None:
    """Compare two values, dispatching by type."""
    # Same type — recurse into containers.
    if isinstance(before, dict) and isinstance(after, dict):
        _diff_dicts(before, after, path=path, diff=diff, ignore_keys=ignore_keys)
        return

    if isinstance(before, list) and isinstance(after, list):
        _diff_lists(before, after, path=path, diff=diff, ignore_keys=ignore_keys)
        return

    # Scalar comparison.
    if before != after:
        diff.changed.append({"path": path, "old_value": before, "new_value": after})


def _diff_lists(
    before: list[Any],
    after: list[Any],
    *,
    path: str,
    diff: StateDiff,
    ignore_keys: frozenset[str],
) -> None:
    """Compare two lists element-wise.

    For lists of different lengths:
    - Compare shared prefix element-wise.
    - Tail elements in `after` are "added".
    - Tail elements in `before` are "removed".

    This is intentionally simple. We do NOT do LCS / Myers diff on lists
    because LangGraph state lists (e.g. messages) are append-only in practice,
    and element-wise comparison is O(n) vs O(n^2) for LCS.
    """
    min_len = min(len(before), len(after))

    # Compare shared prefix.
    for i in range(min_len):
        item_path = f"{path}[{i}]"
        _diff_values(before[i], after[i], path=item_path, diff=diff, ignore_keys=ignore_keys)

    # Added tail.
    for i in range(min_len, len(after)):
        item_path = f"{path}[{i}]"
        diff.added.append({"path": item_path, "value": after[i]})

    # Removed tail.
    for i in range(min_len, len(before)):
        item_path = f"{path}[{i}]"
        diff.removed.append({"path": item_path, "value": before[i]})

    # Also record length change as a top-level signal if lengths differ.
    if len(before) != len(after):
        diff.changed.append({
            "path": f"{path}.length",
            "old_value": len(before),
            "new_value": len(after),
        })


def _join_path(parent: str, key: str) -> str:
    """Build a dotted path string."""
    if not parent:
        return key
    return f"{parent}.{key}"


def apply_diff(state: dict[str, Any], diff: StateDiff) -> dict[str, Any]:
    """Apply a StateDiff to a state dict to produce the next state.

    This is used by the replay engine to reconstruct state from
    checkpoint + sequence of diffs, WITHOUT re-executing the graph.

    Args:
        state: The base state (will NOT be mutated — returns a new dict).
        diff: The diff to apply.

    Returns:
        A new state dict with the diff applied.
    """
    import copy

    result = copy.deepcopy(state)

    # Apply removals first (so paths are still valid).
    for entry in reversed(diff.removed):
        path = entry["path"]
        _delete_at_path(result, path)

    # Apply additions.
    for entry in diff.added:
        path = entry["path"]
        _set_at_path(result, path, copy.deepcopy(entry["value"]))

    # Apply changes (skip synthetic .length entries).
    for entry in diff.changed:
        path = entry["path"]
        if path.endswith(".length"):
            continue  # synthetic — list already resized by add/remove
        _set_at_path(result, path, copy.deepcopy(entry["new_value"]))

    return result


def _parse_path(path: str) -> list[str | int]:
    """Parse "foo.bar[2].baz" into ["foo", "bar", 2, "baz"]."""
    segments: list[str | int] = []
    current = ""
    i = 0
    while i < len(path):
        ch = path[i]
        if ch == ".":
            if current:
                segments.append(current)
                current = ""
        elif ch == "[":
            if current:
                segments.append(current)
                current = ""
            # Read index.
            i += 1
            idx_str = ""
            while i < len(path) and path[i] != "]":
                idx_str += path[i]
                i += 1
            segments.append(int(idx_str))
        else:
            current += ch
        i += 1
    if current:
        segments.append(current)
    return segments


def _get_at_path(obj: Any, path: str) -> Any:
    """Navigate to a value in a nested structure using a dotted/bracketed path."""
    segments = _parse_path(path)
    current = obj
    for seg in segments:
        if isinstance(seg, int):
            current = current[seg]
        else:
            current = current[seg]
    return current


def _set_at_path(obj: Any, path: str, value: Any) -> None:
    """Set a value in a nested structure, creating intermediate dicts as needed."""
    segments = _parse_path(path)
    current = obj
    for seg in segments[:-1]:
        if isinstance(seg, int):
            # Extend list if needed.
            while len(current) <= seg:
                current.append({})
            current = current[seg]
        else:
            if seg not in current:
                current[seg] = {}
            current = current[seg]

    last = segments[-1]
    if isinstance(last, int):
        while len(current) <= last:
            current.append(None)
        current[last] = value
    else:
        current[last] = value


def _delete_at_path(obj: Any, path: str) -> None:
    """Delete a value at a path. Silently ignores missing paths."""
    segments = _parse_path(path)
    current = obj
    try:
        for seg in segments[:-1]:
            if isinstance(seg, int):
                current = current[seg]
            else:
                current = current[seg]
        last = segments[-1]
        if isinstance(last, int) and isinstance(current, list):
            if last < len(current):
                current.pop(last)
        elif isinstance(current, dict) and last in current:
            del current[last]
    except (KeyError, IndexError, TypeError):
        pass  # Path doesn't exist — safe to ignore during replay.
