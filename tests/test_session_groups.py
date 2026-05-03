"""Session grouping logic tests."""

import pytest
import sys
import os

# Add parent dir to path so we can import from hermes_dashboard
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from time_utils import parse_ago_to_hours as _parse_ago_to_hours


class TestParseAgoToHours:
    """Tests for _parse_ago_to_hours function."""

    def test_just_now(self):
        assert _parse_ago_to_hours("just now") == 0

    def test_minutes_ago(self):
        assert _parse_ago_to_hours("30m ago") == 0  # < 1 hour → 0

    def test_one_hour_ago(self):
        assert _parse_ago_to_hours("1h ago") == 1

    def test_hours_ago(self):
        assert _parse_ago_to_hours("5h ago") == 5

    def test_one_day_ago(self):
        assert _parse_ago_to_hours("1d ago") == 24

    def test_days_ago(self):
        assert _parse_ago_to_hours("3d ago") == 72

    def test_large_days_ago(self):
        assert _parse_ago_to_hours("45d ago") == 1080

    def test_invalid_format(self):
        assert _parse_ago_to_hours("invalid") is None

    def test_empty_string(self):
        assert _parse_ago_to_hours("") is None

    def test_none_input(self):
        assert _parse_ago_to_hours(None) is None

    def test_case_insensitive(self):
        assert _parse_ago_to_hours("2H AGO") == 2

    def test_without_ago_suffix(self):
        assert _parse_ago_to_hours("2h") == 2


from time_utils import SessionGroup, get_group_for_hours, GROUPS


class TestSessionGrouping:
    """Tests for session group classification."""

    def test_groups_defined(self):
        """Verify all expected groups exist."""
        group_keys = [g.key for g in GROUPS]
        assert "__group:today__" in group_keys
        assert "__group:3days__" in group_keys
        assert "__group:7days__" in group_keys
        assert "__group:30days__" in group_keys
        assert "__group:older__" in group_keys
        assert "__group:unknown__" in group_keys

    def test_today_group_expanded_by_default(self):
        today = next(g for g in GROUPS if g.key == "__group:today__")
        assert today.expanded is True

    def test_3days_group_expanded_by_default(self):
        g = next(g for g in GROUPS if g.key == "__group:3days__")
        assert g.expanded is True

    def test_7days_group_collapsed_by_default(self):
        g = next(g for g in GROUPS if g.key == "__group:7days__")
        assert g.expanded is False

    def test_30days_group_collapsed_by_default(self):
        g = next(g for g in GROUPS if g.key == "__group:30days__")
        assert g.expanded is False

    def test_older_group_collapsed_by_default(self):
        g = next(g for g in GROUPS if g.key == "__group:older__")
        assert g.expanded is False

    def test_get_group_today_0h(self):
        g = get_group_for_hours(0)
        assert g.key == "__group:today__"

    def test_get_group_today_23h(self):
        g = get_group_for_hours(23)
        assert g.key == "__group:today__"

    def test_get_group_3days_24h(self):
        g = get_group_for_hours(24)
        assert g.key == "__group:3days__"

    def test_get_group_3days_71h(self):
        g = get_group_for_hours(71)
        assert g.key == "__group:3days__"

    def test_get_group_7days_72h(self):
        g = get_group_for_hours(72)
        assert g.key == "__group:7days__"

    def test_get_group_7days_167h(self):
        g = get_group_for_hours(167)
        assert g.key == "__group:7days__"

    def test_get_group_30days_168h(self):
        g = get_group_for_hours(168)
        assert g.key == "__group:30days__"

    def test_get_group_30days_719h(self):
        g = get_group_for_hours(719)
        assert g.key == "__group:30days__"

    def test_get_group_older_720h(self):
        g = get_group_for_hours(720)
        assert g.key == "__group:older__"

    def test_get_group_older_1000h(self):
        g = get_group_for_hours(1000)
        assert g.key == "__group:older__"

    def test_get_group_unknown_none(self):
        g = get_group_for_hours(None)
        assert g.key == "__group:unknown__"
