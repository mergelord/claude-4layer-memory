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


def test_estimate_complexity_prompt_tokens():
    """Verify that prompt_tokens_approx correctly escalates the model."""
    # 160 words * 1.3 = 208 tokens -> score +1
    long_prompt = "word " * 160
    assert estimate_complexity(long_prompt, context_len=0) == "claude-haiku-4"

    # 400 words * 1.3 = 520 tokens -> score +2
    very_long_prompt = "word " * 400
    assert estimate_complexity(very_long_prompt, context_len=0) == "claude-sonnet-4"


def test_estimate_complexity_always_escalate():
    """Verify that specific keywords bypass scoring and always use Opus."""
    assert estimate_complexity("refactor this code", context_len=0) == "claude-opus-4"
    assert estimate_complexity("architect a new module", context_len=0) == "claude-opus-4"


def test_estimate_complexity_returns_string():
    """estimate_complexity always returns a valid model name."""
    result = estimate_complexity("test", context_len=0)
    assert result in ("claude-haiku-4", "claude-sonnet-4", "claude-opus-4")
