#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# pylint: disable=too-many-lines
"""
Memory Lint System - Two-Layer Validation
Inspired by llm-atomic-wiki's lint approach

Layer 1: Deterministic checks (ghost links, orphans, duplicates)
Layer 2: LLM-based semantic checks (contradictions, outdated claims)
"""

import argparse
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Set, Tuple

import yaml

# Add scripts/ for sibling-module imports and repo root for utils package
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import refactored checkers and utilities (after sys.path modification)
# pylint: disable=wrong-import-position,import-error
from antipattern_checkers import AntiPatternRegistry  # noqa: E402
from consistency_checkers import ConsistencyRegistry  # noqa: E402
from memory_lint_helpers import EncodingGate  # noqa: E402
from utils.base_reporter import BaseReporter  # noqa: E402
from utils.colors import Colors  # noqa: E402
# pylint: enable=wrong-import-position,import-error


class MemoryLint(BaseReporter):
    def __init__(self, memory_path: Path, quick_mode: bool = False):
        super().__init__()
        self.memory_path = memory_path
        self.quick_mode = quick_mode
        self.config = self._load_config()

    def clear_cache(self):
        """Clear all caches (call after file modifications)"""
        self.extract_links.cache_clear()
        self._extract_frontmatter.cache_clear()
        self._read_file_cached.cache_clear()

    def _read_file_safe(self, file_path: Path) -> str:
        """Safely read file content with error handling"""
        try:
            return file_path.read_text(encoding='utf-8')
        except Exception as exc:
            self.print_warn(f"Could not read {file_path.name}: {exc}")
            return ""

    def _read_files_parallel(self, files: List[Path], max_workers: int = 4) -> Dict[Path, str]:
        """Read multiple files in parallel"""
        results = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_file = {executor.submit(self._read_file_safe, f): f for f in files}
            for future in as_completed(future_to_file):
                file_path = future_to_file[future]
                content = future.result()
                if content:
                    results[file_path] = content
        return results

    def _load_config(self) -> dict:
        """Load configuration from config/memory_lint_config.yml"""
        config_path = Path(__file__).parent.parent / 'config' / 'memory_lint_config.yml'

        if not config_path.exists():
            # Fallback to default values
            return {
                'file_sizes': {'max_size': 102400},
                'age_thresholds': {
                    'hot_max_hours': 24,
                    'warm_max_days': 14,
                    'cold_max_days': 30
                }
            }

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as exc:
            self.print_warn(f"Could not load config: {exc}")
            return {
                'file_sizes': {'max_size': 102400},
                'age_thresholds': {
                    'hot_max_hours': 24,
                    'warm_max_days': 14,
                    'cold_max_days': 30
                }
            }

    def find_all_md_files(self) -> List[Path]:
        """Find all markdown files in memory directory with read access.

        ``Path.rglob`` itself can raise ``PermissionError`` / ``OSError`` if it
        descends into a directory the process can't read. Catch those and
        warn instead of crashing the whole lint run, so a single unreadable
        subtree doesn't block a multi-project sweep.
        """
        try:
            all_files = list(self.memory_path.rglob("*.md"))
        except (PermissionError, OSError) as err:
            self.print_warn(
                f"Could not enumerate markdown files under {self.memory_path}: {err}"
            )
            return []

        # Filter files with read access
        readable_files = [f for f in all_files if os.access(f, os.R_OK)]

        # Warn about inaccessible files
        inaccessible = len(all_files) - len(readable_files)
        if inaccessible > 0:
            self.print_warn(f"Skipped {inaccessible} file(s) without read access")

        return readable_files

    @lru_cache(maxsize=256)
    def extract_links(self, content: str) -> Set[str]:
        """Extract all markdown links from content (cached)"""
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
        """Check for links to non-existent files (parallel)"""
        self.print_section("Layer 1: Ghost Links Detection")

        ghost_links: Dict[Path, List[str]] = {}
        md_files = self.find_all_md_files()

        # Read all files in parallel
        file_contents = self._read_files_parallel(md_files)

        for md_file, content in file_contents.items():
            links = self.extract_links(content)

            for link in links:
                # Resolve relative path
                target = (md_file.parent / link).resolve()

                if not target.exists():
                    if md_file not in ghost_links:
                        ghost_links[md_file] = []
                    ghost_links[md_file].append(link)

        if ghost_links:
            for file, links_list in ghost_links.items():
                self.print_error(f"{file.name}: {len(links_list)} ghost link(s)")
                for link in links_list:
                    try:
                        print(f"    → {link}")
                    except UnicodeEncodeError:
                        print(f"    -> {link}")
        else:
            self.print_ok("No ghost links found")

        return ghost_links

    def check_orphan_files(self) -> List[Path]:
        """Check for files not linked from anywhere (parallel)"""
        self.print_section("Layer 1: Orphan Files Detection")

        md_files = self.find_all_md_files()
        all_links = set()

        # Read all files in parallel
        file_contents = self._read_files_parallel(md_files)

        # Collect all links
        for md_file, content in file_contents.items():
            links = self.extract_links(content)
            for link in links:
                target = (md_file.parent / link).resolve()
                all_links.add(target)

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
        """Check for duplicate content (parallel)"""
        self.print_section("Layer 1: Duplicate Detection")

        md_files = self.find_all_md_files()
        titles: Dict[str, List[Path]] = {}

        # Read all files in parallel
        file_contents = self._read_files_parallel(md_files)

        for md_file, content in file_contents.items():
            # Extract first heading
            match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
            if match:
                title = match.group(1).strip().lower()
                if title not in titles:
                    titles[title] = []
                titles[title].append(md_file)

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
                    max_hours = self.config['age_thresholds']['hot_max_hours']
                    if age_hours > max_hours:
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
                    max_days = self.config['age_thresholds']['warm_max_days']
                    if age_days > max_days:
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
        threshold = self.config['file_sizes']['max_size']

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

    # Publication status keywords (extracted as constants per Alisa's recommendation)
    PROJECT_KEYWORDS = ['project_status', 'publication', 'github', 'git']
    GIT_KEYWORDS = ['git', 'github', 'gitlab', 'remote', 'repository']
    PUBLICATION_KEYWORDS = ['публичн', 'приватн', 'public', 'private', 'опубликован']

    @lru_cache(maxsize=128)
    def _read_file_cached(self, file_path: Path) -> str:
        """Cached file reading with error handling (per Alisa's recommendation)"""
        try:
            return file_path.read_text(encoding='utf-8').lower()
        except Exception as exc:
            self.print_warn(f"Error reading {file_path.name}: {exc}")
            return ""

    def _has_project_status_in_filename(self, md_file: Path) -> bool:
        """Check if filename indicates project status"""
        return any(kw in md_file.name.lower() for kw in self.PROJECT_KEYWORDS)

    def _has_git_info_in_content(self, content: str) -> bool:
        """Check if content contains git information"""
        return any(kw in content for kw in self.GIT_KEYWORDS)

    def _has_publication_info_in_content(self, content: str) -> bool:
        """Check if content contains publication information"""
        return any(kw in content for kw in self.PUBLICATION_KEYWORDS)

    def check_project_publication_status(self) -> Dict[str, bool]:
        """Check if project publication status is documented in memory"""
        self.print_section("Layer 1: Project Publication Status Check")

        status = {
            'has_project_status': False,
            'has_git_info': False,
            'has_publication_info': False
        }

        md_files = self.find_all_md_files()

        for md_file in md_files:
            content = self._read_file_cached(md_file)
            if not content:
                continue

            # Check for project status indicators
            if self._has_project_status_in_filename(md_file):
                status['has_project_status'] = True

            if self._has_git_info_in_content(content):
                status['has_git_info'] = True

            if self._has_publication_info_in_content(content):
                status['has_publication_info'] = True

        # Report results
        self._report_publication_status(status)

        return status

    def _report_publication_status(self, status: Dict[str, bool]) -> None:
        """Report publication status findings"""
        if status['has_project_status'] and status['has_publication_info']:
            self.print_ok("Project publication status documented")
        elif status['has_git_info']:
            self.print_warn("Git info found, but publication status unclear")
            self.print_info("Consider creating project_publication_status.md")
        else:
            self.print_info("No git/publication info found (may be intentional)")

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
        if self.quick_mode:
            self.print_header("Memory Lint - Quick Check")
        else:
            self.print_header("Memory Lint - Layer 1: Deterministic Checks")

        if not self.memory_path.exists():
            self.print_error(f"Memory directory not found: {self.memory_path}")
            return False

        self.print_ok(f"Memory directory: {self.memory_path}")

        # Run checks (quick mode: only critical)
        self.check_ghost_links()

        if not self.quick_mode:
            self.check_orphan_files()
            self.check_duplicates()
            self.check_hot_memory_age()
            self.check_warm_memory_age()
            self.check_file_sizes()
            self.check_project_publication_status()

        # Summary
        if self.quick_mode:
            if len(self.errors) == 0:
                self.print_ok("Quick check passed")
            else:
                self.print_section("Quick Check Summary")
                print(f"Errors: {Colors.RED}{len(self.errors)}{Colors.END}")
        else:
            self.print_section("Layer 1 Summary")
            print(f"Errors: {Colors.RED}{len(self.errors)}{Colors.END}")
            print(f"Warnings: {Colors.YELLOW}{len(self.warnings)}{Colors.END}")
            print(f"Info: {Colors.CYAN}{len(self.info)}{Colors.END}")

        return len(self.errors) == 0

    def check_contradictions(self) -> List[Dict]:
        """Check for contradictions in memory content"""
        self.print_section("Layer 2: Contradiction Detection")

        md_files = self.find_all_md_files()

        # Collect all statements with context
        statements = []
        for md_file in md_files:
            try:
                content = md_file.read_text(encoding='utf-8')
                # Split into paragraphs
                paragraphs = [p.strip() for p in content.split('\n\n') if p.strip() and not p.startswith('#')]

                for para in paragraphs:
                    if len(para) > 50:  # Skip very short paragraphs
                        statements.append({
                            'file': md_file,
                            'text': para[:500]  # Limit length
                        })
            except Exception as exc:
                self.print_warn(f"Error reading {md_file.name}: {exc}")

        if len(statements) < 2:
            self.print_info("Not enough content for contradiction detection")
            return []

        self.print_info(f"Analyzing {len(statements)} statements for contradictions...")

        # Build prompt for LLM
        self._build_contradiction_prompt(statements)

        # For now, just show what would be checked
        self.print_info(f"Would analyze {len(statements)} statements")
        self.print_info("LLM integration required for actual detection")

        return []

    def _build_contradiction_prompt(self, statements: List[Dict]) -> str:
        """Build prompt for contradiction detection"""
        _ = statements  # Used in prompt building
        prompt = "Analyze these statements from memory files for contradictions:\n\n"

        for i, stmt in enumerate(statements[:20], 1):  # Limit to 20 for context
            prompt += f"{i}. [{stmt['file'].name}]\n{stmt['text']}\n\n"

        prompt += """
Find any contradictions between these statements. For each contradiction found, report:
1. Statement A (file and text)
2. Statement B (file and text)
3. Why they contradict
4. Severity (high/medium/low)

Format as JSON:
{
  "contradictions": [
    {
      "statement_a": {"file": "...", "text": "..."},
      "statement_b": {"file": "...", "text": "..."},
      "reason": "...",
      "severity": "high"
    }
  ]
}
"""
        return prompt

    def check_outdated_claims(self) -> List[Dict]:
        """Check for potentially outdated claims"""
        self.print_section("Layer 2: Outdated Claims Detection")

        md_files = self.find_all_md_files()
        now = datetime.now()

        # Find dated claims
        dated_claims = []
        for md_file in md_files:
            try:
                content = md_file.read_text(encoding='utf-8')

                # Find dates and surrounding context
                pattern = r'(\d{4}-\d{2}-\d{2})[^\n]*([^\n]+)'
                matches = re.finditer(pattern, content)

                for match in matches:
                    date_str = match.group(1)
                    context = match.group(2)

                    try:
                        date = datetime.strptime(date_str, '%Y-%m-%d')
                        age_days = (now - date).days
                        max_days = self.config['age_thresholds']['cold_max_days']

                        if age_days > max_days:  # Claims older than configured threshold
                            dated_claims.append({
                                'file': md_file,
                                'date': date_str,
                                'age_days': age_days,
                                'context': context[:200]
                            })
                    except ValueError:
                        continue
            except Exception as exc:
                self.print_warn(f"Error reading {md_file.name}: {exc}")

        if dated_claims:
            self.print_info(f"Found {len(dated_claims)} claims older than 30 days")
            self.print_info("LLM would verify if these are still valid")

            # Show sample
            for claim in dated_claims[:3]:
                claim_file = claim['file']
                if isinstance(claim_file, Path):
                    file_name = claim_file.name
                else:
                    file_name = str(claim_file)
                self.print_warn(f"{file_name}: {claim['date']} ({claim['age_days']}d old)")
        else:
            self.print_ok("No old claims found")

        return dated_claims

    def check_consistency(self) -> List[Dict]:
        """Check for inconsistent terminology"""
        self.print_section("Layer 2: Consistency Verification")

        md_files = self.find_all_md_files()

        # Use refactored checker registry
        registry = ConsistencyRegistry()
        results = registry.check_all(md_files)

        inconsistencies = results.get('terminology', [])

        # Report findings
        self._report_inconsistencies(inconsistencies)

        return inconsistencies

    def _report_inconsistencies(self, inconsistencies: List[Dict]) -> None:
        """Report terminology inconsistencies"""
        if not inconsistencies:
            self.print_ok("Terminology is consistent")
            return

        for incon in inconsistencies:
            self.print_warn(f"Inconsistent terminology: {incon['base_term']}")
            variants_dict = incon['variants']
            if isinstance(variants_dict, dict):
                for variant, count in variants_dict.items():
                    print(f"    - '{variant}' ({count} occurrences)")
            print(f"    Suggest: standardize to '{incon['base_term']}'")

    def check_completeness(self) -> List[Dict]:
        """Check for incomplete documentation"""
        self.print_section("Layer 2: Completeness Analysis")

        md_files = self.find_all_md_files()

        incomplete = []

        # Check for common incompleteness markers
        markers = [
            'TODO', 'FIXME', 'XXX', 'HACK', 'NOTE:',
            'not yet', 'coming soon', 'to be added',
            'placeholder', 'stub', 'incomplete'
        ]

        for md_file in md_files:
            try:
                content = md_file.read_text(encoding='utf-8')

                for marker in markers:
                    if marker.lower() in content.lower():
                        # Find context
                        lines = content.split('\n')
                        for i, line in enumerate(lines):
                            if marker.lower() in line.lower():
                                incomplete.append({
                                    'file': md_file,
                                    'marker': marker,
                                    'line': i + 1,
                                    'context': line.strip()[:100]
                                })
                                break
            except Exception as exc:
                self.print_warn(f"Error reading {md_file.name}: {exc}")

        if incomplete:
            self.print_warn(f"Found {len(incomplete)} incomplete sections")
            for item in incomplete[:5]:  # Show first 5
                item_file = item['file']
                if isinstance(item_file, Path):
                    file_name = item_file.name
                else:
                    file_name = str(item_file)
                print(f"    {file_name}:{item['line']} - {item['marker']}")
        else:
            self.print_ok("No obvious incomplete sections found")

        return incomplete

    def check_antipatterns(self) -> List[Dict]:
        """Check for memory anti-patterns (inspired by UI/UX Pro Max)"""
        self.print_section("Layer 2: Anti-patterns Detection")

        md_files = self.find_all_md_files()
        antipatterns = []

        # Use refactored checker registry
        registry = AntiPatternRegistry()

        for md_file in md_files:
            try:
                content = md_file.read_text(encoding='utf-8')
                frontmatter = self._extract_frontmatter(content)

                # Run all checkers
                results = registry.check_all(md_file, content, frontmatter)
                antipatterns.extend(results)

            except Exception as exc:
                self.print_warn(f"Error checking {md_file.name}: {exc}")

        # Report findings
        self._report_antipatterns(antipatterns)

        return antipatterns

    def _report_antipatterns(self, antipatterns: List[Dict]) -> None:
        """Report anti-pattern findings"""
        if not antipatterns:
            self.print_ok("No anti-patterns detected")
            return

        severity_counts: Dict[str, int] = {'high': 0, 'medium': 0, 'low': 0}
        for ap in antipatterns:
            severity = str(ap['severity'])
            severity_counts[severity] += 1

        self.print_warn(f"Found {len(antipatterns)} anti-pattern(s)")
        print(f"    High: {severity_counts['high']}, "
              f"Medium: {severity_counts['medium']}, Low: {severity_counts['low']}")

        # Show high severity first
        for ap in sorted(antipatterns,
                       key=lambda x: {'high': 0, 'medium': 1, 'low': 2}[str(x['severity'])]):
            ap_file = ap['file']
            if isinstance(ap_file, Path):
                file_name = ap_file.name
            else:
                file_name = str(ap_file)

            severity_color = {
                'high': Colors.RED,
                'medium': Colors.YELLOW,
                'low': Colors.BLUE
            }.get(str(ap['severity']), '')

            print(f"    {severity_color}[{ap['severity'].upper()}]{Colors.RESET} "
                  f"{file_name}: {ap['message']}")

    @lru_cache(maxsize=256)
    def _extract_frontmatter(self, content: str) -> Dict[str, str]:
        """Extract YAML frontmatter from markdown content (cached)"""
        frontmatter = {}

        # Match frontmatter between --- markers
        match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
        if match:
            yaml_content = match.group(1)
            # Simple YAML parsing (key: value)
            for line in yaml_content.split('\n'):
                if ':' in line:
                    key, value = line.split(':', 1)
                    frontmatter[key.strip()] = value.strip()

        return frontmatter

    def _check_duplicate_memories(self) -> bool:
        """Check 1: No duplicate memories"""
        self.print_section("[ ] No duplicate memories")
        duplicates = self.check_duplicates()
        if duplicates:
            self.print_error(f"[X] Found {len(duplicates)} duplicate(s)")
            return False
        self.print_ok("[OK] No duplicates")
        return True

    def _check_all_links_valid(self) -> bool:
        """Check 2: All links valid"""
        self.print_section("[ ] All links valid (no ghost links)")
        ghost_links = self.check_ghost_links()
        if ghost_links:
            self.print_error(f"[X] Found {len(ghost_links)} ghost link(s)")
            return False
        self.print_ok("[OK] All links valid")
        return True

    def _check_frontmatter_complete(self) -> bool:
        """Check 3: Frontmatter complete"""
        self.print_section("[ ] Frontmatter complete (name, description, type)")
        md_files = self.find_all_md_files()
        incomplete_frontmatter = []

        for md_file in md_files:
            if md_file.name in ['MEMORY.md', 'handoff.md', 'decisions.md', 'README.md']:
                continue

            try:
                content = md_file.read_text(encoding='utf-8')
                frontmatter = self._extract_frontmatter(content)
                required_fields = ['name', 'description', 'type']
                missing = [f for f in required_fields if f not in frontmatter or not frontmatter[f]]

                if missing:
                    incomplete_frontmatter.append((md_file, missing))
            except Exception as exc:
                self.print_warn(f"Error checking {md_file.name}: {exc}")

        if incomplete_frontmatter:
            self.print_error(f"[X] {len(incomplete_frontmatter)} file(s) with incomplete frontmatter")
            for file, missing in incomplete_frontmatter[:3]:
                print(f"    {file.name}: missing {', '.join(missing)}")
            return False
        self.print_ok("[OK] All frontmatter complete")
        return True

    def _check_hot_memory_fresh(self) -> bool:
        """Check 4: HOT memory within 24h window"""
        self.print_section("[ ] HOT memory within 24h window")
        old_hot = self.check_hot_memory_age()
        if old_hot:
            self.print_error(f"[X] {len(old_hot)} old HOT entries")
            return False
        self.print_ok("[OK] HOT memory fresh")
        return True

    def _check_warm_memory_fresh(self) -> bool:
        """Check 5: WARM memory within 14d window"""
        self.print_section("[ ] WARM memory within 14d window")
        old_warm = self.check_warm_memory_age()
        if old_warm:
            self.print_error(f"[X] {len(old_warm)} old WARM entries")
            return False
        self.print_ok("[OK] WARM memory fresh")
        return True

    def _check_file_sizes_ok(self) -> bool:
        """Check 6: File sizes < 100KB"""
        self.print_section("[ ] File size < 100KB")
        large_files = self.check_file_sizes()
        if large_files:
            self.print_error(f"[X] {len(large_files)} large file(s)")
            return False
        self.print_ok("[OK] All files within size limit")
        return True

    def _check_why_how_present(self) -> bool:
        """Check 7: Why:/How to apply: sections present"""
        self.print_section("[ ] Why:/How to apply: sections present (feedback/project)")
        md_files = self.find_all_md_files()
        missing_why_how = []

        for md_file in md_files:
            try:
                content = md_file.read_text(encoding='utf-8')
                frontmatter = self._extract_frontmatter(content)
                memory_type = frontmatter.get('type', '')

                if memory_type in ['feedback', 'project']:
                    if '**Why:**' not in content or '**How to apply:**' not in content:
                        missing_why_how.append(md_file)
            except Exception as exc:
                self.print_warn(f"Error checking {md_file.name}: {exc}")

        if missing_why_how:
            self.print_error(f"[X] {len(missing_why_how)} file(s) missing Why:/How to apply:")
            for file in missing_why_how[:3]:
                print(f"    {file.name}")
            return False
        self.print_ok("[OK] All feedback/project files have Why:/How to apply:")
        return True

    def pre_delivery_checklist(self) -> Dict[str, bool]:
        """
        Pre-Delivery Checklist - Quick validation before commit
        Inspired by UI/UX Pro Max pre-delivery checklist pattern
        """
        self.print_header("Pre-Delivery Checklist")

        checklist = {
            'no_duplicate_memories': self._check_duplicate_memories(),
            'all_links_valid': self._check_all_links_valid(),
            'frontmatter_complete': self._check_frontmatter_complete(),
            'hot_memory_fresh': self._check_hot_memory_fresh(),
            'warm_memory_fresh': self._check_warm_memory_fresh(),
            'file_sizes_ok': self._check_file_sizes_ok(),
            'why_how_present': self._check_why_how_present()
        }

        # Final summary
        self.print_section("Pre-Delivery Summary")
        passed = sum(1 for v in checklist.values() if v)
        total = len(checklist)

        if passed == total:
            self.print_ok(f"[OK] All checks passed ({passed}/{total})")
            print(f"\n{Colors.GREEN}[OK] Ready for commit!{Colors.END}\n")
        else:
            failed = total - passed
            self.print_error(f"[X] {failed} check(s) failed ({passed}/{total} passed)")
            print(f"\n{Colors.RED}[X] Fix issues before commit{Colors.END}\n")

        return checklist

    def run_layer2(self) -> bool:
        """Run Layer 2: LLM-based semantic checks"""
        self.print_header("Memory Lint - Layer 2: Semantic Checks")

        if not self.memory_path.exists():
            self.print_error(f"Memory directory not found: {self.memory_path}")
            return False

        # Run semantic checks
        contradictions = self.check_contradictions()
        outdated = self.check_outdated_claims()
        inconsistencies = self.check_consistency()
        incomplete = self.check_completeness()
        antipatterns = self.check_antipatterns()

        # Summary
        self.print_section("Layer 2 Summary")
        print(f"Contradictions: {len(contradictions)}")
        print(f"Outdated claims: {len(outdated)}")
        print(f"Inconsistencies: {len(inconsistencies)}")
        print(f"Incomplete sections: {len(incomplete)}")
        print(f"Anti-patterns: {len(antipatterns)}")

        return True

def _safe_rglob_md(memory_path: Path) -> List[Path]:
    """Sorted ``*.md`` walk of ``memory_path`` that tolerates unreadable subtrees.

    Mirrors ``MemoryLint.find_all_md_files()`` (lines 108-114): any
    ``PermissionError`` / ``OSError`` raised while expanding ``rglob``
    is downgraded to a stderr warning so the rest of the audit can
    still proceed.
    """
    try:
        return sorted(memory_path.rglob('*.md'))
    except (PermissionError, OSError) as exc:
        print(
            f"Warning: could not fully walk {memory_path}: {exc}",
            file=sys.stderr,
        )
        return []


def _run_encoding_validation(memory_path: Path) -> int:
    """Walk ``memory_path`` and report any markdown file with mojibake.

    Returns 0 if every ``*.md`` file under ``memory_path`` is clean
    UTF-8 with no cp1251-as-utf8 mojibake markers, otherwise 1. Used
    by ``memory_lint --validate-encoding``.
    """
    if not memory_path.exists():
        print(f"Memory path does not exist: {memory_path}", file=sys.stderr)
        return 1
    issues: List[Tuple[Path, str]] = []
    for md_file in _safe_rglob_md(memory_path):
        issue = EncodingGate.scan_file(md_file)
        if issue is not None:
            issues.append((md_file, issue))
    if not issues:
        print(f"Encoding validation passed: no mojibake in {memory_path}")
        return 0
    print(
        f"Encoding validation FAILED: {len(issues)} file(s) under "
        f"{memory_path} contain encoding corruption.",
        file=sys.stderr,
    )
    for path, issue in issues:
        try:
            rel = path.relative_to(memory_path)
        except ValueError:
            rel = path
        print(f"  {rel}: {issue}", file=sys.stderr)
    print(
        "\nRun ``memory_lint --repair-mojibake`` to preview a fix, "
        "or ``--repair-mojibake --apply`` to apply it.",
        file=sys.stderr,
    )
    return 1


def _run_encoding_repair(memory_path: Path, *, apply: bool) -> int:
    """Walk ``memory_path`` and attempt to repair every mojibake'd file.

    Args:
        memory_path: Directory to scan for ``*.md`` files.
        apply: If True, overwrite the original file in place (after
            saving a ``<file>.bak`` copy). If False, write the
            repaired content next to the original as ``<file>.fixed``
            so the user can diff before applying.

    Returns:
        0 if every corrupted file was successfully repaired (or the
        directory was already clean). 1 if at least one file could
        not be repaired automatically (mixed double-encoding,
        unsupported codepoints, etc.) — those are listed and need
        manual review.
    """
    if not memory_path.exists():
        print(f"Memory path does not exist: {memory_path}", file=sys.stderr)
        return 1
    repaired_paths: List[Path] = []
    skipped_clean: List[Path] = []
    failed: List[Tuple[Path, str]] = []
    for md_file in _safe_rglob_md(memory_path):
        issue = EncodingGate.scan_file(md_file)
        if issue is None:
            skipped_clean.append(md_file)
            continue
        try:
            text = md_file.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError) as exc:
            failed.append((md_file, f"unreadable: {exc}"))
            continue
        recovered, ok = EncodingGate.repair_mojibake(text)
        if not ok:
            failed.append((md_file, f"could not repair: {issue}"))
            continue
        if apply:
            backup = md_file.with_suffix(md_file.suffix + '.bak')
            md_file.replace(backup)
            md_file.write_text(recovered, encoding='utf-8')
        else:
            preview = md_file.with_suffix(md_file.suffix + '.fixed')
            preview.write_text(recovered, encoding='utf-8')
        repaired_paths.append(md_file)
    print(
        f"Encoding repair scan complete in {memory_path}:\n"
        f"  clean: {len(skipped_clean)}\n"
        f"  repaired: {len(repaired_paths)}\n"
        f"  manual-review: {len(failed)}"
    )
    for path in repaired_paths:
        try:
            rel = path.relative_to(memory_path)
        except ValueError:
            rel = path
        suffix = ".bak (original)" if apply else ".fixed (preview)"
        print(f"  REPAIRED: {rel}  ->  {rel}{suffix}")
    if failed:
        print("\nManual review required for these files:", file=sys.stderr)
        for path, reason in failed:
            try:
                rel = path.relative_to(memory_path)
            except ValueError:
                rel = path
            print(f"  {rel}: {reason}", file=sys.stderr)
        return 1
    return 0


def main():
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
    parser.add_argument(
        '--quick',
        action='store_true',
        help='Quick mode: only critical checks (ghost links, errors)'
    )
    parser.add_argument(
        '--checklist',
        action='store_true',
        help='Run pre-delivery checklist (all critical checks before commit)'
    )
    parser.add_argument(
        '--validate-encoding',
        action='store_true',
        help=(
            'Scan every markdown file for cp1251-as-utf8 mojibake or '
            'replacement characters and exit non-zero if any are found. '
            'Use this on the existing tree before / after deploys to '
            'catch corruption introduced by Windows write hooks.'
        )
    )
    parser.add_argument(
        '--repair-mojibake',
        action='store_true',
        help=(
            'Walk the memory tree and try to invert cp1251-as-utf8 '
            'mojibake on every corrupted markdown file. By default '
            'writes recovered text to ``<file>.fixed`` next to the '
            'original; pass --apply to overwrite the original (with '
            'a ``<file>.bak`` rescue copy). Always lists files that '
            'could NOT be repaired automatically and require manual '
            'review.'
        )
    )
    parser.add_argument(
        '--apply',
        action='store_true',
        help=(
            'Modifier for --repair-mojibake: actually overwrite the '
            'original file (after saving ``<file>.bak``) instead of '
            'producing a side-by-side ``<file>.fixed`` for review.'
        )
    )

    args = parser.parse_args()

    # ``--apply`` is only meaningful in combination with
    # ``--repair-mojibake`` (it switches the repair mode from
    # ``.fixed`` preview to in-place rewrite). Reject the
    # combination explicitly so users don't get silently-ignored
    # flags.
    if args.apply and not args.repair_mojibake:
        parser.error("--apply requires --repair-mojibake")

    # Determine memory path
    if args.memory_path:
        memory_path = Path(args.memory_path)
    else:
        memory_path = Path.home() / ".claude" / "memory"

    # Encoding validation is independent of the layered lint flow:
    # it walks the tree once and reports without instantiating the
    # full MemoryLint pipeline.
    if args.validate_encoding:
        sys.exit(_run_encoding_validation(memory_path))

    if args.repair_mojibake:
        sys.exit(_run_encoding_repair(memory_path, apply=args.apply))

    # Run lint
    lint = MemoryLint(memory_path, quick_mode=args.quick)

    # Pre-delivery checklist mode
    if args.checklist:
        checklist = lint.pre_delivery_checklist()
        all_passed = all(checklist.values())
        sys.exit(0 if all_passed else 1)

    if args.layer in ['1', 'all']:
        lint.run_layer1()

    if args.layer in ['2', 'all'] and not args.quick:
        lint.run_layer2()

    # Save report
    if args.report:
        import json  # pylint: disable=import-outside-toplevel
        report = lint.generate_report()
        with open(args.report, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2)
        print(f"\nReport saved: {args.report}")

    # Exit code
    sys.exit(0 if len(lint.errors) == 0 else 1)


if __name__ == '__main__':
    main()
