import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from unittest.mock import MagicMock, patch
from l4_semantic_global import GlobalSemanticMemory


def test_warn_if_mixed_metrics():
    """_warn_if_mixed_metrics() should warn when collections use different metrics."""
    gsm = object.__new__(GlobalSemanticMemory)
    gsm.client = MagicMock()

    col1 = MagicMock()
    col1.name = "memory_C--BAT"
    col1.metadata = {"hnsw:space": "cosine"}

    col2 = MagicMock()
    col2.name = "memory_C--TEST"
    col2.metadata = {"hnsw:space": "l2"}

    gsm.client.list_collections.return_value = [col1, col2]

    with patch("l4_semantic_global.logging") as mock_logging:
        gsm._warn_if_mixed_metrics()
        warnings = [
            call
            for call in mock_logging.warning.call_args_list
            if "metric" in str(call).lower() or "Mixed" in str(call)
        ]
        assert len(warnings) > 0, (
            "_warn_if_mixed_metrics() should log a warning for mixed metrics"
        )


def test_warn_if_same_metrics():
    """_warn_if_mixed_metrics() should NOT warn when all collections use the same metric."""
    gsm = object.__new__(GlobalSemanticMemory)
    gsm.client = MagicMock()

    col1 = MagicMock()
    col1.name = "memory_C--BAT"
    col1.metadata = {"hnsw:space": "cosine"}

    col2 = MagicMock()
    col2.name = "memory_C--TEST"
    col2.metadata = {"hnsw:space": "cosine"}

    gsm.client.list_collections.return_value = [col1, col2]

    with patch("l4_semantic_global.logging") as mock_logging:
        gsm._warn_if_mixed_metrics()
        mock_logging.warning.assert_not_called()
