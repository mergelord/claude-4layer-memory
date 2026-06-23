"""Tests for the pre-install audit script."""

import audit


def test_audit_python_gate_matches_project_support_matrix():
    """Pre-install audit must reject versions below the supported 3.10+ floor."""
    assert audit.MIN_PYTHON_VERSION == (3, 10)
    assert audit.MIN_PYTHON_VERSION_TEXT == "3.10"

    is_supported, message = audit.get_python_version_check((3, 10, 0))
    assert is_supported
    assert message == "Python 3.10.0 (>= 3.10 required)"

    is_supported, message = audit.get_python_version_check((3, 13, 1))
    assert is_supported
    assert message == "Python 3.13.1 (>= 3.10 required)"

    is_supported, message = audit.get_python_version_check((3, 9, 18))
    assert not is_supported
    assert message == "Python 3.9.18 (>= 3.10 required)"
