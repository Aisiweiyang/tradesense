"""Shared LIKE search helpers.

SQLite's LIKE has no default escape character: without an explicit ESCAPE
clause a backslash-escaped pattern silently matches nothing. Always pair
`contains()` with `ilike(pattern, escape=ESCAPE)`.
"""
ESCAPE = "\\"


def contains(q: str) -> str:
    """'Contains q' pattern with % and _ escaped to literals."""
    safe = q.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
    return f"%{safe}%"
