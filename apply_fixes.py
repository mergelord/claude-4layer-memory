from pathlib import Path

# --- 1. равим scripts/semantic_search.py ---
sp = Path('scripts/semantic_search.py')
content = sp.read_text('utf-8')

target_t = (
    '    except OSError as exc:\n'
    '        _emit_fallback(user_prompt, "os_error", str(exc))\n'
    '        return'
)
replace_t = target_t + '\n    except Exception as exc:\n        _emit_fallback(user_prompt, "unexpected", str(exc))\n        return'
content = content.replace(target_t, replace_t)

target_rc = (
    '    # тслеживаем стоимость операции\n'
    '    track_search_cost(user_prompt, result.stdout, trigger_found)'
)
replace_rc = (
    '    if result.returncode != 0:\n'
    '        detail = result.stderr.strip() or f"L4 search returned non-zero exit code: {result.returncode}"\n'
    '        _emit_fallback(user_prompt, "subprocess_error", detail)\n'
    '        return\n\n'
    + target_rc
)
content = content.replace(target_rc, replace_rc)

sp.write_text(content, 'utf-8')
print('[OK] scripts/semantic_search.py updated')

# --- 2. ишем свежий tests/test_semantic_search_hook.py ---
test_code = """#!/usr/bin/env python3
# -*- coding: utf-8 -*-
\"\"\"Tests for semantic_search.py fallback paths.\"\"\"

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import semantic_search


@pytest.fixture
def dummy_script(tmp_path):
    \"\"\"Создаёт временный python-файл, используемый как заглушка L4-скрипта.\"\"\"
    script = tmp_path / "dummy.py"
    script.write_text("# dummy script")
    return script


class TestExecuteSemanticSearch:
    @patch('semantic_search.logging')
    def test_timeout(self, mock_logging, dummy_script):
        with patch('semantic_search.safe_path', return_value=dummy_script):
            with patch('semantic_search.subprocess.run',
                       side_effect=subprocess.TimeoutExpired(cmd="dummy", timeout=30)):
                semantic_search.execute_semantic_search("test query", "как мы")
        mock_logging.warning.assert_called_once_with(
            'Semantic search fallback (%s): %s',
            'timeout',
            "L4 search exceeded 30s budget for trigger 'как мы'"
        )

    @patch('semantic_search.logging')
    def test_file_not_found(self, mock_logging, dummy_script):
        not_found = dummy_script.with_name("nonexistent.py")
        with patch('semantic_search.safe_path', return_value=not_found):
            semantic_search.execute_semantic_search("test query", "как мы")
        mock_logging.warning.assert_called_once()
        assert "not found" in str(mock_logging.warning.call_args)

    @patch('semantic_search.logging')
    def test_subprocess_error(self, mock_logging, dummy_script):
        with patch('semantic_search.safe_path', return_value=dummy_script):
            with patch('semantic_search.subprocess.run',
                       side_effect=subprocess.CalledProcessError(1, "dummy", b"", b"error")):
                semantic_search.execute_semantic_search("test query", "как мы")
        mock_logging.warning.assert_called_once()
        assert "non-zero" in str(mock_logging.warning.call_args)

    @patch('semantic_search.logging')
    def test_os_error(self, mock_logging, dummy_script):
        with patch('semantic_search.safe_path', return_value=dummy_script):
            with patch('semantic_search.subprocess.run',
                       side_effect=OSError("OS error")):
                semantic_search.execute_semantic_search("test query", "как мы")
        mock_logging.warning.assert_called_once()
        assert "OS error" in str(mock_logging.warning.call_args)

    @patch('semantic_search.logging')
    def test_unsafe_path(self, mock_logging):
        with patch('semantic_search.safe_path',
                   side_effect=ValueError("Path /etc/passwd is outside home directory")):
            semantic_search.execute_semantic_search("test query", "как мы")
        mock_logging.warning.assert_called_once()
        assert "unsafe_path" in str(mock_logging.warning.call_args)

    @patch('semantic_search.logging')
    def test_permission_error(self, mock_logging, dummy_script):
        with patch('semantic_search.safe_path', return_value=dummy_script):
            with patch('semantic_search.subprocess.run',
                       side_effect=PermissionError("permission denied")):
                semantic_search.execute_semantic_search("test query", "как мы")
        mock_logging.warning.assert_called_once()
        assert "no_access" in str(mock_logging.warning.call_args)
"""

Path('tests/test_semantic_search_hook.py').write_text(test_code, 'utf-8')
print('[OK] tests/test_semantic_search_hook.py updated')
