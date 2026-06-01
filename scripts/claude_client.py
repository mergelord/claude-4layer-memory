#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Claude API wrapper with automatic token/cost tracking and optional model routing.

Thin wrapper around ``anthropic.Anthropic.messages.create`` that:

1. Records *exact* API-returned ``usage`` tokens via ``CostTracker``
   (no local estimation — only authoritative values from the response).
2. Exposes a ``route_and_complete`` helper that auto-selects the cheapest
   capable model based on task complexity heuristics.
3. Is fully mockable: inject a fake ``client`` and/or ``cost_tracker``
   and the wrapper works without the real Anthropic SDK.

Usage::

    from claude_client import TrackedClaudeClient

    client = TrackedClaudeClient()

    # Simple call — all kwargs forwarded to messages.create
    msg = client.messages_create(
        model="claude-haiku-4",
        max_tokens=512,
        messages=[{"role": "user", "content": "Hello"}],
        operation_type="search_answer",
    )

    # Auto-routing shortcut — model selected by complexity
    msg = client.route_and_complete(
        prompt="Refactor the 900-line indexing module",
        max_tokens=4096,
    )
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

# --- import CostTracker from wherever it lives --------------------------------
# The wrapper may be imported from the repo root, from scripts/, or from a
# deployed ~/.claude/scripts/ layout.  Try the common layouts in order.
try:
    from cost_tracker import CostTracker  # same-directory (e.g. scripts/)
except ImportError:
    try:
        # pylint: disable=import-outside-toplevel
        _SCRIPTS_DIR = str(Path(__file__).resolve().parent / "scripts")
        if _SCRIPTS_DIR not in sys.path:
            sys.path.insert(0, _SCRIPTS_DIR)
        from cost_tracker import CostTracker  # type: ignore[no-redef]
    except ImportError:
        # Deployed layout: scripts are at ../scripts relative to the wrapper
        _DEPLOY_DIR = str(Path(__file__).resolve().parent.parent / "scripts")
        if _DEPLOY_DIR not in sys.path:
            sys.path.insert(0, _DEPLOY_DIR)
        from cost_tracker import CostTracker  # type: ignore[no-redef]


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Canonical operation taxonomy (used by the cost tracker and for analytics)
# ---------------------------------------------------------------------------

CLAUDE_OPERATION_TYPES = {
    "summarize":        "claude.summarize",
    "code_review":      "claude.code_review",
    "memory_compact":   "claude.memory_compact",
    "search_answer":    "claude.search_answer",
    "refactor":         "claude.refactor",
    "issue_analysis":   "claude.issue_analysis",
    # Model-routing / escalation operations
    "deep_reason":      "claude.delegate",       # Haiku escalated to Sonnet/Opus
    "architect":        "claude.architect",       # Architecture-level reasoning
    "generate_code":    "claude.generate_code",   # Greenfield code generation
    "generic":          "claude.message",
}


def claude_operation(name: str) -> str:
    """Return the canonical Claude cost operation name for a task alias."""
    return CLAUDE_OPERATION_TYPES.get(name, name)


# ---------------------------------------------------------------------------
# Complexity heuristics for model routing (zero-cost, no LLM calls)
# ---------------------------------------------------------------------------

# Patterns that strongly suggest a complex task (weight +1 each).
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

# Patterns that suggest a task is simple enough for Haiku (weight −1 each).
_SIMPLE_HEURISTICS = [
    "what is", "explain", "show me", "find", "list",
    "что такое", "объясни", "покажи", "найди", "список",
    "read", "search", "grep",
    "format", "translate", "convert",
    "comment", "docstring",
    "summary", "summarize",
]

# Tasks that should always escalate (never stay on Haiku).
_ALWAYS_ESCALATE = [
    "refactor", "architect", "deep_reason", "generate_code",
]


def _estimate_complexity(
    prompt: str,
    context_len: int = 0,
    operation_type: str = "generic",
) -> str:
    """Return the recommended model name based on cheap heuristics.

    Does **not** call any LLM — pure string analysis, so it is safe to
    run before every API call without adding latency or cost.

    Returns one of ``"claude-haiku-4"``, ``"claude-sonnet-4"``, or
    ``"claude-opus-4"``.
    """
    # --- hard overrides -------------------------------------------------------
    if operation_type in _ALWAYS_ESCALATE:
        return "claude-opus-4"

    # --- score-based ----------------------------------------------------------
    query_lower = prompt.lower()
    score = 0

    # 1. Context size
    if context_len > 80_000:
        score += 4
    elif context_len > 30_000:
        score += 2
    elif context_len > 8_000:
        score += 1

    # 2. Prompt length
    prompt_tokens_approx = len(prompt.split())
    if prompt_tokens_approx > 500:
        score += 2
    elif prompt_tokens_approx > 200:
        score += 1

    # 3. Keyword heuristics
    for kw in _COMPLEX_HEURISTICS:
        if kw in query_lower:
            score += 1
    for kw in _SIMPLE_HEURISTICS:
        if kw in query_lower:
            score -= 1

    # 4. Structural signals
    if "```" in prompt and prompt.count("```") >= 4:
        score += 1  # Multiple code blocks
    if prompt.count("\n") > 40:
        score += 1  # Very long, multi-line prompt

    # --- decision -------------------------------------------------------------
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


class TrackedClaudeClient:
    """Thin Anthropic Messages API wrapper that persists exact usage tokens.

    Every successful ``messages.create`` call is automatically recorded by
    the attached ``CostTracker``.  The wrapper does **not** modify the
    response — your code can use it exactly like a raw Anthropic client.
    """

    def __init__(
        self,
        client: Any | None = None,
        cost_tracker: CostTracker | None = None,
        *,
        api_key: str | None = None,
    ) -> None:
        """
        Args:
            client: Pre-built ``anthropic.Anthropic`` instance (for testing
                or custom config).  If ``None``, one is created lazily.
            cost_tracker: Pre-built ``CostTracker``.  If ``None``, a default
                tracker is created.
            api_key: Override for ``ANTHROPIC_API_KEY`` (only used when
                *client* is also ``None``).
        """
        self.client = (
            client if client is not None
            else self._build_anthropic_client(api_key)
        )
        self.cost_tracker = (
            cost_tracker if cost_tracker is not None
            else CostTracker()
        )

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_anthropic_client(api_key: str | None = None) -> Any:
        """Create the real Anthropic client lazily."""
        try:
            import anthropic  # pylint: disable=import-outside-toplevel
        except ImportError as exc:
            raise RuntimeError(
                "anthropic package is required for real Claude API calls. "
                "Install project requirements or pass a preconfigured client."
            ) from exc

        resolved_api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if resolved_api_key:
            return anthropic.Anthropic(api_key=resolved_api_key)
        return anthropic.Anthropic()

    # ------------------------------------------------------------------
    # Metadata helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_cost_metadata(
        operation_type: str,
        cost_metadata: Optional[dict[str, Any]],
        routing_info: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Ensure every tracked call has ``task``, ``provider``, and optional routing keys."""
        metadata = dict(cost_metadata or {})
        metadata.setdefault("task", operation_type)
        metadata.setdefault("provider", "anthropic")
        if routing_info:
            metadata.setdefault("routing", routing_info)
        return metadata

    # ------------------------------------------------------------------
    # Core API calls
    # ------------------------------------------------------------------

    def messages_create(
        self,
        *,
        operation_type: str = CLAUDE_OPERATION_TYPES["generic"],
        cost_metadata: Optional[dict[str, Any]] = None,
        routing_info: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        """Call ``client.messages.create(**kwargs)`` and track usage.

        Args:
            operation_type: Cost-tracker operation name (see
                ``CLAUDE_OPERATION_TYPES``).
            cost_metadata: Optional JSON-compatible dict saved with the
                cost row (e.g. ``{"project": "claude-4layer-memory"}``).
            routing_info: Optional dict describing routing decision
                (e.g. ``{"complexity_score": 3, "auto_routed": True}``).
            **kwargs: Passed unchanged to ``Anthropic.messages.create``.

        Returns:
            The original Anthropic message response (unchanged).

        Raises:
            The underlying API exception after exhausting retries.
        """
        canonical_operation = claude_operation(operation_type)
        metadata = self._build_cost_metadata(
            canonical_operation, cost_metadata, routing_info,
        )

        last_exc: Optional[Exception] = None
        for attempt in range(1, _API_MAX_RETRIES + 1):
            try:
                message = self.client.messages.create(**kwargs)
            except Exception as exc:
                last_exc = exc
                status = getattr(exc, "status_code", None)
                if status in _API_RETRY_CODES and attempt < _API_MAX_RETRIES:
                    delay = _API_RETRY_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        "Claude API call failed (attempt %d/%d, status %s): %s. "
                        "Retrying in %.1fs...",
                        attempt, _API_MAX_RETRIES, status, exc, delay,
                    )
                    time.sleep(delay)
                    continue
                logger.error(
                    "Claude API call failed: operation=%s model=%s error=%s",
                    canonical_operation, kwargs.get("model", "?"), exc,
                )
                raise

            # Success — track exact usage
            try:
                self.cost_tracker.track_claude_message(
                    canonical_operation,
                    message,
                    metadata=metadata,
                )
            except Exception as track_exc:
                # Cost tracking must never break the caller.
                logger.warning("Cost tracking failed (response still returned): %s", track_exc)
            return message

        # Should be unreachable, but guard against an empty retry loop.
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
        """Convenience wrapper for a single user-message completion.

        Builds a ``messages`` list automatically.  All other kwargs are
        forwarded to :meth:`messages_create`.
        """
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

    # ------------------------------------------------------------------
    # Model routing convenience API
    # ------------------------------------------------------------------

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
        """Auto-select model by task complexity, then complete.

        Uses cheap heuristics (no LLM call) to pick the cheapest capable
        model.  Override with ``force_model`` to bypass routing.

        Args:
            prompt: The user prompt.
            operation_type: Cost-tracker operation name.
            context_tokens: Approximate context length in tokens (used
                by the complexity scorer).  Omit / pass 0 if unknown.
            cost_metadata: Optional JSON metadata.
            max_tokens: Passed to the API.
            force_model: If set, skip routing and use this model.
            **kwargs: Passed to :meth:`complete`.

        Returns:
            The Anthropic message response.
        """
        if force_model:
            chosen_model = force_model
            routing_info = {"method": "forced", "model": chosen_model}
        else:
            chosen_model = _estimate_complexity(
                prompt,
                context_len=context_tokens,
                operation_type=operation_type,
            )
            routing_info = {
                "method": "auto",
                "model": chosen_model,
                "context_tokens": context_tokens,
            }

        logger.info(
            "Routing: op=%s model=%s (prompt_len=%d, ctx=%d)",
            operation_type, chosen_model, len(prompt.split()), context_tokens,
        )

        return self.complete(
            prompt=prompt,
            model=chosen_model,
            max_tokens=max_tokens,
            operation_type=operation_type,
            cost_metadata=cost_metadata,
            routing_info=routing_info,
            **kwargs,
        )


# ---------------------------------------------------------------------------
# Module-level factory (kept for backward compatibility)
# ---------------------------------------------------------------------------

def create_tracked_claude_client(
    *,
    client: Any | None = None,
    cost_tracker: CostTracker | None = None,
    api_key: str | None = None,
) -> TrackedClaudeClient:
    """Factory for callers that prefer function-style construction."""
    return TrackedClaudeClient(
        client=client,
        cost_tracker=cost_tracker,
        api_key=api_key,
    )
