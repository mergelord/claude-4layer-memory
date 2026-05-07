#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for EncodingGate cleanup methods (strip_bom, strip_control_chars, clean_file)."""

import sys
from pathlib import Path

import pytest

# Add scripts/ to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from memory_lint_helpers import EncodingGate


class TestStripBOM:
    """Tests for EncodingGate.strip_bom()"""

    def test_utf8_bom_removed(self):
        """UTF-8 BOM (EF BB BF) is detected and removed."""
        data = b'\xef\xbb\xbfHello World'
        cleaned, bom_type = EncodingGate.strip_bom(data)
        assert cleaned == b'Hello World'
        assert bom_type == "UTF-8"

    def test_utf16_le_bom_removed(self):
        """UTF-16 LE BOM (FF FE) is detected and removed."""
        data = b'\xff\xfeH\x00e\x00l\x00l\x00o\x00'
        cleaned, bom_type = EncodingGate.strip_bom(data)
        assert cleaned == b'H\x00e\x00l\x00l\x00o\x00'
        assert bom_type == "UTF-16-LE"

    def test_utf16_be_bom_removed(self):
        """UTF-16 BE BOM (FE FF) is detected and removed."""
        data = b'\xfe\xff\x00H\x00e\x00l\x00l\x00o'
        cleaned, bom_type = EncodingGate.strip_bom(data)
        assert cleaned == b'\x00H\x00e\x00l\x00l\x00o'
        assert bom_type == "UTF-16-BE"

    def test_no_bom_returns_original(self):
        """Data without BOM is returned unchanged."""
        data = b'Hello World'
        cleaned, bom_type = EncodingGate.strip_bom(data)
        assert cleaned == data
        assert bom_type is None

    def test_empty_data(self):
        """Empty bytes return empty with no BOM."""
        data = b''
        cleaned, bom_type = EncodingGate.strip_bom(data)
        assert cleaned == b''
        assert bom_type is None

    def test_partial_bom_not_removed(self):
        """Partial BOM sequences are not mistaken for full BOM."""
        data = b'\xef\xbbHello'  # Only 2 bytes of UTF-8 BOM
        cleaned, bom_type = EncodingGate.strip_bom(data)
        assert cleaned == data
        assert bom_type is None


class TestStripControlChars:
    """Tests for EncodingGate.strip_control_chars()"""

    def test_null_bytes_removed(self):
        """Null bytes (0x00) are removed."""
        data = b'Hello\x00World\x00'
        cleaned, removed = EncodingGate.strip_control_chars(data)
        assert cleaned == b'HelloWorld'
        assert removed == 2

    def test_control_chars_removed(self):
        """Control characters (0x01-0x1F except newline/CR) are removed."""
        data = b'Hello\x01\x02\x03World\x1f'
        cleaned, removed = EncodingGate.strip_control_chars(data)
        assert cleaned == b'HelloWorld'
        assert removed == 4

    def test_newline_preserved(self):
        """Newline (0x0A) is preserved."""
        data = b'Hello\nWorld'
        cleaned, removed = EncodingGate.strip_control_chars(data)
        assert cleaned == b'Hello\nWorld'
        assert removed == 0

    def test_carriage_return_preserved(self):
        """Carriage return (0x0D) is preserved."""
        data = b'Hello\r\nWorld'
        cleaned, removed = EncodingGate.strip_control_chars(data)
        assert cleaned == b'Hello\r\nWorld'
        assert removed == 0

    def test_mixed_control_chars(self):
        """Mix of null bytes, control chars, and valid newlines."""
        data = b'Line1\n\x00Line2\x01\r\nLine3\x1f'
        cleaned, removed = EncodingGate.strip_control_chars(data)
        assert cleaned == b'Line1\nLine2\r\nLine3'
        assert removed == 3

    def test_clean_data_unchanged(self):
        """Data without control chars returns unchanged."""
        data = b'Hello World\nNew Line'
        cleaned, removed = EncodingGate.strip_control_chars(data)
        assert cleaned == data
        assert removed == 0

    def test_empty_data(self):
        """Empty bytes return empty with zero removed."""
        data = b''
        cleaned, removed = EncodingGate.strip_control_chars(data)
        assert cleaned == b''
        assert removed == 0


class TestCleanFile:
    """Tests for EncodingGate.clean_file()"""

    def test_clean_file_with_bom(self, tmp_path):
        """File with UTF-8 BOM is cleaned."""
        test_file = tmp_path / "test_bom.txt"
        test_file.write_bytes(b'\xef\xbb\xbfHello World')

        changed, changes = EncodingGate.clean_file(test_file)

        assert changed is True
        assert "BOM (UTF-8) removed" in changes
        assert test_file.read_bytes() == b'Hello World'

    def test_clean_file_with_control_chars(self, tmp_path):
        """File with control chars is cleaned."""
        test_file = tmp_path / "test_control.txt"
        test_file.write_bytes(b'Hello\x00World\x01')

        changed, changes = EncodingGate.clean_file(test_file)

        assert changed is True
        assert any("Control chars removed" in c for c in changes)
        assert test_file.read_bytes() == b'HelloWorld'

    def test_clean_file_with_mojibake(self, tmp_path):
        """File with cp1251-as-utf8 mojibake is repaired."""
        # Create mojibake: "Привет" encoded as UTF-8, then decoded as cp1251, then encoded as UTF-8
        original = "Привет"
        mojibake = original.encode('utf-8').decode('cp1251').encode('utf-8')

        test_file = tmp_path / "test_mojibake.txt"
        test_file.write_bytes(mojibake)

        changed, changes = EncodingGate.clean_file(test_file)

        assert changed is True
        assert "Mojibake repaired" in changes
        assert test_file.read_text(encoding='utf-8') == original

    def test_clean_file_all_issues(self, tmp_path):
        """File with BOM + control chars + mojibake is fully cleaned."""
        original = "Привет"
        mojibake = original.encode('utf-8').decode('cp1251').encode('utf-8')
        data = b'\xef\xbb\xbf' + b'Start\x00' + mojibake + b'\x01End'

        test_file = tmp_path / "test_all.txt"
        test_file.write_bytes(data)

        changed, changes = EncodingGate.clean_file(test_file)

        assert changed is True
        assert "BOM (UTF-8) removed" in changes
        assert any("Control chars removed" in c for c in changes)
        assert "Mojibake repaired" in changes

        result = test_file.read_text(encoding='utf-8')
        assert "Start" in result
        assert original in result
        assert "End" in result
        assert "\x00" not in result
        assert "\x01" not in result

    def test_clean_file_already_clean(self, tmp_path):
        """Clean file returns no changes."""
        test_file = tmp_path / "test_clean.txt"
        test_file.write_text("Hello World\n", encoding='utf-8')

        changed, changes = EncodingGate.clean_file(test_file)

        assert changed is False
        assert changes == []

    def test_clean_file_skip_bom(self, tmp_path):
        """strip_bom=False preserves BOM."""
        test_file = tmp_path / "test_skip_bom.txt"
        test_file.write_bytes(b'\xef\xbb\xbfHello')

        changed, changes = EncodingGate.clean_file(test_file, strip_bom=False)

        assert changed is False
        assert changes == []
        assert test_file.read_bytes() == b'\xef\xbb\xbfHello'

    def test_clean_file_skip_control(self, tmp_path):
        """strip_control=False preserves control chars."""
        test_file = tmp_path / "test_skip_control.txt"
        test_file.write_bytes(b'Hello\x00World')

        changed, changes = EncodingGate.clean_file(test_file, strip_control=False)

        assert changed is False
        assert changes == []
        assert test_file.read_bytes() == b'Hello\x00World'

    def test_clean_file_skip_mojibake(self, tmp_path):
        """repair_mojibake=False preserves mojibake."""
        original = "Привет"
        mojibake = original.encode('utf-8').decode('cp1251').encode('utf-8')

        test_file = tmp_path / "test_skip_mojibake.txt"
        test_file.write_bytes(mojibake)

        changed, changes = EncodingGate.clean_file(
            test_file, repair_mojibake=False
        )

        assert changed is False
        assert changes == []
        # Mojibake should still be present
        assert test_file.read_bytes() == mojibake

    def test_clean_file_invalid_utf8_fallback(self, tmp_path):
        """Invalid UTF-8 triggers errors='replace' fallback."""
        test_file = tmp_path / "test_invalid.txt"
        # Invalid UTF-8 sequence
        test_file.write_bytes(b'Hello\xff\xfeWorld')

        changed, changes = EncodingGate.clean_file(test_file)

        assert changed is True
        assert "Invalid UTF-8 replaced with U+FFFD" in changes
        result = test_file.read_text(encoding='utf-8')
        assert "Hello" in result
        assert "World" in result
        assert "?" in result  # Replacement character


class TestIntegration:
    """Integration tests combining multiple cleanup operations."""

    def test_real_world_corrupted_file(self, tmp_path):
        """Simulate real-world file with multiple encoding issues."""
        # Create a file that mimics what might happen in Windows:
        # 1. UTF-8 BOM from editor
        # 2. Null bytes from binary corruption
        # 3. Mojibake from subprocess output
        # 4. Control chars from copy-paste

        original_text = "Проект: claude-4layer-memory"
        mojibake = original_text.encode('utf-8').decode('cp1251').encode('utf-8')

        data = (
            b'\xef\xbb\xbf'  # UTF-8 BOM
            + b'# Memory System\n\x00'  # Null byte
            + mojibake  # Mojibake
            + b'\x01\x02'  # Control chars
            + b'\n\nStatus: OK'
        )

        test_file = tmp_path / "corrupted.md"
        test_file.write_bytes(data)

        # Clean the file
        changed, changes = EncodingGate.clean_file(test_file)

        assert changed is True
        assert len(changes) == 3  # BOM, control chars, mojibake

        # Verify result
        result = test_file.read_text(encoding='utf-8')
        assert result.startswith("# Memory System")
        assert original_text in result
        assert "Status: OK" in result
        assert "\x00" not in result
        assert "\x01" not in result
        assert "\x02" not in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
