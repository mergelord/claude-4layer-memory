#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Memory Lint System - Two-Layer Validation
Inspired by llm-atomic-wiki's lint approach

Layer 1: Deterministic checks (ghost links, orphans, duplicates)
Layer 2: LLM-based semantic checks (contradictions, outdated claims)
"""

import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple

# Add parent directory to path for utils import
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.base_reporter import \
    BaseReporter  # pylint: disable=wrong-import-position
from utils.colors import Colors  # pylint: disable=wrong-import-position


class MemoryLint(BaseReporter):
    def __init__(self, memory_path: Path, quick_mode: bool = False):
        super().__init__()
        self.memory_path = memory_path
        self.quick_mode = quick_mode

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

        ghost_links: Dict[Path, List[str]] = {}
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
            except Exception as exc:
                self.print_warn(f"Could not read {md_file.name}: {exc}")

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
            except Exception as exc:
                self.print_warn(f"Error reading {md_file.name}: {exc}")

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
        titles: Dict[str, List[Path]] = {}

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
            except Exception as exc:
                self.print_warn(f"Error reading {md_file.name}: {exc}")

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

    def check_project_publication_status(self) -> Dict[str, bool]:
        """Check if project publication status is documented in memory"""
        self.print_section("Layer 1: Project Publication Status Check")

        status = {
            'has_project_status': False,
            'has_git_info': False,
            'has_publication_info': False
        }

        md_files = self.find_all_md_files()

        # Ищем файлы со статусом проекта
        project_keywords = ['project_status', 'publication', 'github', 'git']
        git_keywords = ['git', 'github', 'gitlab', 'remote', 'repository']
        publication_keywords = ['публичн', 'приватн', 'public', 'private', 'опубликован']

        for md_file in md_files:
            try:
                content = md_file.read_text(encoding='utf-8').lower()

                # Проверяем наличие информации о статусе проекта
                if any(kw in md_file.name.lower() for kw in project_keywords):
                    status['has_project_status'] = True

                # Проверяем наличие git информации
                if any(kw in content for kw in git_keywords):
                    status['has_git_info'] = True

                # Проверяем наличие информации о публикации
                if any(kw in content for kw in publication_keywords):
                    status['has_publication_info'] = True

            except Exception as exc:
                self.print_warn(f"Error reading {md_file.name}: {exc}")

        # Оценка результатов
        if status['has_project_status'] and status['has_publication_info']:
            self.print_ok("Project publication status documented")
        elif status['has_git_info']:
            self.print_warn("Git info found, but publication status unclear")
            self.print_info("Consider creating project_publication_status.md")
        else:
            self.print_info("No git/publication info found (may be intentional)")

        return status

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

                        if age_days > 30:  # Claims older than 30 days
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

        # Common inconsistencies to check
        term_variants = {
            'autopilot': ['auto-pilot', 'auto pilot', 'AP', 'A/P'],
            'SimConnect': ['simconnect', 'sim-connect', 'sim connect'],
            'WASM': ['wasm', 'WebAssembly', 'web assembly'],
        }

        inconsistencies = []

        for base_term, variants in term_variants.items():
            counts = {base_term: 0}
            for variant in variants:
                counts[variant] = 0

            # Count occurrences
            for md_file in md_files:
                try:
                    content = md_file.read_text(encoding='utf-8').lower()

                    for term in [base_term] + variants:
                        counts[term] += content.count(term.lower())
                except Exception as exc:
                    self.print_warn(f"Error reading {md_file.name}: {exc}")

            # Check if multiple variants used
            used_variants = {k: v for k, v in counts.items() if v > 0}
            if len(used_variants) > 1:
                inconsistencies.append({
                    'base_term': base_term,
                    'variants': used_variants
                })

        if inconsistencies:
            for incon in inconsistencies:
                self.print_warn(f"Inconsistent terminology: {incon['base_term']}")
                variants_dict = incon['variants']
                if isinstance(variants_dict, dict):
                    for variant, count in variants_dict.items():
                        print(f"    - '{variant}' ({count} occurrences)")
                print(f"    Suggest: standardize to '{incon['base_term']}'")
        else:
            self.print_ok("Terminology is consistent")

        return inconsistencies

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

        for md_file in md_files:
            try:
                content = md_file.read_text(encoding='utf-8')

                # Extract frontmatter
                frontmatter = self._extract_frontmatter(content)
                memory_type = frontmatter.get('type', '')

                # Anti-pattern 1: Missing Why:/How to apply: in feedback/project types
                if memory_type in ['feedback', 'project']:
                    if '**Why:**' not in content and '**How to apply:**' not in content:
                        antipatterns.append({
                            'file': md_file,
                            'type': 'missing_why_how',
                            'severity': 'high',
                            'message': f'{memory_type} memory missing Why:/How to apply: sections'
                        })

                # Anti-pattern 2: Code snippets in memory (should be in codebase)
                code_blocks = re.findall(r'```[\s\S]*?```', content)
                if len(code_blocks) > 3:
                    antipatterns.append({
                        'file': md_file,
                        'type': 'excessive_code',
                        'severity': 'medium',
                        'message': f'{len(code_blocks)} code blocks - consider storing in codebase'
                    })

                # Anti-pattern 3: Vague descriptions (too generic)
                description = frontmatter.get('description', '')
                vague_words = ['stuff', 'things', 'various', 'some', 'etc', 'and so on']
                if any(word in description.lower() for word in vague_words):
                    antipatterns.append({
                        'file': md_file,
                        'type': 'vague_description',
                        'severity': 'low',
                        'message': 'Description contains vague words - be more specific'
                    })

                # Anti-pattern 4: Temporary data in WARM/COLD layers
                temp_markers = ['temp', 'temporary', 'draft', 'wip', 'work in progress']
                if (md_file.name not in ['handoff.md'] and
                        any(marker in content.lower() for marker in temp_markers)):
                    antipatterns.append({
                        'file': md_file,
                        'type': 'temporary_in_permanent',
                        'severity': 'medium',
                        'message': 'Temporary data in permanent layer - should be in HOT'
                    })

                # Anti-pattern 5: Outdated claims without dates
                claim_words = ['currently', 'now', 'today', 'recently', 'latest']
                has_claims = any(word in content.lower() for word in claim_words)
                has_dates = bool(re.search(r'\d{4}-\d{2}-\d{2}', content))

                if has_claims and not has_dates:
                    antipatterns.append({
                        'file': md_file,
                        'type': 'undated_claims',
                        'severity': 'medium',
                        'message': 'Time-sensitive claims without dates - add timestamps'
                    })

                # Anti-pattern 6: Duplicate information from git history
                git_markers = ['commit', 'merged', 'pull request', 'pr #', 'issue #']
                if sum(1 for marker in git_markers if marker in content.lower()) > 3:
                    antipatterns.append({
                        'file': md_file,
                        'type': 'git_duplication',
                        'severity': 'low',
                        'message': 'Duplicates git history - use git log instead'
                    })

            except Exception as exc:
                self.print_warn(f"Error checking {md_file.name}: {exc}")

        # Report findings
        if antipatterns:
            severity_counts: Dict[str, int] = {'high': 0, 'medium': 0, 'low': 0}
            for ap in antipatterns:
                severity = str(ap['severity'])  # Ensure string type
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

                severity = str(ap['severity'])  # Ensure string type for dict access
                severity_color = {
                    'high': Colors.RED,
                    'medium': Colors.YELLOW,
                    'low': Colors.CYAN
                }[severity]

                print(f"    {severity_color}[{severity.upper()}]{Colors.END} "
                      f"{file_name}: {ap['message']}")
        else:
            self.print_ok("No anti-patterns detected")

        return antipatterns

    def _extract_frontmatter(self, content: str) -> Dict[str, str]:
        """Extract YAML frontmatter from markdown content"""
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

    def pre_delivery_checklist(self) -> Dict[str, bool]:
        """
        Pre-Delivery Checklist - Quick validation before commit
        Inspired by UI/UX Pro Max pre-delivery checklist pattern
        """
        self.print_header("Pre-Delivery Checklist")

        checklist = {
            'no_duplicate_memories': True,
            'all_links_valid': True,
            'frontmatter_complete': True,
            'hot_memory_fresh': True,
            'warm_memory_fresh': True,
            'file_sizes_ok': True,
            'why_how_present': True
        }

        # Check 1: No duplicate memories
        self.print_section("[ ] No duplicate memories")
        duplicates = self.check_duplicates()
        if duplicates:
            checklist['no_duplicate_memories'] = False
            self.print_error(f"[X] Found {len(duplicates)} duplicate(s)")
        else:
            self.print_ok("[OK] No duplicates")

        # Check 2: All links valid
        self.print_section("[ ] All links valid (no ghost links)")
        ghost_links = self.check_ghost_links()
        if ghost_links:
            checklist['all_links_valid'] = False
            self.print_error(f"[X] Found {len(ghost_links)} ghost link(s)")
        else:
            self.print_ok("[OK] All links valid")

        # Check 3: Frontmatter complete
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
            checklist['frontmatter_complete'] = False
            self.print_error(f"[X] {len(incomplete_frontmatter)} file(s) with incomplete frontmatter")
            for file, missing in incomplete_frontmatter[:3]:
                print(f"    {file.name}: missing {', '.join(missing)}")
        else:
            self.print_ok("[OK] All frontmatter complete")

        # Check 4: HOT memory within 24h window
        self.print_section("[ ] HOT memory within 24h window")
        old_hot = self.check_hot_memory_age()
        if old_hot:
            checklist['hot_memory_fresh'] = False
            self.print_error(f"[X] {len(old_hot)} old HOT entries")
        else:
            self.print_ok("[OK] HOT memory fresh")

        # Check 5: WARM memory within 14d window
        self.print_section("[ ] WARM memory within 14d window")
        old_warm = self.check_warm_memory_age()
        if old_warm:
            checklist['warm_memory_fresh'] = False
            self.print_error(f"[X] {len(old_warm)} old WARM entries")
        else:
            self.print_ok("[OK] WARM memory fresh")

        # Check 6: File sizes < 100KB
        self.print_section("[ ] File size < 100KB")
        large_files = self.check_file_sizes()
        if large_files:
            checklist['file_sizes_ok'] = False
            self.print_error(f"[X] {len(large_files)} large file(s)")
        else:
            self.print_ok("[OK] All files within size limit")

        # Check 7: Why:/How to apply: sections present
        self.print_section("[ ] Why:/How to apply: sections present (feedback/project)")
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
            checklist['why_how_present'] = False
            self.print_error(f"[X] {len(missing_why_how)} file(s) missing Why:/How to apply:")
            for file in missing_why_how[:3]:
                print(f"    {file.name}")
        else:
            self.print_ok("[OK] All feedback/project files have Why:/How to apply:")

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

    args = parser.parse_args()

    # Determine memory path
    if args.memory_path:
        memory_path = Path(args.memory_path)
    else:
        memory_path = Path.home() / ".claude" / "memory"

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
