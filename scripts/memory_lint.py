#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Memory Lint System - Two-Layer Validation
Inspired by llm-atomic-wiki's lint approach

Layer 1: Deterministic checks (ghost links, orphans, duplicates)
Layer 2: LLM-based semantic checks (contradictions, outdated claims)
"""

import sys
import os
from pathlib import Path
import re
from datetime import datetime, timedelta
from typing import List, Dict, Set, Tuple
import json

class Colors:
    """ANSI color codes"""
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'

    @staticmethod
    def disable():
        Colors.GREEN = ''
        Colors.YELLOW = ''
        Colors.RED = ''
        Colors.CYAN = ''
        Colors.BOLD = ''
        Colors.END = ''

if sys.platform == 'win32':
    Colors.disable()

class MemoryLint:
    def __init__(self, memory_path: Path):
        self.memory_path = memory_path
        self.errors = []
        self.warnings = []
        self.info = []

    def print_header(self, text: str):
        print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*70}{Colors.END}")
        print(f"{Colors.BOLD}{Colors.CYAN}{text:^70}{Colors.END}")
        print(f"{Colors.BOLD}{Colors.CYAN}{'='*70}{Colors.END}\n")

    def print_section(self, text: str):
        print(f"\n{Colors.BOLD}{Colors.CYAN}## {text}{Colors.END}")
        print(f"{Colors.CYAN}{'-'*70}{Colors.END}")

    def print_ok(self, text: str):
        try:
            print(f"{Colors.GREEN}✓{Colors.END} {text}")
        except UnicodeEncodeError:
            print(f"{Colors.GREEN}[OK]{Colors.END} {text}")

    def print_warn(self, text: str):
        try:
            print(f"{Colors.YELLOW}⚠{Colors.END} {text}")
        except UnicodeEncodeError:
            print(f"{Colors.YELLOW}[WARN]{Colors.END} {text}")
        self.warnings.append(text)

    def print_error(self, text: str):
        try:
            print(f"{Colors.RED}✗{Colors.END} {text}")
        except UnicodeEncodeError:
            print(f"{Colors.RED}[ERROR]{Colors.END} {text}")
        self.errors.append(text)

    def print_info(self, text: str):
        try:
            print(f"{Colors.CYAN}ℹ{Colors.END} {text}")
        except UnicodeEncodeError:
            print(f"{Colors.CYAN}[INFO]{Colors.END} {text}")
        self.info.append(text)

    def find_all_md_files(self) -> List[Path]:
        """Find all markdown files in memory directory"""
        return list(self.memory_path.rglob("*.md"))

    def extract_links(self, content: str) -> Set[str]:
        """Extract all markdown links from content"""
        # Match [text](link) and [text](link.md)
        pattern = r'\[([^\]]+)\]\(([^\)]+)\)'
        links = set()
        for match in re.finditer(pattern, content):
            link = match.group(2)
            # Skip external links
            if not link.startswith(('http://', 'https://', '#')):
                links.add(link)
        return links

    def check_ghost_links(self) -> Dict[Path, List[str]]:
        """Check for links to non-existent files"""
        self.print_section("Layer 1: Ghost Links Detection")

        ghost_links = {}
        md_files = self.find_all_md_files()

        for md_file in md_files:
            try:
                content = md_file.read_text(encoding='utf-8')
                links = self.extract_links(content)

                for link in links:
                    # Resolve relative path
                    target = (md_file.parent / link).resolve()

                    if not target.exists():
                        if md_file not in ghost_links:
                            ghost_links[md_file] = []
                        ghost_links[md_file].append(link)
            except Exception as e:
                self.print_warn(f"Could not read {md_file.name}: {e}")

        if ghost_links:
            for file, links in ghost_links.items():
                self.print_error(f"{file.name}: {len(links)} ghost link(s)")
                for link in links:
                    try:
                        print(f"    → {link}")
                    except UnicodeEncodeError:
                        print(f"    -> {link}")
        else:
            self.print_ok("No ghost links found")

        return ghost_links

    def check_orphan_files(self) -> List[Path]:
        """Check for files not linked from anywhere"""
        self.print_section("Layer 1: Orphan Files Detection")

        md_files = self.find_all_md_files()
        all_links = set()

        # Collect all links
        for md_file in md_files:
            try:
                content = md_file.read_text(encoding='utf-8')
                links = self.extract_links(content)
                for link in links:
                    target = (md_file.parent / link).resolve()
                    all_links.add(target)
            except Exception as e:
                continue

        # Find orphans (exclude index files)
        orphans = []
        exclude_names = {'MEMORY.md', 'handoff.md', 'decisions.md', 'README.md'}

        for md_file in md_files:
            if md_file.name not in exclude_names:
                if md_file.resolve() not in all_links:
                    orphans.append(md_file)

        if orphans:
            for orphan in orphans:
                self.print_warn(f"Orphan file: {orphan.relative_to(self.memory_path)}")
        else:
            self.print_ok("No orphan files found")

        return orphans

    def check_duplicates(self) -> Dict[str, List[Path]]:
        """Check for duplicate content (same title or very similar content)"""
        self.print_section("Layer 1: Duplicate Detection")

        md_files = self.find_all_md_files()
        titles = {}

        for md_file in md_files:
            try:
                content = md_file.read_text(encoding='utf-8')
                # Extract first heading
                match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
                if match:
                    title = match.group(1).strip().lower()
                    if title not in titles:
                        titles[title] = []
                    titles[title].append(md_file)
            except Exception as e:
                continue

        duplicates = {title: files for title, files in titles.items() if len(files) > 1}

        if duplicates:
            for title, files in duplicates.items():
                self.print_warn(f"Duplicate title: '{title}'")
                for file in files:
                    try:
                        print(f"    → {file.relative_to(self.memory_path)}")
                    except UnicodeEncodeError:
                        print(f"    -> {file.relative_to(self.memory_path)}")
        else:
            self.print_ok("No duplicate titles found")

        return duplicates

    def check_hot_memory_age(self) -> List[Tuple[str, int]]:
        """Check if HOT memory entries are within 24h window"""
        self.print_section("Layer 1: HOT Memory Age Check")

        handoff = self.memory_path / "handoff.md"
        if not handoff.exists():
            self.print_info("handoff.md not found (HOT layer)")
            return []

        try:
            content = handoff.read_text(encoding='utf-8')
            # Extract timestamps (format: 2026-04-18 02:10)
            pattern = r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})'
            timestamps = re.findall(pattern, content)

            now = datetime.now()
            old_entries = []

            for ts_str in timestamps:
                try:
                    ts = datetime.strptime(ts_str, '%Y-%m-%d %H:%M')
                    age_hours = (now - ts).total_seconds() / 3600
                    if age_hours > 24:
                        old_entries.append((ts_str, int(age_hours)))
                except ValueError:
                    continue

            if old_entries:
                for ts, age in old_entries:
                    self.print_warn(f"HOT entry older than 24h: {ts} ({age}h old)")
                self.print_info("Consider rotating old entries to WARM layer")
            else:
                self.print_ok("All HOT entries within 24h window")

            return old_entries
        except Exception as e:
            self.print_warn(f"Could not check HOT memory age: {e}")
            return []

    def check_warm_memory_age(self) -> List[Tuple[str, int]]:
        """Check if WARM memory entries are within 14d window"""
        self.print_section("Layer 1: WARM Memory Age Check")

        decisions = self.memory_path / "decisions.md"
        if not decisions.exists():
            self.print_info("decisions.md not found (WARM layer)")
            return []

        try:
            content = decisions.read_text(encoding='utf-8')
            # Extract dates (format: 2026-04-18)
            pattern = r'(\d{4}-\d{2}-\d{2})'
            dates = re.findall(pattern, content)

            now = datetime.now()
            old_entries = []

            for date_str in dates:
                try:
                    date = datetime.strptime(date_str, '%Y-%m-%d')
                    age_days = (now - date).days
                    if age_days > 14:
                        old_entries.append((date_str, age_days))
                except ValueError:
                    continue

            if old_entries:
                for date, age in old_entries:
                    self.print_warn(f"WARM entry older than 14d: {date} ({age}d old)")
                self.print_info("Consider archiving old entries to COLD layer")
            else:
                self.print_ok("All WARM entries within 14d window")

            return old_entries
        except Exception as e:
            self.print_warn(f"Could not check WARM memory age: {e}")
            return []

    def check_file_sizes(self) -> Dict[Path, int]:
        """Check for unusually large files"""
        self.print_section("Layer 1: File Size Check")

        md_files = self.find_all_md_files()
        large_files = {}
        threshold = 100 * 1024  # 100KB

        for md_file in md_files:
            size = md_file.stat().st_size
            if size > threshold:
                large_files[md_file] = size

        if large_files:
            for file, size in large_files.items():
                self.print_warn(f"Large file: {file.name} ({size / 1024:.1f} KB)")
            self.print_info("Consider splitting large files into smaller chunks")
        else:
            self.print_ok("All files within reasonable size")

        return large_files

    def generate_report(self) -> Dict:
        """Generate lint report"""
        return {
            'timestamp': datetime.now().isoformat(),
            'memory_path': str(self.memory_path),
            'errors': len(self.errors),
            'warnings': len(self.warnings),
            'info': len(self.info),
            'details': {
                'errors': self.errors,
                'warnings': self.warnings,
                'info': self.info
            }
        }

    def run_layer1(self) -> bool:
        """Run Layer 1: Deterministic checks"""
        self.print_header("Memory Lint - Layer 1: Deterministic Checks")

        if not self.memory_path.exists():
            self.print_error(f"Memory directory not found: {self.memory_path}")
            return False

        self.print_ok(f"Memory directory: {self.memory_path}")

        # Run all checks
        self.check_ghost_links()
        self.check_orphan_files()
        self.check_duplicates()
        self.check_hot_memory_age()
        self.check_warm_memory_age()
        self.check_file_sizes()

        # Summary
        self.print_section("Layer 1 Summary")
        print(f"Errors: {Colors.RED}{len(self.errors)}{Colors.END}")
        print(f"Warnings: {Colors.YELLOW}{len(self.warnings)}{Colors.END}")
        print(f"Info: {Colors.CYAN}{len(self.info)}{Colors.END}")

        return len(self.errors) == 0

    def run_layer2_placeholder(self):
        """Placeholder for Layer 2: LLM-based semantic checks"""
        self.print_header("Memory Lint - Layer 2: Semantic Checks")
        self.print_info("Layer 2 (LLM-based checks) not yet implemented")
        self.print_info("Future checks:")
        print("  • Contradiction detection")
        print("  • Outdated claims detection")
        print("  • Consistency verification")
        print("  • Completeness analysis")

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Memory Lint System - Two-Layer Validation'
    )
    parser.add_argument(
        'memory_path',
        nargs='?',
        help='Path to memory directory (default: ~/.claude/memory)'
    )
    parser.add_argument(
        '--layer',
        choices=['1', '2', 'all'],
        default='all',
        help='Which layer to run (default: all)'
    )
    parser.add_argument(
        '--report',
        help='Save report to JSON file'
    )

    args = parser.parse_args()

    # Determine memory path
    if args.memory_path:
        memory_path = Path(args.memory_path)
    else:
        memory_path = Path.home() / ".claude" / "memory"

    # Run lint
    lint = MemoryLint(memory_path)

    if args.layer in ['1', 'all']:
        success = lint.run_layer1()

    if args.layer in ['2', 'all']:
        lint.run_layer2_placeholder()

    # Save report
    if args.report:
        report = lint.generate_report()
        with open(args.report, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2)
        print(f"\nReport saved: {args.report}")

    # Exit code
    sys.exit(0 if len(lint.errors) == 0 else 1)

if __name__ == '__main__':
    main()
