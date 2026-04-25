#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for Cleanup System Artifacts

Покрытие:
- Инициализация и поиск артефактов
- Нормализация путей
- Удаление артефактов
- Безопасность (проверка прав доступа, валидация путей)
- Статистика и verbose режим
"""

import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.cleanup_system_artifacts import (
    SYSTEM_PATH_PATTERNS,
    cleanup_artifacts,
    find_system_artifacts,
    is_system_artifact,
    normalize_path,
)


class TestNormalizePath:
    """Test path normalization"""

    def test_normalize_windows_path(self):
        """Test Windows path normalization"""
        assert normalize_path("C:\\WINDOWS\\system32") == "C--WINDOWS-system32"

    def test_normalize_unix_path(self):
        """Test Unix path normalization"""
        assert normalize_path("/usr/bin") == "-usr-bin"

    def test_normalize_mixed_separators(self):
        """Test mixed separators"""
        assert normalize_path("C:/WINDOWS\\system32") == "C--WINDOWS-system32"

    def test_normalize_with_colon(self):
        """Test colon replacement"""
        assert normalize_path("C:test") == "C-test"


class TestIsSystemArtifact:
    """Test system artifact detection"""

    def test_windows_system32(self):
        """Test Windows system32 detection"""
        assert is_system_artifact("C--WINDOWS-system32") is True
        assert is_system_artifact("C-WINDOWS-system32") is True

    def test_program_files(self):
        """Test Program Files detection"""
        assert is_system_artifact("C--Program Files") is True
        assert is_system_artifact("C-Program Files (x86)") is True

    def test_unix_paths(self):
        """Test Unix system paths"""
        assert is_system_artifact("-usr-bin") is True
        assert is_system_artifact("-etc") is True

    def test_non_system_path(self):
        """Test non-system path"""
        assert is_system_artifact("C--BAT") is False
        assert is_system_artifact("my-project") is False

    def test_normalized_detection(self):
        """Test detection with normalization"""
        # Should normalize and detect
        assert is_system_artifact("C:\\WINDOWS\\system32") is True


class TestFindSystemArtifacts:
    """Test finding system artifacts"""

    @pytest.fixture
    def temp_projects_dir(self):
        """Create temporary projects directory"""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_find_no_artifacts(self, temp_projects_dir):
        """Test when no artifacts exist"""
        # Create normal project
        (temp_projects_dir / "my-project").mkdir()

        artifacts = find_system_artifacts(temp_projects_dir)
        assert len(artifacts) == 0

    def test_find_system_artifacts(self, temp_projects_dir):
        """Test finding system artifacts"""
        # Create system artifacts
        (temp_projects_dir / "C--WINDOWS-system32").mkdir()
        (temp_projects_dir / "-usr-bin").mkdir()
        # Create normal project
        (temp_projects_dir / "my-project").mkdir()

        artifacts = find_system_artifacts(temp_projects_dir)
        assert len(artifacts) == 2

    def test_nonexistent_directory(self):
        """Test with nonexistent directory"""
        fake_dir = Path("/tmp/nonexistent-12345")
        artifacts = find_system_artifacts(fake_dir)
        assert artifacts == []

    def test_no_read_access(self, temp_projects_dir):
        """Test directory without read access"""
        with patch('os.access', return_value=False):
            artifacts = find_system_artifacts(temp_projects_dir)
            assert artifacts == []


class TestCleanupArtifacts:
    """Test artifact cleanup"""

    @pytest.fixture
    def temp_projects_dir(self):
        """Create temporary projects directory"""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_cleanup_no_artifacts(self):
        """Test cleanup with no artifacts"""
        deleted, failed = cleanup_artifacts([], dry_run=False)
        assert deleted == 0
        assert failed == 0

    def test_cleanup_dry_run(self, temp_projects_dir):
        """Test dry run mode"""
        artifact = temp_projects_dir / "C--WINDOWS-system32"
        artifact.mkdir()

        deleted, failed = cleanup_artifacts([artifact], dry_run=True)
        assert deleted == 0
        assert failed == 0
        assert artifact.exists()  # Should not be deleted

    def test_cleanup_success(self, temp_projects_dir):
        """Test successful cleanup"""
        artifact = temp_projects_dir / "C--WINDOWS-system32"
        artifact.mkdir()

        deleted, failed = cleanup_artifacts([artifact], dry_run=False,
                                           projects_dir=temp_projects_dir)
        assert deleted == 1
        assert failed == 0
        assert not artifact.exists()

    def test_cleanup_multiple_artifacts(self, temp_projects_dir):
        """Test cleaning multiple artifacts"""
        artifact1 = temp_projects_dir / "C--WINDOWS-system32"
        artifact2 = temp_projects_dir / "-usr-bin"
        artifact1.mkdir()
        artifact2.mkdir()

        deleted, failed = cleanup_artifacts([artifact1, artifact2], dry_run=False,
                                           projects_dir=temp_projects_dir)
        assert deleted == 2
        assert failed == 0

    def test_cleanup_no_write_access(self, temp_projects_dir):
        """Test cleanup without write access"""
        artifact = temp_projects_dir / "C--WINDOWS-system32"
        artifact.mkdir()

        with patch('os.access', return_value=False):
            deleted, failed = cleanup_artifacts([artifact], dry_run=False,
                                               projects_dir=temp_projects_dir)
            assert deleted == 0
            assert failed == 1
            assert artifact.exists()

    def test_cleanup_path_validation(self, temp_projects_dir):
        """Test path validation (outside projects_dir)"""
        outside_path = Path(tempfile.mkdtemp())
        try:
            deleted, failed = cleanup_artifacts([outside_path], dry_run=False,
                                               projects_dir=temp_projects_dir)
            assert deleted == 0
            assert failed == 1
            assert outside_path.exists()
        finally:
            shutil.rmtree(outside_path, ignore_errors=True)

    def test_cleanup_verbose_mode(self, temp_projects_dir):
        """Test verbose mode output"""
        artifact = temp_projects_dir / "C--WINDOWS-system32"
        artifact.mkdir()
        # Create some files
        (artifact / "test.txt").write_text("test content")

        deleted, failed = cleanup_artifacts([artifact], dry_run=False,
                                           verbose=True, projects_dir=temp_projects_dir)
        assert deleted == 1
        assert failed == 0


class TestEdgeCases:
    """Test edge cases"""

    @pytest.fixture
    def temp_projects_dir(self):
        """Create temporary projects directory"""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_empty_artifact_name(self):
        """Test empty artifact name"""
        assert is_system_artifact("") is False

    def test_artifact_with_files(self, temp_projects_dir):
        """Test artifact containing files"""
        artifact = temp_projects_dir / "C--WINDOWS-system32"
        artifact.mkdir()
        (artifact / "file1.txt").write_text("content1")
        (artifact / "subdir").mkdir()
        (artifact / "subdir" / "file2.txt").write_text("content2")

        deleted, failed = cleanup_artifacts([artifact], dry_run=False,
                                           projects_dir=temp_projects_dir)
        assert deleted == 1
        assert failed == 0
        assert not artifact.exists()

    def test_unicode_in_paths(self, temp_projects_dir):
        """Test Unicode handling"""
        artifact = temp_projects_dir / "C--WINDOWS-system32"
        artifact.mkdir()
        (artifact / "тест.txt").write_text("содержимое", encoding="utf-8")

        deleted, failed = cleanup_artifacts([artifact], dry_run=False,
                                           projects_dir=temp_projects_dir)
        assert deleted == 1
        assert failed == 0

    def test_symlink_artifact(self, temp_projects_dir):
        """Test handling of symlinks"""
        real_dir = temp_projects_dir / "real"
        real_dir.mkdir()

        # Skip on Windows if symlinks not supported
        try:
            symlink = temp_projects_dir / "C--WINDOWS-system32"
            symlink.symlink_to(real_dir)

            deleted, failed = cleanup_artifacts([symlink], dry_run=False,
                                               projects_dir=temp_projects_dir)
            # Should handle symlink
            assert deleted + failed == 1
        except OSError:
            pytest.skip("Symlinks not supported")


class TestSystemPatterns:
    """Test SYSTEM_PATH_PATTERNS completeness"""

    def test_patterns_not_empty(self):
        """Test that patterns set is not empty"""
        assert len(SYSTEM_PATH_PATTERNS) > 0

    def test_windows_patterns_present(self):
        """Test Windows patterns are present"""
        assert "C--WINDOWS-system32" in SYSTEM_PATH_PATTERNS
        assert "C--Program Files" in SYSTEM_PATH_PATTERNS

    def test_unix_patterns_present(self):
        """Test Unix patterns are present"""
        assert "-usr-bin" in SYSTEM_PATH_PATTERNS
        assert "-etc" in SYSTEM_PATH_PATTERNS


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
