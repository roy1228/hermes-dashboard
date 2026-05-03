"""Session grouping logic tests."""

import pytest
import sys
import os

# Add parent dir to path so we can import from hermes_dashboard
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hermes_dashboard import _parse_ago_to_hours


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
