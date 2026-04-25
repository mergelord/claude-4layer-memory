#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuration for L4 Semantic Global Search
Extracted from l4_semantic_global.py per Alisa's recommendations
"""

import locale
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SemanticSearchConfig:
    """Configuration for semantic search system"""

    # Paths
    home: Path
    global_memory: Path
    projects_base: Path
    global_projects_file: Path
    db_path: Path

    # Model settings
    model_name: str = 'paraphrase-multilingual-MiniLM-L12-v2'

    # Search settings
    max_results: int = 5
    similarity_threshold: float = 0.3

    # Performance settings
    batch_size: int = 32
    max_workers: int = 4
    timeout: int = 30  # seconds

    # Output settings
    max_prompt_log_length: int = 100
    encoding: str = 'utf-8'

    # ChromaDB settings
    anonymized_telemetry: bool = False

    @classmethod
    def from_environment(cls) -> 'SemanticSearchConfig':
        """
        Create configuration from environment variables and defaults

        Environment variables:
            L4_MODEL - embedding model name
            L4_MAX_RESULTS - maximum search results
            L4_TIMEOUT - operation timeout in seconds
            L4_BATCH_SIZE - batch size for processing

        Returns:
            SemanticSearchConfig instance
        """
        home = Path.home()

        return cls(
            home=home,
            global_memory=home / ".claude" / "memory",
            projects_base=home / ".claude" / "projects",
            global_projects_file=home / ".claude" / "GLOBAL_PROJECTS.md",
            db_path=home / ".claude" / "semantic_db_global",
            model_name=os.getenv('L4_MODEL', 'paraphrase-multilingual-MiniLM-L12-v2'),
            max_results=int(os.getenv('L4_MAX_RESULTS', '5')),
            timeout=int(os.getenv('L4_TIMEOUT', '30')),
            batch_size=int(os.getenv('L4_BATCH_SIZE', '32')),
        )

    def validate(self) -> bool:
        """
        Validate configuration

        Returns:
            True if configuration is valid

        Raises:
            ValueError: If configuration is invalid
        """
        if not self.home.exists():
            raise ValueError(f"Home directory does not exist: {self.home}")

        if self.max_results < 1:
            raise ValueError(f"max_results must be >= 1, got {self.max_results}")

        if self.timeout < 1:
            raise ValueError(f"timeout must be >= 1, got {self.timeout}")

        if self.batch_size < 1:
            raise ValueError(f"batch_size must be >= 1, got {self.batch_size}")

        return True

    def ensure_directories(self):
        """Create necessary directories if they don't exist"""
        self.global_memory.mkdir(parents=True, exist_ok=True)
        self.projects_base.mkdir(parents=True, exist_ok=True)
        self.db_path.mkdir(parents=True, exist_ok=True)


class InputReader:
    """Safe input reading with platform-specific handling"""

    @staticmethod
    def read_input() -> str:
        """
        Read input from stdin with proper encoding handling

        Returns:
            Input string or empty string on error
        """
        try:
            if os.name == 'nt':  # Windows
                # Windows может использовать разные кодировки консоли
                # Пробуем UTF-8, затем fallback на системную кодировку
                try:
                    return sys.stdin.read().strip()
                except UnicodeDecodeError:
                    # Fallback на системную кодировку Windows
                    system_encoding = locale.getpreferredencoding()
                    return sys.stdin.buffer.read().decode(system_encoding).strip()
            else:  # Unix-like systems
                return sys.stdin.read().strip()

        except UnicodeDecodeError as exc:
            logging.warning("Failed to decode input: %s", exc)
            return ""
        except Exception as exc:
            logging.error("Error reading input: %s", exc)
            return ""

    @staticmethod
    def read_line() -> str:
        """
        Read single line from stdin

        Returns:
            Input line or empty string on error
        """
        try:
            if os.name == 'nt':  # Windows
                try:
                    return input().strip()
                except UnicodeDecodeError:
                    system_encoding = locale.getpreferredencoding()
                    return sys.stdin.buffer.readline().decode(system_encoding).strip()
            else:  # Unix-like systems
                return input().strip()

        except UnicodeDecodeError as exc:
            logging.warning("Failed to decode input line: %s", exc)
            return ""
        except EOFError:
            return ""
        except Exception as exc:
            logging.error("Error reading input line: %s", exc)
            return ""


# Для обратной совместимости
def get_default_config() -> SemanticSearchConfig:
    """Get default configuration"""
    return SemanticSearchConfig.from_environment()
