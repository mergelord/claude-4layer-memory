#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Memory Lint Helpers - Common patterns and utilities
Extracted from memory_lint.py to reduce duplication
"""

import re
from pathlib import Path
from typing import Any, Callable, List, Optional


class RegexPatterns:
    """Compiled regex patterns for better performance"""

    # Frontmatter extraction
    FRONTMATTER = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.DOTALL)

    # Link patterns
    LINK_PATTERN = re.compile(r'\[([^\]]+)\]\(([^\)]+)\)')
    MARKDOWN_LINK = re.compile(r'\[([^\]]+)\]\(([^\)]+\.md)\)')

    # Frontmatter field patterns
    FIELD_NAME = re.compile(r'^name:\s*(.+)$', re.MULTILINE)
    FIELD_DESCRIPTION = re.compile(r'^description:\s*(.+)$', re.MULTILINE)
    FIELD_TYPE = re.compile(r'^type:\s*(.+)$', re.MULTILINE)

    # Date patterns
    DATE_PATTERN = re.compile(r'\b(20\d{2}[-/]\d{2}[-/]\d{2})\b')

    # Special characters for sanitization
    SPECIAL_CHARS = re.compile(r'[^\w\s\-.,!?]')


class CheckResultHandler:
    """Handler for check results with consistent formatting"""

    def __init__(self, reporter):
        """
        Initialize handler with reporter instance

        Args:
            reporter: BaseReporter instance for output
        """
        self.reporter = reporter

    def handle_check_result(
        self,
        results: List[Any],
        check_name: str,
        show_details: bool = True
    ) -> List[Any]:
        """
        Handle check results with consistent formatting

        Args:
            results: List of check results
            check_name: Name of the check
            show_details: Whether to show detailed results

        Returns:
            Original results list
        """
        self.reporter.print_section(check_name)

        if results:
            self.reporter.print_warn(f"Found {len(results)} issue(s)")
            if show_details:
                for result in results:
                    self.reporter.print_info(f"  {result}")
        else:
            self.reporter.print_ok("No issues found")

        return results

    def handle_check_dict_result(
        self,
        results: List[dict],
        check_name: str,
        key_field: str = 'file'
    ) -> List[dict]:
        """
        Handle dictionary check results

        Args:
            results: List of dict results
            check_name: Name of the check
            key_field: Field to use as primary identifier

        Returns:
            Original results list
        """
        self.reporter.print_section(check_name)

        if results:
            self.reporter.print_warn(f"Found {len(results)} issue(s)")
            for result in results:
                key = result.get(key_field, 'unknown')
                message = result.get('message', str(result))
                self.reporter.print_info(f"  {key}: {message}")
        else:
            self.reporter.print_ok("No issues found")

        return results


class SafeFileOperations:
    """Safe file operations with error handling"""

    def __init__(self, reporter):
        """
        Initialize with reporter for warnings

        Args:
            reporter: BaseReporter instance for output
        """
        self.reporter = reporter

    def safe_file_operation(
        self,
        file_path: Path,
        operation: Callable[[Path], Any],
        default: Any = None
    ) -> Any:
        """
        Execute file operation with error handling

        Args:
            file_path: Path to file
            operation: Function to execute on file
            default: Default value on error

        Returns:
            Operation result or default on error
        """
        try:
            return operation(file_path)
        except PermissionError:
            self.reporter.print_warn(f"Permission denied: {file_path}")
            return default
        except FileNotFoundError:
            self.reporter.print_warn(f"File not found: {file_path}")
            return default
        except Exception as exc:
            self.reporter.print_warn(f"Error processing {file_path}: {exc}")
            return default

    def safe_read_text(self, file_path: Path, encoding: str = 'utf-8') -> str:
        """
        Safely read file text

        Args:
            file_path: Path to file
            encoding: Text encoding

        Returns:
            File content or empty string on error
        """
        return self.safe_file_operation(
            file_path,
            lambda p: p.read_text(encoding=encoding),
            default=""
        )

    def safe_read_bytes(self, file_path: Path) -> bytes:
        """
        Safely read file bytes

        Args:
            file_path: Path to file

        Returns:
            File content or empty bytes on error
        """
        return self.safe_file_operation(
            file_path,
            lambda p: p.read_bytes(),
            default=b""
        )

    def safe_stat(self, file_path: Path) -> Optional[Any]:
        """
        Safely get file stats

        Args:
            file_path: Path to file

        Returns:
            File stats or None on error
        """
        return self.safe_file_operation(
            file_path,
            lambda p: p.stat(),
            default=None
        )


class FrontmatterExtractor:
    """Extract and parse frontmatter from markdown files"""

    @staticmethod
    def extract_frontmatter(content: str) -> dict:
        """
        Extract YAML frontmatter from markdown content

        Args:
            content: Markdown file content

        Returns:
            Dictionary with frontmatter fields
        """
        match = RegexPatterns.FRONTMATTER.match(content)
        if not match:
            return {}

        frontmatter_text = match.group(1)
        result = {}

        # Extract common fields
        if name_match := RegexPatterns.FIELD_NAME.search(frontmatter_text):
            result['name'] = name_match.group(1).strip()

        if desc_match := RegexPatterns.FIELD_DESCRIPTION.search(frontmatter_text):
            result['description'] = desc_match.group(1).strip()

        if type_match := RegexPatterns.FIELD_TYPE.search(frontmatter_text):
            result['type'] = type_match.group(1).strip()

        return result

    @staticmethod
    def extract_links(content: str) -> List[str]:
        """
        Extract markdown links from content

        Args:
            content: Markdown content

        Returns:
            List of link targets
        """
        links = []
        for match in RegexPatterns.LINK_PATTERN.finditer(content):
            link = match.group(2)
            # Skip external links and anchors
            if not link.startswith(('http://', 'https://', '#')):
                links.append(link)
        return links


class ValidationHelpers:
    """Common validation helpers"""

    @staticmethod
    def is_valid_memory_type(memory_type: str) -> bool:
        """
        Check if memory type is valid

        Args:
            memory_type: Type string to validate

        Returns:
            True if valid type
        """
        valid_types = {'user', 'feedback', 'project', 'reference'}
        return memory_type.lower() in valid_types

    @staticmethod
    def sanitize_input(text: str) -> str:
        """
        Sanitize user input by removing special characters

        Args:
            text: Input text

        Returns:
            Sanitized text
        """
        return RegexPatterns.SPECIAL_CHARS.sub('', text)

    @staticmethod
    def extract_dates(content: str) -> List[str]:
        """
        Extract dates from content

        Args:
            content: Text content

        Returns:
            List of date strings
        """
        return RegexPatterns.DATE_PATTERN.findall(content)
