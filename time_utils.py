"""Time parsing utilities."""

import re


def parse_ago_to_hours(ago: str | None) -> int | None:
    """Parse ago string like '2h ago', '3d ago', 'just now' to hours.

    Returns None if cannot parse.
    Minutes (< 1 hour) return 0.
    """
    if not ago:
        return None

    ago = ago.strip().lower()

    if ago == "just now":
        return 0

    m = re.match(r'^(\d+)\s*([mhd])\s*(ago)?$', ago)
    if not m:
        return None

    value = int(m.group(1))
    unit = m.group(2)

    if unit == 'm':
        return 0
    elif unit == 'h':
        return value
    elif unit == 'd':
        return value * 24
