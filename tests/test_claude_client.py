#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for scripts/claude_client.py — timeout parsing and API timeout injection."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from claude_client import _parse_api_timeout  # noqa: E402


class TestParseApiTimeout:
    """Safe parsing of CLAUDE_API_TIMEOUT env value."""

    def test_default_value(self):
        assert _parse_api_timeout("120") == 120.0

    def test_zero_disables(self):
        assert _parse_api_timeout("0") is None

    def test_none_string_disables(self):
        assert _parse_api_timeout("none") is None

    def test_false_string_disables(self):
        assert _parse_api_timeout("false") is None

    def test_off_string_disables(self):
        assert _parse_api_timeout("off") is None

    def test_empty_string_disables(self):
        assert _parse_api_timeout("") is None

    def test_invalid_falls_back_to_default(self):
        assert _parse_api_timeout("abc") == 120.0

    def test_negative_disables(self):
        assert _parse_api_timeout("-5") is None

    def test_float_value(self):
        assert _parse_api_timeout("30.5") == 30.5

    def test_whitespace_trimmed(self):
        assert _parse_api_timeout("  60  ") == 60.0
