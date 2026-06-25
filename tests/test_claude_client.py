#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for scripts/claude_client.py — timeout parsing and API timeout injection."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from claude_client import _parse_api_timeout, TrackedClaudeClient  # noqa: E402


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


class TestTimeoutInjection:
    """Verify that messages_create injects a per-request timeout."""

    def _make_client(self) -> TrackedClaudeClient:
        """Build a TrackedClaudeClient with a mock Anthropic client + tracker."""
        mock_api = MagicMock()
        fake_message = MagicMock()
        fake_message.usage = MagicMock(input_tokens=10, output_tokens=5)
        mock_api.messages.create.return_value = fake_message
        tracker = MagicMock()
        return TrackedClaudeClient(client=mock_api, cost_tracker=tracker)

    @patch("claude_client._API_TIMEOUT", 120.0)
    def test_timeout_injected_when_absent(self):
        """When kwargs lacks 'timeout', messages_create should add one."""
        client = self._make_client()
        client.messages_create(model="test-model", max_tokens=10, messages=[])
        call_kwargs = client.client.messages.create.call_args
        assert "timeout" in call_kwargs.kwargs
        assert call_kwargs.kwargs["timeout"] is not None
        assert call_kwargs.kwargs["timeout"] > 0

    def test_caller_timeout_respected(self):
        """When kwargs already has 'timeout', messages_create must not override."""
        client = self._make_client()
        client.messages_create(
            model="test-model", max_tokens=10, messages=[], timeout=300.0
        )
        call_kwargs = client.client.messages.create.call_args
        assert call_kwargs.kwargs["timeout"] == 300.0

    @patch("claude_client._API_TIMEOUT", None)
    def test_no_timeout_when_disabled(self):
        """When _API_TIMEOUT is None, no timeout key is added to kwargs."""
        client = self._make_client()
        client.messages_create(model="test-model", max_tokens=10, messages=[])
        call_kwargs = client.client.messages.create.call_args
        assert "timeout" not in call_kwargs.kwargs

    @patch("claude_client._API_TIMEOUT", 120.0)
    def test_timeout_is_not_positional(self):
        """timeout must be passed as a keyword arg, not positional."""
        client = self._make_client()
        client.messages_create(model="test-model", max_tokens=10, messages=[])
        call_kwargs = client.client.messages.create.call_args
        # call_args.kwargs should contain it, not call_args.args
        assert "timeout" in call_kwargs.kwargs
