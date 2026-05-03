"""Time parsing utilities."""

import re
from dataclasses import dataclass


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


@dataclass
class SessionGroup:
    """Defines a collapsible group of sessions in the sidebar."""
    name: str           # Display name, e.g. "今天（24h 内）"
    key: str            # Unique identifier, e.g. "__group:today__"
    expanded: bool      # Default expanded state
    order: int          # Sort priority (lower = higher)


# Group definitions in display order
GROUPS: list[SessionGroup] = [
    SessionGroup("今天（24h 内）", "__group:today__", True, 1),
    SessionGroup("3 天内", "__group:3days__", True, 2),
    SessionGroup("3-7 天", "__group:7days__", False, 3),
    SessionGroup("7 天-1 个月", "__group:30days__", False, 4),
    SessionGroup("1 个月以上", "__group:older__", False, 5),
    SessionGroup("未知时间", "__group:unknown__", False, 6),
]

# Prefix to identify group header rows in DataTable
GROUP_KEY_PREFIX = "__group:"


def get_group_for_hours(hours: int | None) -> SessionGroup:
    """Return the appropriate group for a given hour count.
    
    None (unparseable) → unknown group.
    """
    if hours is None:
        return GROUPS[-1]  # unknown
    
    if hours < 24:
        return GROUPS[0]   # today
    elif hours < 72:
        return GROUPS[1]   # 3 days
    elif hours < 168:
        return GROUPS[2]   # 7 days
    elif hours < 720:
        return GROUPS[3]   # 30 days
    else:
        return GROUPS[4]   # older
