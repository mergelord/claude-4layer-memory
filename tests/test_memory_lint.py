"""
Tests for memory_lint.py - Extended test coverage
"""
import shutil
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

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

    def test_find_all_md_files_skips_no_access(self, temp_memory_dir, memory_lint):
        """Test that files without read access are skipped"""
        (temp_memory_dir / "test.md").write_text("# Test")

        with patch('os.access', return_value=False):
            files = memory_lint.find_all_md_files()
            assert len(files) == 0

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

    def test_check_duplicates_found(self, temp_memory_dir, memory_lint):
        """Test duplicate detection finds duplicates"""
        (temp_memory_dir / "test1.md").write_text("# Same Title")
        (temp_memory_dir / "test2.md").write_text("# Same Title")

        duplicates = memory_lint.check_duplicates()
        assert len(duplicates) > 0

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


class TestMemoryLintExtractLinks:
    """Test link extraction"""

    @pytest.fixture
    def memory_lint(self):
        """Create MemoryLint instance"""
        temp_dir = Path(tempfile.mkdtemp())
        lint = MemoryLint(temp_dir, quick_mode=True)
        yield lint
        shutil.rmtree(temp_dir)

    def test_extract_links_simple(self, memory_lint):
        """Test simple link extraction"""
        content = "[Link](file.md)"
        links = memory_lint.extract_links(content)
        assert links == {"file.md"}

    def test_extract_links_multiple(self, memory_lint):
        """Test multiple link extraction"""
        content = "[Link1](file1.md) and [Link2](file2.md)"
        links = memory_lint.extract_links(content)
        assert links == {"file1.md", "file2.md"}

    def test_extract_links_skips_external(self, memory_lint):
        """Test that external links are skipped"""
        content = "[External](https://example.com) [Local](file.md)"
        links = memory_lint.extract_links(content)
        assert links == {"file.md"}

    def test_extract_links_skips_anchors(self, memory_lint):
        """Test that anchor links are skipped"""
        content = "[Anchor](#section) [Local](file.md)"
        links = memory_lint.extract_links(content)
        assert links == {"file.md"}

    def test_extract_links_cached(self, memory_lint):
        """Test that extract_links uses cache"""
        content = "[Link](file.md)"
        links1 = memory_lint.extract_links(content)
        links2 = memory_lint.extract_links(content)

        assert links1 == links2
        cache_info = memory_lint.extract_links.cache_info()
        assert cache_info.hits > 0


class TestMemoryLintFrontmatter:
    """Test frontmatter extraction"""

    @pytest.fixture
    def memory_lint(self):
        """Create MemoryLint instance"""
        temp_dir = Path(tempfile.mkdtemp())
        lint = MemoryLint(temp_dir, quick_mode=True)
        yield lint
        shutil.rmtree(temp_dir)

    def test_extract_frontmatter_valid(self, memory_lint):
        """Test valid frontmatter extraction"""
        content = """---
name: Test Memory
description: Test description
type: feedback
---

Content here"""
        frontmatter = memory_lint._extract_frontmatter(content)

        assert frontmatter['name'] == 'Test Memory'
        assert frontmatter['description'] == 'Test description'
        assert frontmatter['type'] == 'feedback'

    def test_extract_frontmatter_empty(self, memory_lint):
        """Test extraction with no frontmatter"""
        content = "# Just content"
        frontmatter = memory_lint._extract_frontmatter(content)
        assert len(frontmatter) == 0

    def test_extract_frontmatter_cached(self, memory_lint):
        """Test that frontmatter extraction uses cache"""
        content = """---
name: Test
---
Content"""
        fm1 = memory_lint._extract_frontmatter(content)
        fm2 = memory_lint._extract_frontmatter(content)

        assert fm1 == fm2
        cache_info = memory_lint._extract_frontmatter.cache_info()
        assert cache_info.hits > 0


class TestMemoryLintAge:
    """Test age checking"""

    @pytest.fixture
    def temp_memory_dir(self):
        """Create temporary memory directory"""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def memory_lint(self, temp_memory_dir):
        """Create MemoryLint instance"""
        return MemoryLint(temp_memory_dir, quick_mode=False)

    def test_check_hot_memory_age_fresh(self, temp_memory_dir, memory_lint):
        """Test that fresh HOT entries pass"""
        now = datetime.now()
        timestamp = now.strftime('%Y-%m-%d %H:%M')

        handoff = temp_memory_dir / "handoff.md"
        handoff.write_text(f"Event at {timestamp}", encoding='utf-8')

        old_entries = memory_lint.check_hot_memory_age()
        assert len(old_entries) == 0

    def test_check_hot_memory_age_old(self, temp_memory_dir, memory_lint):
        """Test that old HOT entries are detected"""
        old_time = datetime.now() - timedelta(hours=48)
        timestamp = old_time.strftime('%Y-%m-%d %H:%M')

        handoff = temp_memory_dir / "handoff.md"
        handoff.write_text(f"Event at {timestamp}", encoding='utf-8')

        old_entries = memory_lint.check_hot_memory_age()
        assert len(old_entries) > 0


class TestMemoryLintPerformance:
    """Test performance features"""

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

    def test_parallel_reading(self, temp_memory_dir, memory_lint):
        """Test parallel file reading"""
        # Create multiple files
        files = []
        for i in range(10):
            file = temp_memory_dir / f"file{i}.md"
            file.write_text(f"Content {i}", encoding='utf-8')
            files.append(file)

        results = memory_lint._read_files_parallel(files)
        assert len(results) == 10

    def test_cache_clear(self, memory_lint):
        """Test cache clearing"""
        content = "[Link](file.md)"
        memory_lint.extract_links(content)
        memory_lint._extract_frontmatter("---\nname: test\n---")

        # Check cache is populated
        assert memory_lint.extract_links.cache_info().currsize > 0

        # Clear cache
        memory_lint.clear_cache()

        # Check cache is empty
        assert memory_lint.extract_links.cache_info().currsize == 0


class TestMemoryLintEdgeCases:
    """Test edge cases"""

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

    def test_unicode_content(self, temp_memory_dir, memory_lint):
        """Test Unicode content handling"""
        file = temp_memory_dir / "unicode.md"
        file.write_text("# Тестовый заголовок\n中文内容", encoding='utf-8')

        duplicates = memory_lint.check_duplicates()
        assert isinstance(duplicates, dict)

    def test_empty_files(self, temp_memory_dir, memory_lint):
        """Test empty file handling"""
        file = temp_memory_dir / "empty.md"
        file.write_text("", encoding='utf-8')

        ghost_links = memory_lint.check_ghost_links()
        assert isinstance(ghost_links, dict)

    def test_nonexistent_memory_path(self, temp_memory_dir):
        """Test nonexistent directory handling"""
        fake_path = temp_memory_dir / "nonexistent"
        lint = MemoryLint(fake_path, quick_mode=True)

        result = lint.run_layer1()
        assert result is False

