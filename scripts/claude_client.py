#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Claude API wrapper with automatic token/cost tracking and model routing.

Thin wrapper around ``anthropic.Anthropic.messages.create`` that:

1. Records *exact* API-returned ``usage`` tokens via ``CostTracker``
2. Exposes ``route_and_complete`` for auto-selecting the cheapest capable model
3. Supports custom ``base_url`` for gateways/proxies (auto-detects ANTHROPIC_BASE_URL)
4. Fully mockable for testing
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

try:
    from cost_tracker import CostTracker
except ImportError:
    try:
        _SCRIPTS_DIR = str(Path(__file__).resolve().parent / "scripts")
        if _SCRIPTS_DIR not in sys.path:
            sys.path.insert(0, _SCRIPTS_DIR)
        from cost_tracker import CostTracker  # type: ignore[no-redef]
    except ImportError:
        _DEPLOY_DIR = str(Path(__file__).resolve().parent.parent / "scripts")
        if _DEPLOY_DIR not in sys.path:
            sys.path.insert(0, _DEPLOY_DIR)
        from cost_tracker import CostTracker  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Operation taxonomy
# ---------------------------------------------------------------------------

CLAUDE_OPERATION_TYPES = {
    "summarize":        "claude.summarize",
    "code_review":      "claude.code_review",
    "memory_compact":   "claude.memory_compact",
    "search_answer":    "claude.search_answer",
    "refactor":         "claude.refactor",
    "issue_analysis":   "claude.issue_analysis",
    "deep_reason":      "claude.delegate",
    "smart_complete":   "claude.smart_complete",
    "architect":        "claude.architect",
    "generate_code":    "claude.generate_code",
    "generic":          "claude.message",
}


def claude_operation(name: str) -> str:
    return CLAUDE_OPERATION_TYPES.get(name, name)


# ---------------------------------------------------------------------------
# Complexity heuristics — PUBLIC (used by routing_learner.py)
# ---------------------------------------------------------------------------

_COMPLEX_HEURISTICS = [
    "refactor", "refactoring", "рефакторинг",
    "architecture", "architect", "архитектур",
    "design pattern", "design system",
    "migrate", "миграци",
    "implement from scratch", "напиши с нуля",
    "debug", "trace", "root cause",
    "optimize", "оптимизируй",
    "security audit", "vulnerability",
]

_SIMPLE_HEURISTICS = [
    "what is", "explain", "show me", "find", "list",
    "что такое", "объясни", "покажи", "найди", "список",
    "read", "search", "grep",
    "format", "translate", "convert",
    "comment", "docstring",
    "summary", "summarize",
]

_ALWAYS_ESCALATE = [
    "refactor", "architect", "deep_reason", "generate_code",
]


def approx_tokens(text: str) -> int:
    """Estimate token count from text. ~1.3 tokens per word for English,
    more for code/Cyrillic. Simple heuristic: words * 1.3."""
    return int(len(text.split()) * 1.3)


def estimate_complexity(
    prompt: str,
    context_len: int = 0,
    operation_type: str = "generic",
) -> str:
    """Return recommended model: 'claude-haiku-4'/'claude-sonnet-4'/'claude-opus-4'.

    Zero-cost heuristics — no LLM calls.  This is the PUBLIC entry point
    used by routing_learner.py and MCP tools.
    """
    if operation_type in _ALWAYS_ESCALATE:
        return "claude-opus-4"

    query_lower = prompt.lower()
    score = 0

    if context_len > 80_000:
        score += 4
    elif context_len > 30_000:
        score += 2
    elif context_len > 8_000:
        score += 1

    prompt_tokens_approx = approx_tokens(prompt)
    if prompt_tokens_approx > 500:
        score += 2
    elif prompt_tokens_approx > 200:
        score += 1

    for kw in _COMPLEX_HEURISTICS:
        if kw in query_lower:
            score += 1
    for kw in _SIMPLE_HEURISTICS:
        if kw in query_lower:
            score -= 1

    if "```" in prompt and prompt.count("```") >= 4:
        score += 1
    if prompt.count("\n") > 40:
        score += 1

    if score >= 4:
        return "claude-opus-4"
    if score >= 2:
        return "claude-sonnet-4"
    return "claude-haiku-4"


# ---------------------------------------------------------------------------
# Tracked client
# ---------------------------------------------------------------------------

_API_RETRY_CODES = {429, 502, 503, 504}
_API_MAX_RETRIES = 3
_API_RETRY_DELAY = 1.0


def _parse_api_timeout(raw: str) -> float | None:
    """Parse CLAUDE_API_TIMEOUT env value safely.

    Returns the timeout in seconds, or ``None`` to disable.
    Invalid values fall back to the default (120.0) with a warning.
    """
    value = raw.strip().lower()
    if value in ("", "0", "none", "false", "off"):
        return None
    try:
        timeout = float(value)
    except ValueError:
        logger.warning("Invalid CLAUDE_API_TIMEOUT=%r, using default 120s", raw)
        return 120.0
    if timeout <= 0:
        return None
    return timeout


# Hard wall-clock cap on a single messages.create call. Without it a
# hung socket (gateway stall, DNS black-hole, idle keep-alive drop) can
# block the caller forever — the SDK's retry logic only fires on raised
# errors, never on a request that never returns. Configurable via env so
# long-running generations can opt out. ``None``/``0`` disables it.
_API_TIMEOUT = _parse_api_timeout(os.getenv("CLAUDE_API_TIMEOUT", "120"))


class TrackedClaudeClient:
    """Thin Anthropic Messages API wrapper that persists exact usage tokens."""

    def __init__(
        self,
        client: Any | None = None,
        cost_tracker: CostTracker | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.client = (
            client if client is not None
            else self._build_anthropic_client(api_key, base_url)
        )
        self.cost_tracker = (
            cost_tracker if cost_tracker is not None
            else CostTracker()
        )

    @staticmethod
    def _build_anthropic_client(
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> Any:
        try:
            import anthropic  # pylint: disable=import-outside-toplevel
        except ImportError as exc:
            raise RuntimeError(
                "anthropic package is required. Install project requirements."
            ) from exc

        resolved_api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        resolved_base_url = (
            base_url
            or os.environ.get("ANTHROPIC_BASE_URL")
        )

        kwargs: dict[str, Any] = {}
        if resolved_api_key:
            kwargs["api_key"] = resolved_api_key
        if resolved_base_url:
            kwargs["base_url"] = resolved_base_url

        return anthropic.Anthropic(**kwargs)

    @staticmethod
    def _build_cost_metadata(
        operation_type: str,
        cost_metadata: Optional[dict[str, Any]],
        routing_info: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        metadata = dict(cost_metadata or {})
        metadata.setdefault("task", operation_type)
        metadata.setdefault("provider", "anthropic")
        if routing_info:
            metadata.setdefault("routing", routing_info)
        return metadata

    def messages_create(
        self,
        *,
        operation_type: str = CLAUDE_OPERATION_TYPES["generic"],
        cost_metadata: Optional[dict[str, Any]] = None,
        routing_info: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        canonical_operation = claude_operation(operation_type)
        metadata = self._build_cost_metadata(
            canonical_operation, cost_metadata, routing_info,
        )

        last_exc: Optional[Exception] = None
        # Inject a per-request timeout only when the caller hasn't set
        # one explicitly. ``timeout`` may already be present in kwargs
        # (e.g. via route_and_complete passthrough) — respect it.
        if "timeout" not in kwargs and _API_TIMEOUT is not None:
            kwargs = {"timeout": _API_TIMEOUT, **kwargs}
        for attempt in range(1, _API_MAX_RETRIES + 1):
            try:
                message = self.client.messages.create(**kwargs)
            except Exception as exc:
                last_exc = exc
                status = getattr(exc, "status_code", None)
                if status in _API_RETRY_CODES and attempt < _API_MAX_RETRIES:
                    delay = _API_RETRY_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        "API call failed (attempt %d/%d, %s). Retrying in %.1fs...",
                        attempt, _API_MAX_RETRIES, status, delay,
                    )
                    time.sleep(delay)
                    continue
                logger.error(
                    "API call failed: op=%s model=%s error=%s",
                    canonical_operation, kwargs.get("model", "?"), exc,
                )
                raise

            try:
                self.cost_tracker.track_claude_message(
                    canonical_operation, message, metadata=metadata,
                )
            except Exception as track_exc:
                logger.warning("Cost tracking failed: %s", track_exc)
            return message

        assert last_exc is not None  # nosec
        raise last_exc  # type: ignore[misc]

    def complete(
        self,
        prompt: str,
        *,
        model: str = "claude-sonnet-4",
        max_tokens: int = 1024,
        operation_type: str = CLAUDE_OPERATION_TYPES["generic"],
        cost_metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        messages = kwargs.pop("messages", None)
        if messages is None:
            messages = [{"role": "user", "content": prompt}]
        return self.messages_create(
            operation_type=operation_type,
            cost_metadata=cost_metadata,
            model=model,
            max_tokens=max_tokens,
            messages=messages,
            **kwargs,
        )

    def route_and_complete(
        self,
        prompt: str,
        *,
        operation_type: str = CLAUDE_OPERATION_TYPES["generic"],
        context_tokens: int = 0,
        cost_metadata: Optional[dict[str, Any]] = None,
        max_tokens: int = 4096,
        force_model: Optional[str] = None,
        **kwargs: Any,
    ) -> Any:
        if force_model:
            chosen_model = force_model
            routing_info: dict[str, Any] = {"method": "forced", "model": chosen_model}
        else:
            chosen_model = estimate_complexity(
                prompt, context_len=context_tokens, operation_type=operation_type,
            )
            routing_info = {
                "method": "auto", "model": chosen_model, "context_tokens": context_tokens,
            }

        logger.info(
            "Routing: op=%s model=%s (prompt_len=%d, ctx=%d)",
            operation_type, chosen_model, len(prompt.split()), context_tokens,
        )

        return self.complete(
            prompt=prompt, model=chosen_model, max_tokens=max_tokens,
            operation_type=operation_type, cost_metadata=cost_metadata,
            routing_info=routing_info, **kwargs,
        )


def create_tracked_claude_client(
    *,
    client: Any | None = None,
    cost_tracker: CostTracker | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> TrackedClaudeClient:
    return TrackedClaudeClient(
        client=client, cost_tracker=cost_tracker,
        api_key=api_key, base_url=base_url,
    )
