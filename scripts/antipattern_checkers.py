#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Anti-pattern Checkers for Memory Lint
Extracted from memory_lint.py to reduce complexity
"""

import re
from pathlib import Path
from typing import Dict, List


class AntiPatternChecker:
    """Base class for anti-pattern detection"""

    def __init__(self, severity: str = 'medium'):
        self.severity = severity

    def check(self, file_path: Path, content: str, frontmatter: Dict) -> List[Dict]:
        """Check for anti-patterns. Override in subclasses."""
        raise NotImplementedError


class MissingWhyHowChecker(AntiPatternChecker):
    """Check for missing Why:/How to apply: in feedback/project types"""

    def __init__(self):
        super().__init__(severity='high')

    def check(self, file_path: Path, content: str, frontmatter: Dict) -> List[Dict]:
        memory_type = frontmatter.get('type', '')

        if memory_type not in ['feedback', 'project']:
            return []

        if '**Why:**' in content and '**How to apply:**' in content:
            return []

        return [{
            'file': file_path,
            'type': 'missing_why_how',
            'severity': self.severity,
            'message': f'{memory_type} memory missing Why:/How to apply: sections'
        }]


class ExcessiveCodeChecker(AntiPatternChecker):
    """Check for excessive code blocks (should be in codebase)"""

    def __init__(self, max_blocks: int = 3):
        super().__init__(severity='medium')
        self.max_blocks = max_blocks

    def check(self, file_path: Path, content: str, frontmatter: Dict) -> List[Dict]:
        code_blocks = re.findall(r'```[\s\S]*?```', content)

        if len(code_blocks) <= self.max_blocks:
            return []

        return [{
            'file': file_path,
            'type': 'excessive_code',
            'severity': self.severity,
            'message': f'{len(code_blocks)} code blocks - consider storing in codebase'
        }]


class VagueDescriptionChecker(AntiPatternChecker):
    """Check for vague descriptions"""

    VAGUE_WORDS = ['stuff', 'things', 'various', 'some', 'etc', 'and so on']

    def __init__(self):
        super().__init__(severity='low')

    def check(self, file_path: Path, content: str, frontmatter: Dict) -> List[Dict]:
        description = frontmatter.get('description', '')

        if not any(word in description.lower() for word in self.VAGUE_WORDS):
            return []

        return [{
            'file': file_path,
            'type': 'vague_description',
            'severity': self.severity,
            'message': 'Description contains vague words - be more specific'
        }]


class TemporaryDataChecker(AntiPatternChecker):
    """Check for temporary data in permanent layers"""

    TEMP_MARKERS = ['temp', 'temporary', 'draft', 'wip', 'work in progress']

    def __init__(self):
        super().__init__(severity='medium')

    def check(self, file_path: Path, content: str, frontmatter: Dict) -> List[Dict]:
        # Skip handoff.md (HOT layer)
        if file_path.name == 'handoff.md':
            return []

        if not any(marker in content.lower() for marker in self.TEMP_MARKERS):
            return []

        return [{
            'file': file_path,
            'type': 'temporary_in_permanent',
            'severity': self.severity,
            'message': 'Temporary data in permanent layer - should be in HOT'
        }]


class UndatedClaimsChecker(AntiPatternChecker):
    """Check for time-sensitive claims without dates"""

    CLAIM_WORDS = ['currently', 'now', 'today', 'recently', 'latest']

    def __init__(self):
        super().__init__(severity='medium')

    def check(self, file_path: Path, content: str, frontmatter: Dict) -> List[Dict]:
        has_claims = any(word in content.lower() for word in self.CLAIM_WORDS)
        has_dates = bool(re.search(r'\d{4}-\d{2}-\d{2}', content))

        if not has_claims or has_dates:
            return []

        return [{
            'file': file_path,
            'type': 'undated_claims',
            'severity': self.severity,
            'message': 'Time-sensitive claims without dates - add timestamps'
        }]


class GitDuplicationChecker(AntiPatternChecker):
    """Check for duplicate information from git history"""

    GIT_MARKERS = ['commit', 'merged', 'pull request', 'pr #', 'issue #']

    def __init__(self, max_markers: int = 3):
        super().__init__(severity='low')
        self.max_markers = max_markers

    def check(self, file_path: Path, content: str, frontmatter: Dict) -> List[Dict]:
        marker_count = sum(1 for marker in self.GIT_MARKERS if marker in content.lower())

        if marker_count <= self.max_markers:
            return []

        return [{
            'file': file_path,
            'type': 'git_duplication',
            'severity': self.severity,
            'message': 'Duplicates git history - use git log instead'
        }]


class AntiPatternRegistry:
    """Registry of all anti-pattern checkers"""

    def __init__(self):
        self.checkers: List[AntiPatternChecker] = [
            MissingWhyHowChecker(),
            ExcessiveCodeChecker(),
            VagueDescriptionChecker(),
            TemporaryDataChecker(),
            UndatedClaimsChecker(),
            GitDuplicationChecker()
        ]

    def check_all(self, file_path: Path, content: str, frontmatter: Dict) -> List[Dict]:
        """Run all checkers and collect results"""
        results = []
        for checker in self.checkers:
            results.extend(checker.check(file_path, content, frontmatter))
        return results
