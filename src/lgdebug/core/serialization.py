"""Safe serialization of arbitrary Python state objects.

LangGraph state can contain Pydantic models, dataclasses, sets, bytes,
datetime objects, and arbitrary nested structures. This module converts
any state dict into a JSON-safe dict that can be stored, diffed, and
transmitted over HTTP.

Design decisions:
- We never mutate the original state.
- Circular references are detected and replaced with a sentinel string.
- Unserializable objects fall back to repr() so debugging data is never lost.
- Large binary blobs are truncated with a size annotation.
"""

from __future__ import annotations

import copy
import dataclasses
import json
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID

# Sentinel used to replace circular references.
_CIRCULAR_REF = "<circular reference>"

# Maximum length for repr() fallback strings.
_MAX_REPR_LEN = 500

# Maximum bytes to inline — larger blobs are truncated.
_MAX_BYTES_INLINE = 1024


def safe_deepcopy(obj: Any) -> Any:
    """Deep copy with fallback for objects that don't support copy.

    Some LLM response objects override __copy__ poorly or hold file handles.
    We try copy.deepcopy first, then fall through to serialization round-trip.
    """
    try:
        return copy.deepcopy(obj)
    except Exception:
        # Round-trip through our serializer as a last resort.
        return json.loads(json.dumps(serialize_state(obj)))


def serialize_state(state: Any, *, _seen: set[int] | None = None) -> Any:
    """Convert an arbitrary Python object into a JSON-serializable structure.

    Args:
        state: The object to serialize.
        _seen: Internal set of object ids for circular reference detection.

    Returns:
        A JSON-safe Python object (dict, list, str, int, float, bool, None).
    """
    if _seen is None:
        _seen = set()

    # Primitives — pass through.
    if state is None or isinstance(state, (bool, int, float)):
        return state

    if isinstance(state, str):
        return state

    # Circular reference guard for containers.
    obj_id = id(state)
    if isinstance(state, (dict, list, tuple, set, frozenset)):
        if obj_id in _seen:
            return _CIRCULAR_REF
        _seen = _seen | {obj_id}  # new set — don't pollute siblings

    # Dicts — most common case for LangGraph state.
    if isinstance(state, dict):
        return {str(k): serialize_state(v, _seen=_seen) for k, v in state.items()}

    # Lists / tuples.
    if isinstance(state, (list, tuple)):
        return [serialize_state(item, _seen=_seen) for item in state]

    # Sets / frozensets → sorted lists for deterministic output.
    if isinstance(state, (set, frozenset)):
        try:
            return sorted(serialize_state(item, _seen=_seen) for item in state)
        except TypeError:
            return [serialize_state(item, _seen=_seen) for item in state]

    # Enums.
    if isinstance(state, Enum):
        return state.value

    # Dates / datetimes.
    if isinstance(state, (datetime, date)):
        return state.isoformat()

    # UUIDs.
    if isinstance(state, UUID):
        return str(state)

    # Paths.
    if isinstance(state, Path):
        return str(state)

    # Bytes — inline small, truncate large.
    if isinstance(state, (bytes, bytearray)):
        if len(state) <= _MAX_BYTES_INLINE:
            return f"<bytes len={len(state)}>"
        return f"<bytes len={len(state)} truncated>"

    # Pydantic v2 models.
    if hasattr(state, "model_dump"):
        try:
            return serialize_state(state.model_dump(), _seen=_seen)
        except Exception:
            pass

    # Pydantic v1 models.
    if hasattr(state, "dict") and hasattr(state, "__fields__"):
        try:
            return serialize_state(state.dict(), _seen=_seen)
        except Exception:
            pass

    # Dataclasses.
    if dataclasses.is_dataclass(state) and not isinstance(state, type):
        try:
            return serialize_state(dataclasses.asdict(state), _seen=_seen)
        except Exception:
            pass

    # Objects with __dict__ (generic Python objects).
    if hasattr(state, "__dict__"):
        obj_id = id(state)
        if obj_id in _seen:
            return _CIRCULAR_REF
        _seen = _seen | {obj_id}
        try:
            result = {
                "__type__": type(state).__qualname__,
            }
            result.update(
                {
                    str(k): serialize_state(v, _seen=_seen)
                    for k, v in state.__dict__.items()
                    if not k.startswith("_")
                }
            )
            return result
        except Exception:
            pass

    # Last resort: repr().
    try:
        r = repr(state)
        if len(r) > _MAX_REPR_LEN:
            r = r[:_MAX_REPR_LEN] + "..."
        return f"<unserializable: {r}>"
    except Exception:
        return f"<unserializable: {type(state).__name__}>"
