#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for Skill Creator

Покрытие:
- Инициализация
- Анализ сессий
- Паттерны и кандидаты
- Генерация skills
- Безопасность (валидация путей)
- Производительность (кэширование, параллельная обработка)
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.skill_creator import SkillCreator


class TestSkillCreatorInit:
    """Test initialization"""

    @pytest.fixture
    def temp_claude_dir(self):
        """Create temporary .claude directory"""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_init_default(self):
        """Test default initialization"""
        creator = SkillCreator()
        assert creator.claude_dir == Path.home() / ".claude"
        assert creator.min_pattern_count == 3
        assert creator.min_success_rate == 0.8

    def test_safe_file_path_valid(self, temp_claude_dir):
        """Test safe_file_path with valid path"""
        creator = SkillCreator()
        creator.claude_dir = temp_claude_dir

        valid_path = temp_claude_dir / "test.json"
        result = creator.safe_file_path(valid_path)
        assert result.is_absolute()

    def test_safe_file_path_invalid(self, temp_claude_dir):
        """Test safe_file_path rejects path outside claude_dir"""
        creator = SkillCreator()
        creator.claude_dir = temp_claude_dir

        invalid_path = Path("/tmp/outside.json")
        with pytest.raises(ValueError, match="Invalid path"):
            creator.safe_file_path(invalid_path)


class TestSessionAnalysis:
    """Test session analysis"""

    @pytest.fixture
    def temp_claude_dir(self):
        """Create temporary .claude directory"""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def creator(self, temp_claude_dir):
        """Create SkillCreator with temp directory"""
        creator = SkillCreator()
        creator.claude_dir = temp_claude_dir
        creator.patterns_db = temp_claude_dir / "patterns.json"
        return creator

    def test_analyze_session_nonexistent(self, creator):
        """Test analyzing nonexistent session file"""
        fake_file = Path("/tmp/nonexistent.jsonl")
        patterns = creator.analyze_session(fake_file)
        assert patterns == []

    def test_analyze_session_valid(self, creator, temp_claude_dir):
        """Test analyzing valid session file"""
        session_file = temp_claude_dir / "session.jsonl"

        # Create mock session data
        session_data = [
            {"type": "user", "message": {"content": "Test task"}},
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "Read"},
                {"type": "tool_use", "name": "Edit"}
            ]}},
        ]

        with open(session_file, 'w', encoding='utf-8') as f:
            for entry in session_data:
                f.write(json.dumps(entry) + '\n')

        patterns = creator.analyze_session(session_file)
        assert len(patterns) > 0
        assert patterns[0]['tools'] == ['Read', 'Edit']
        assert patterns[0]['success'] is True

    def test_analyze_session_no_read_access(self, creator, temp_claude_dir):
        """Test that files without read access are skipped"""
        session_file = temp_claude_dir / "session.jsonl"
        session_file.write_text('{"type": "user"}', encoding='utf-8')

        with patch('os.access', return_value=False):
            patterns = creator.analyze_session(session_file)
            assert patterns == []


class TestPatternsDatabase:
    """Test patterns database operations"""

    @pytest.fixture
    def temp_claude_dir(self):
        """Create temporary .claude directory"""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def creator(self, temp_claude_dir):
        """Create SkillCreator with temp directory"""
        creator = SkillCreator()
        creator.claude_dir = temp_claude_dir
        creator.patterns_db = temp_claude_dir / "patterns.json"
        return creator

    def test_load_patterns_db_empty(self, creator):
        """Test loading nonexistent patterns DB"""
        db = creator.load_patterns_db()
        assert db == {'patterns': {}, 'last_update': None}

    def test_save_and_load_patterns_db(self, creator):
        """Test saving and loading patterns DB"""
        test_db = {
            'patterns': {'test': {'count': 1}},
            'last_update': None
        }

        creator.save_patterns_db(test_db)
        loaded = creator.load_patterns_db()

        assert 'test' in loaded['patterns']
        assert loaded['patterns']['test']['count'] == 1
        assert loaded['last_update'] is not None

    def test_load_patterns_db_cached(self, creator):
        """Test that load_patterns_db uses cache"""
        # First call
        db1 = creator.load_patterns_db()
        # Second call (should hit cache)
        db2 = creator.load_patterns_db()

        assert db1 == db2
        cache_info = creator.load_patterns_db.cache_info()
        assert cache_info.hits > 0

    def test_update_patterns(self, creator):
        """Test updating patterns"""
        new_patterns = [
            {'tools': ['Read', 'Edit'], 'success': True, 'task': 'Test task 1'},
            {'tools': ['Read', 'Edit'], 'success': True, 'task': 'Test task 2'},
        ]

        creator.update_patterns(new_patterns)
        db = creator.load_patterns_db()

        # Should have one pattern with count=2
        assert len(db['patterns']) == 1
        pattern_key = str(tuple(['Read', 'Edit']))
        assert db['patterns'][pattern_key]['count'] == 2
        assert db['patterns'][pattern_key]['success_count'] == 2


class TestSkillCandidates:
    """Test skill candidate detection"""

    @pytest.fixture
    def temp_claude_dir(self):
        """Create temporary .claude directory"""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def creator(self, temp_claude_dir):
        """Create SkillCreator with temp directory"""
        creator = SkillCreator()
        creator.claude_dir = temp_claude_dir
        creator.patterns_db = temp_claude_dir / "patterns.json"
        return creator

    def test_find_skill_candidates_empty(self, creator):
        """Test finding candidates with no patterns"""
        candidates = creator.find_skill_candidates()
        assert candidates == []

    def test_find_skill_candidates_below_threshold(self, creator):
        """Test that patterns below threshold are not candidates"""
        # Create pattern with only 2 uses (below min_pattern_count=3)
        db = {
            'patterns': {
                'test': {
                    'tools': ['Read', 'Edit'],
                    'count': 2,
                    'success_count': 2,
                    'example_tasks': ['Task 1', 'Task 2']
                }
            },
            'last_update': None
        }
        creator.save_patterns_db(db)

        candidates = creator.find_skill_candidates()
        assert len(candidates) == 0

    def test_find_skill_candidates_valid(self, creator):
        """Test finding valid skill candidates"""
        # Create pattern meeting thresholds
        db = {
            'patterns': {
                'test': {
                    'tools': ['Read', 'Edit'],
                    'count': 5,
                    'success_count': 5,
                    'example_tasks': ['Task 1', 'Task 2', 'Task 3']
                }
            },
            'last_update': None
        }
        creator.save_patterns_db(db)

        candidates = creator.find_skill_candidates()
        assert len(candidates) == 1
        assert candidates[0]['count'] == 5
        assert candidates[0]['success_rate'] == 1.0


class TestSkillGeneration:
    """Test skill generation"""

    @pytest.fixture
    def temp_claude_dir(self):
        """Create temporary .claude directory"""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def creator(self, temp_claude_dir):
        """Create SkillCreator with temp directory"""
        creator = SkillCreator()
        creator.claude_dir = temp_claude_dir
        creator.skills_dir = temp_claude_dir / "skills"
        return creator

    def test_generate_skill(self, creator):
        """Test skill content generation"""
        candidate = {
            'tools': ['Read', 'Edit'],
            'count': 5,
            'success_rate': 0.9,
            'example_tasks': ['Task 1', 'Task 2']
        }

        content = creator.generate_skill(candidate, "Test Skill")

        assert "Test Skill" in content
        assert "Read" in content
        assert "Edit" in content
        assert "90%" in content
        assert "Task 1" in content

    def test_create_skill_file(self, creator):
        """Test creating skill file"""
        content = "# Test Skill\nTest content"
        result = creator.create_skill_file("Test Skill", content)

        assert result is True
        skill_file = creator.skills_dir / "test-skill" / "SKILL.md"
        assert skill_file.exists()
        assert "Test content" in skill_file.read_text(encoding='utf-8')

    def test_create_skill_file_sanitizes_name(self, creator):
        """Test that skill name is sanitized and stays inside skills_dir"""
        content = "# Test"
        result = creator.create_skill_file("Test/../../../etc/passwd", content)

        # Should accept the call after sanitisation
        assert result is True
        # Every SKILL.md created by create_skill_file must live under skills_dir
        skills_dir = creator.skills_dir.resolve()
        created = list(skills_dir.rglob("SKILL.md"))
        assert created, "Expected create_skill_file to write a SKILL.md under skills_dir"
        for skill_file in created:
            # raises ValueError if the resolved path escaped skills_dir
            skill_file.resolve().relative_to(skills_dir)

    def test_suggest_skills(self, creator):
        """Test skill suggestions"""
        # Create valid pattern
        db = {
            'patterns': {
                'test': {
                    'tools': ['Read', 'Edit'],
                    'count': 5,
                    'success_count': 5,
                    'example_tasks': ['Task 1']
                }
            },
            'last_update': None
        }
        creator.patterns_db = creator.claude_dir / "patterns.json"
        creator.save_patterns_db(db)

        suggestions = creator.suggest_skills()
        assert len(suggestions) > 0
        assert 'name' in suggestions[0]
        assert 'candidate' in suggestions[0]


class TestPerformance:
    """Test performance features"""

    @pytest.fixture
    def temp_claude_dir(self):
        """Create temporary .claude directory"""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def creator(self, temp_claude_dir):
        """Create SkillCreator with temp directory"""
        creator = SkillCreator()
        creator.claude_dir = temp_claude_dir
        creator.projects_dir = temp_claude_dir / "projects"
        creator.patterns_db = temp_claude_dir / "patterns.json"
        return creator

    def test_analyze_all_sessions_parallel(self, creator):
        """Test parallel session analysis"""
        # Create test project with multiple sessions
        project_dir = creator.projects_dir / "test-project"
        project_dir.mkdir(parents=True)

        for i in range(3):
            session_file = project_dir / f"session{i}.jsonl"
            session_data = [
                {"type": "user", "message": {"content": f"Task {i}"}},
                {"type": "assistant", "message": {"content": [
                    {"type": "tool_use", "name": "Read"}
                ]}},
            ]
            with open(session_file, 'w', encoding='utf-8') as f:
                for entry in session_data:
                    f.write(json.dumps(entry) + '\n')

        count = creator.analyze_all_sessions(max_workers=2)
        assert count == 3


class TestEdgeCases:
    """Test edge cases"""

    @pytest.fixture
    def temp_claude_dir(self):
        """Create temporary .claude directory"""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def creator(self, temp_claude_dir):
        """Create SkillCreator with temp directory"""
        creator = SkillCreator()
        creator.claude_dir = temp_claude_dir
        creator.patterns_db = temp_claude_dir / "patterns.json"
        return creator

    def test_analyze_session_malformed_json(self, creator, temp_claude_dir):
        """Test handling malformed JSON in session"""
        session_file = temp_claude_dir / "bad.jsonl"
        session_file.write_text("not valid json\n{\"valid\": true}", encoding='utf-8')

        patterns = creator.analyze_session(session_file)
        # Should skip malformed lines but continue
        assert isinstance(patterns, list)

    def test_analyze_session_empty_file(self, creator, temp_claude_dir):
        """Test analyzing empty session file"""
        session_file = temp_claude_dir / "empty.jsonl"
        session_file.write_text("", encoding='utf-8')

        patterns = creator.analyze_session(session_file)
        assert patterns == []

    def test_unicode_in_patterns(self, creator):
        """Test Unicode handling in patterns"""
        patterns = [
            {'tools': ['Read'], 'success': True, 'task': 'Тестовая задача 中文'}
        ]

        creator.update_patterns(patterns)
        db = creator.load_patterns_db()
        assert len(db['patterns']) > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
