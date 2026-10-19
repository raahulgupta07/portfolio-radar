"""Field projection: callers pass `fields` to get back only what they need.

Paths are dotted. `[]` walks into a list:
    ["code", "health"]                    on a list of projects, or on one project
    ["projects[].code", "total"]          on {"projects": [...], "total": 10}
    ["owner.name"]                        on nested objects
Unknown paths are ignored, so a projection can only remove data, never add it.
"""

from typing import Any


def project(value: Any, fields: list[str] | None) -> Any:
    if not fields:
        return value
    if isinstance(value, list):
        return [project(item, fields) for item in value]
    if not isinstance(value, dict):
        return value
    out: dict[str, Any] = {}
    for path in fields:
        parts = [p for p in path.strip().split(".") if p]
        if parts:
            _copy_path(value, parts, out)
    return out


def _copy_path(source: dict[str, Any], parts: list[str], target: dict[str, Any]) -> None:
    head, rest = parts[0], parts[1:]
    is_list = head.endswith("[]")
    key = head[:-2] if is_list else head
    if key not in source:
        return
    val = source[key]

    if not rest:
        target[key] = val
        return

    if is_list or isinstance(val, list):
        if not isinstance(val, list):
            return
        existing = target.get(key)
        if not isinstance(existing, list) or len(existing) != len(val):
            existing = [{} if isinstance(item, dict) else item for item in val]
            target[key] = existing
        for i, item in enumerate(val):
            if isinstance(item, dict) and isinstance(existing[i], dict):
                _copy_path(item, rest, existing[i])
        return

    if isinstance(val, dict):
        sub = target.get(key)
        if not isinstance(sub, dict):
            sub = {}
            target[key] = sub
        _copy_path(val, rest, sub)
