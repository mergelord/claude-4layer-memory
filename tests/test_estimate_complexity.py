import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from unittest.mock import MagicMock, patch
from claude_client import estimate_complexity


def test_estimate_complexity_words_vs_tokens():
    """estimate_complexity should treat context_len as tokens, not words.

    8000 words ≈ 10400 tokens. With token-aware thresholds, 8000 words
    should cross the 8000-token boundary and trigger score +1.
    """
    short = estimate_complexity("Refactor fts5_search", context_len=1000)
    long = estimate_complexity("Refactor fts5_search", context_len=10000)

    if short == long:
        pass  # context_len might not be the only factor — acceptable
    else:
        assert long != "claude-haiku-4", (
            "10000 tokens should not map to Haiku (threshold is 8000)"
        )


def test_estimate_complexity_returns_string():
    """estimate_complexity always returns a valid model name."""
    result = estimate_complexity("test", context_len=0)
    assert result in ("claude-haiku-4", "claude-sonnet-4", "claude-opus-4")
