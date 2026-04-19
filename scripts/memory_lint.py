#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Memory Lint System - Two-Layer Validation
Inspired by llm-atomic-wiki's lint approach

Layer 1: Deterministic checks (ghost links, orphans, duplicates)
Layer 2: LLM-based semantic checks (contradictions, outdated claims)
"""

import sys
from pathlib import Path
import re
from datetime import datetime
from typing import List, Dict, Set, Tuple

# Add parent directory to path for utils import
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.colors import Colors  # pylint: disable=wrong-import-position

class MemoryLint:
    def __init__(self, memory_path: Path, quick_mode: bool = False):
        self.memory_path = memory_path
        self.quick_mode = quick_mode
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []

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

        # Summary
        self.print_section("Layer 2 Summary")
        print(f"Contradictions: {len(contradictions)}")
        print(f"Outdated claims: {len(outdated)}")
        print(f"Inconsistencies: {len(inconsistencies)}")
        print(f"Incomplete sections: {len(incomplete)}")

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

    args = parser.parse_args()

    # Determine memory path
    if args.memory_path:
        memory_path = Path(args.memory_path)
    else:
        memory_path = Path.home() / ".claude" / "memory"

    # Run lint
    lint = MemoryLint(memory_path, quick_mode=args.quick)

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
