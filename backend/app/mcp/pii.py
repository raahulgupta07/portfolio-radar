"""Remove personal data from tool answers and audit rows: email addresses and
phone numbers. Names stay, because people need to see who owns a project."""

import re
from typing import Any

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# International numbers (+95 9 123 456 789) and Myanmar mobile numbers (09xxxxxxxx).
# Written so that dates like 2026-10-19 never match.
PHONE = re.compile(r"(?<![\w+])\+\d{1,3}(?:[\s.-]?\d{1,4}){2,5}(?!\w)|(?<!\d)09\d{7,9}(?!\d)")

EMAIL_MASK = "[email removed]"
PHONE_MASK = "[phone removed]"


def redact_text(text: str) -> str:
    return PHONE.sub(PHONE_MASK, EMAIL.sub(EMAIL_MASK, text))


def redact(value: Any) -> Any:
    """Return a copy of value with PII removed from every string inside it."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, tuple):
        return tuple(redact(v) for v in value)
    return value
