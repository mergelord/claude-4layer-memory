"""
Tests for memory_lint.py
"""
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from memory_lint import MemoryLint


class TestMemoryLint:
    """Test MemoryLint class"""

    @pytest.fixture
    def temp_memory_dir(self):
        """Create temporary memory directory"""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def memory_lint(self, temp_memory_dir):
        """Create MemoryLint instance"""
        return MemoryLint(temp_memory_dir, quick_mode=True)

    def test_init(self, memory_lint, temp_memory_dir):
        """Test MemoryLint initialization"""
        assert memory_lint.memory_path == temp_memory_dir
        assert memory_lint.quick_mode is True
        assert memory_lint.errors == []
        assert memory_lint.warnings == []
        assert memory_lint.info == []

    def test_find_all_md_files_empty(self, memory_lint):
        """Test finding markdown files in empty directory"""
        files = memory_lint.find_all_md_files()
        assert files == []

    def test_find_all_md_files_with_files(self, temp_memory_dir, memory_lint):
        """Test finding markdown files"""
        # Create test files
        (temp_memory_dir / "test1.md").write_text("# Test 1")
        (temp_memory_dir / "test2.md").write_text("# Test 2")
        (temp_memory_dir / "test.txt").write_text("Not markdown")

        files = memory_lint.find_all_md_files()
        assert len(files) == 2
        assert all(f.suffix == '.md' for f in files)

    def test_check_ghost_links_no_links(self, temp_memory_dir, memory_lint):
        """Test ghost link detection with no links"""
        (temp_memory_dir / "test.md").write_text("# Test\n\nNo links here")

        ghost_links = memory_lint.check_ghost_links()
        assert ghost_links == {}

    def test_check_ghost_links_valid_link(self, temp_memory_dir, memory_lint):
        """Test ghost link detection with valid link"""
        (temp_memory_dir / "test1.md").write_text("# Test 1")
        (temp_memory_dir / "test2.md").write_text("# Test 2\n\nSee [test1](test1.md)")

        ghost_links = memory_lint.check_ghost_links()
        assert ghost_links == {}

    def test_check_ghost_links_broken_link(self, temp_memory_dir, memory_lint):
        """Test ghost link detection with broken link"""
        (temp_memory_dir / "test.md").write_text("# Test\n\nSee [missing](missing.md)")

        ghost_links = memory_lint.check_ghost_links()
        assert len(ghost_links) > 0

    def test_check_orphan_files_no_orphans(self, temp_memory_dir, memory_lint):
        """Test orphan detection with no orphans"""
        (temp_memory_dir / "MEMORY.md").write_text("# Memory\n\n- [test](test.md)")
        (temp_memory_dir / "test.md").write_text("# Test")

        orphans = memory_lint.check_orphan_files()
        assert orphans == []

    def test_check_duplicates_no_duplicates(self, temp_memory_dir, memory_lint):
        """Test duplicate detection with unique names"""
        (temp_memory_dir / "test1.md").write_text("---\nname: test1\n---\n# Test 1")
        (temp_memory_dir / "test2.md").write_text("---\nname: test2\n---\n# Test 2")

        duplicates = memory_lint.check_duplicates()
        assert duplicates == {}

    def test_generate_report(self, memory_lint):
        """Test report generation"""
        report = memory_lint.generate_report()

        assert 'timestamp' in report
        assert 'memory_path' in report
        assert 'errors' in report
        assert 'warnings' in report
        assert 'info' in report
        assert report['errors'] == 0
        assert report['warnings'] == 0
        assert report['info'] == 0
