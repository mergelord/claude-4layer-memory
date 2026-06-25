import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from claude_client import estimate_complexity, approx_tokens


def test_approx_tokens():
    """Verify that approx_tokens correctly applies the 1.3 multiplier."""
    # 10 words * 1.3 = 13 tokens
    text = "word " * 10
    assert approx_tokens(text) == 13


def test_estimate_complexity_context_thresholds():
    """Verify that context_len correctly escalates the model."""
    # Neutral prompt so it doesn't auto-escalate
    neutral_prompt = "do a generic task"  # score 0
    
    # 0 context -> score = 0 -> Haiku
    assert estimate_complexity(neutral_prompt, context_len=0) == "claude-haiku-4"
    
    # > 8000 context -> +1 -> score 1 -> Haiku
    assert estimate_complexity(neutral_prompt, context_len=8001) == "claude-haiku-4"

    # > 30000 context -> +2 -> score 2 -> Sonnet
    assert estimate_complexity(neutral_prompt, context_len=30001) == "claude-sonnet-4"

    # > 80000 context -> +4 -> score 4 -> Opus
    assert estimate_complexity(neutral_prompt, context_len=80001) == "claude-opus-4"


def test_estimate_complexity_boundary_context_thresholds():
    """At exactly 8000/30000/80000 context, the > threshold must NOT fire.

    estimate_complexity uses strict > comparisons:
        context_len > 80_000 → +4
        context_len > 30_000 → +2
        context_len > 8_000  → +1
    So exactly 8000/30000/80000 should get +0 (Haiku with neutral prompt).
    """
    neutral_prompt = "do a generic task"  # score 0

    # Exactly 8000 — should NOT trigger the >8000 threshold
    assert estimate_complexity(neutral_prompt, context_len=8000) == "claude-haiku-4"

    # Exactly 30000 — should NOT trigger the >30000 threshold
    assert estimate_complexity(neutral_prompt, context_len=30000) == "claude-haiku-4"

    # Exactly 80000 — should NOT trigger the >80000 threshold
    assert estimate_complexity(neutral_prompt, context_len=80000) == "claude-sonnet-4"


def test_estimate_complexity_prompt_tokens():
    """Verify that prompt_tokens_approx correctly escalates the model."""
    # 160 words * 1.3 = 208 tokens -> score +1
    long_prompt = "word " * 160
    assert estimate_complexity(long_prompt, context_len=0) == "claude-haiku-4"

    # 400 words * 1.3 = 520 tokens -> score +2
    very_long_prompt = "word " * 400
    assert estimate_complexity(very_long_prompt, context_len=0) == "claude-sonnet-4"


def test_estimate_complexity_boundary_prompt_tokens():
    """At exactly 200 and 500 prompt tokens, the > threshold must NOT fire.

    Heuristics use strict >:
        prompt_tokens_approx > 500 → +2
        prompt_tokens_approx > 200 → +1
    So exactly 200 tokens → +0 (Haiku), exactly 500 tokens → +1 (Haiku).
    """
    neutral_score_0 = "do a generic task"

    # 200 tokens exactly: 200 / 1.3 ≈ 153.8 words → 153 words → 198 tokens (under)
    # Use 154 words → 200.2 → int(200.2) = 200 tokens exactly
    prompt_200_tokens = "word " * 154  # 154 * 1.3 = 200.2 → int = 200
    assert approx_tokens(prompt_200_tokens) == 200
    assert estimate_complexity(prompt_200_tokens, context_len=0) == "claude-haiku-4"

    # 500 tokens exactly: 500 / 1.3 ≈ 384.6 → 384 words → 499.2 → int = 499
    # Need 385 words → 385 * 1.3 = 500.5 → int = 500
    prompt_500_tokens = "word " * 385  # 385 * 1.3 = 500.5 → int = 500
    assert approx_tokens(prompt_500_tokens) == 500
    assert estimate_complexity(prompt_500_tokens, context_len=0) == "claude-haiku-4"


def test_estimate_complexity_always_escalate():
    """Verify that specific operation types bypass scoring and always use Opus."""
    assert estimate_complexity("any text", operation_type="refactor") == "claude-opus-4"
    assert estimate_complexity("any text", operation_type="architect") == "claude-opus-4"


def test_estimate_complexity_returns_string():
    """estimate_complexity always returns a valid model name."""
    result = estimate_complexity("test", context_len=0)
    assert result in ("claude-haiku-4", "claude-sonnet-4", "claude-opus-4")
