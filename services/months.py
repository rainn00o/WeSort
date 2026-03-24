from __future__ import annotations

import re
from pathlib import Path


YEAR_MONTH_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^(?P<year>20\d{2})[-_.](?P<month>0?[1-9]|1[0-2])$"),
    re.compile(r"^(?P<year>20\d{2})(?P<month>0[1-9]|1[0-2])$"),
    re.compile(r"^(?P<year>20\d{2})年(?P<month>0?[1-9]|1[0-2])月$"),
)

MONTH_ONLY_PATTERN = re.compile(r"^(?P<month>0?[1-9]|1[0-2])月$")


def normalize_month_component(text: str) -> str:
    value = text.strip()
    if not value:
        return ""
    for pattern in YEAR_MONTH_PATTERNS:
        match = pattern.match(value)
        if match:
            year = int(match.group("year"))
            month = int(match.group("month"))
            return f"{year:04d}-{month:02d}"
    match = MONTH_ONLY_PATTERN.match(value)
    if match:
        month = int(match.group("month"))
        return f"{month:02d}月"
    return ""


def resolve_month_tag(path: Path, root: Path) -> str:
    candidates: list[str] = []
    try:
        relative_parent = path.parent.relative_to(root)
        candidates.extend(relative_parent.parts)
    except ValueError:
        candidates.extend(path.parent.parts)

    # If the selected source directory itself is a month folder like "2025-07",
    # include it as a valid candidate. This is the common case in real usage.
    candidates.append(root.name)

    for part in reversed(candidates):
        normalized = normalize_month_component(part)
        if normalized:
            return normalized
    return ""
