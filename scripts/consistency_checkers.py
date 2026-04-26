#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Consistency Checkers for Memory Lint
Extracted from memory_lint.py to reduce complexity
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, TypedDict

logger = logging.getLogger(__name__)


class TerminologyInconsistency(TypedDict):
    """One inconsistency entry: a base term used alongside one or more variants."""

    base_term: str
    variants: Dict[str, int]


class TerminologyChecker:
    """Check for inconsistent terminology across memory files"""

    # Common inconsistencies to check
    TERM_VARIANTS = {
        'autopilot': ['auto-pilot', 'auto pilot', 'AP', 'A/P'],
        'SimConnect': ['simconnect', 'sim-connect', 'sim connect'],
        'WASM': ['wasm', 'WebAssembly', 'web assembly'],
    }

    def __init__(self, custom_terms: Optional[Dict[str, List[str]]] = None):
        """
        Args:
            custom_terms: Additional term variants to check
        """
        self.term_variants = self.TERM_VARIANTS.copy()
        if custom_terms:
            self.term_variants.update(custom_terms)

    def check_files(self, md_files: List[Path]) -> List[TerminologyInconsistency]:
        """Check all files for terminology inconsistencies"""
        inconsistencies: List[TerminologyInconsistency] = []

        for base_term, variants in self.term_variants.items():
            counts = self._count_term_occurrences(base_term, variants, md_files)

            # Check if multiple variants used
            used_variants = {k: v for k, v in counts.items() if v > 0}
            if len(used_variants) > 1:
                inconsistencies.append({
                    'base_term': base_term,
                    'variants': used_variants
                })

        return inconsistencies

    def _count_term_occurrences(
        self,
        base_term: str,
        variants: List[str],
        md_files: List[Path]
    ) -> Dict[str, int]:
        """Count occurrences of term and its variants"""
        counts = {base_term: 0}
        for variant in variants:
            counts[variant] = 0

        # Count occurrences in all files
        for md_file in md_files:
            try:
                content = md_file.read_text(encoding='utf-8').lower()
            except (OSError, UnicodeDecodeError) as err:
                # Skip files that can't be read or decoded, but log so the
                # operator can investigate broken encodings instead of
                # silently dropping data.
                logger.warning(
                    "Skipping %s during terminology check: %s", md_file, err
                )
                continue

            for term in [base_term] + variants:
                counts[term] += content.count(term.lower())

        return counts


class ConsistencyRegistry:
    """Registry of all consistency checkers"""

    def __init__(self, custom_terms: Optional[Dict[str, List[str]]] = None):
        self.terminology_checker = TerminologyChecker(custom_terms)

    def check_all(
        self, md_files: List[Path]
    ) -> Dict[str, List[TerminologyInconsistency]]:
        """Run all consistency checks"""
        return {
            'terminology': self.terminology_checker.check_files(md_files)
        }
