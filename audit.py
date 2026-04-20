#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claude 4-Layer Memory System - Pre-Installation Audit
Analyzes current Claude Code setup and provides recommendations
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# Add current directory to path for utils import
sys.path.insert(0, str(Path(__file__).parent))
from utils.base_reporter import \
    BaseReporter  # pylint: disable=wrong-import-position
from utils.colors import Colors  # pylint: disable=wrong-import-position


class PreInstallAudit(BaseReporter):
    def __init__(self):
        super().__init__()
        self.home = Path.home()
        self.claude_dir = self.home / ".claude"
        self.issues = self.errors  # Alias for compatibility
        self.stats = {}

    def check_claude_installation(self):
        """Check if Claude Code is installed"""
        self.print_section("Claude Code Installation")

        if not self.claude_dir.exists():
            self.print_error(f"Claude Code directory not found: {self.claude_dir}")
            self.print_info("Please install Claude Code first")
            return False

        self.print_ok(f"Claude Code directory found: {self.claude_dir}")

        # Check hooks directory
        hooks_dir = self.claude_dir / "hooks"
        if hooks_dir.exists():
            hook_count = len(list(hooks_dir.glob("*")))
            self.print_ok(f"Hooks directory exists ({hook_count} files)")
            self.stats['existing_hooks'] = hook_count
        else:
            self.print_warn("Hooks directory not found (will be created)")
            self.stats['existing_hooks'] = 0

        return True

    def analyze_memory_structure(self):
        """Analyze existing memory structure"""
        self.print_section("Current Memory Structure")

        memory_dir = self.claude_dir / "memory"

        if not memory_dir.exists():
            self.print_info("No existing memory directory (will be created)")
            self.stats['has_memory'] = False
            return

        self.stats['has_memory'] = True
        self.print_ok(f"Memory directory exists: {memory_dir}")

        # Check for existing memory files
        memory_files = {
            'MEMORY.md': 'Memory index',
            'handoff.md': 'HOT layer (24h)',
            'decisions.md': 'WARM layer (14d)',
        }

        existing_files = []
        for filename, description in memory_files.items():
            filepath = memory_dir / filename
            if filepath.exists():
                size = filepath.stat().st_size
                existing_files.append(filename)
                self.print_ok(f"{filename} exists ({size} bytes) - {description}")
            else:
                self.print_info(f"{filename} not found - {description}")

        self.stats['existing_memory_files'] = existing_files

        # Check archive
        archive_dir = memory_dir / "archive"
        if archive_dir.exists():
            archive_count = len(list(archive_dir.rglob("*.md")))
            self.print_ok(f"Archive directory exists ({archive_count} files)")
            self.stats['archive_files'] = archive_count
        else:
            self.print_info("No archive directory")
            self.stats['archive_files'] = 0

        # Scan all .md files
        all_md_files = list(memory_dir.rglob("*.md"))
        self.stats['total_memory_files'] = len(all_md_files)
        self.print_info(f"Total memory files: {len(all_md_files)}")

        # Calculate total size
        total_size = sum(f.stat().st_size for f in all_md_files)
        self.stats['total_memory_size'] = total_size
        self.print_info(f"Total memory size: {total_size / 1024:.1f} KB")

    def analyze_projects(self):
        """Analyze existing projects"""
        self.print_section("Existing Projects")

        projects_dir = self.claude_dir / "projects"

        if not projects_dir.exists():
            self.print_info("No projects directory (will be created)")
            self.stats['project_count'] = 0
            return

        # Find all project directories
        project_dirs = [d for d in projects_dir.iterdir() if d.is_dir()]
        self.stats['project_count'] = len(project_dirs)

        if not project_dirs:
            self.print_info("No existing projects found")
            return

        self.print_ok(f"Found {len(project_dirs)} project directories")

        # Analyze each project
        projects_with_memory = []
        for project_dir in project_dirs:
            memory_path = project_dir / "memory"
            if memory_path.exists():
                md_count = len(list(memory_path.rglob("*.md")))
                projects_with_memory.append(project_dir.name)
                self.print_ok(f"  {project_dir.name} ({md_count} memory files)")
            else:
                self.print_warn(f"  {project_dir.name} (no memory directory)")

        self.stats['projects_with_memory'] = len(projects_with_memory)

    def check_global_projects_file(self):
        """Check for GLOBAL_PROJECTS.md"""
        self.print_section("Project Registry")

        global_projects = self.claude_dir / "GLOBAL_PROJECTS.md"

        if global_projects.exists():
            size = global_projects.stat().st_size
            self.print_ok(f"GLOBAL_PROJECTS.md exists ({size} bytes)")

            # Try to parse it
            try:
                content = global_projects.read_text(encoding='utf-8')
                # Count project entries (lines with **Path:**)
                project_count = content.count('**Path:**')
                self.print_info(f"Contains {project_count} project entries")
                self.stats['global_projects_entries'] = project_count
            except Exception as e:
                self.print_warn(f"Could not parse GLOBAL_PROJECTS.md: {e}")
        else:
            self.print_info("GLOBAL_PROJECTS.md not found (will be created from template)")
            self.stats['global_projects_entries'] = 0

    def check_semantic_db(self):
        """Check for existing semantic database"""
        self.print_section("Semantic Search (L4 Layer)")

        semantic_db = self.claude_dir / "semantic_db_global"

        if semantic_db.exists():
            # Check size
            total_size = sum(f.stat().st_size for f in semantic_db.rglob("*") if f.is_file())
            self.print_ok(f"Semantic database exists ({total_size / 1024 / 1024:.1f} MB)")

            # Check for ChromaDB
            chroma_db = semantic_db / "chroma.sqlite3"
            if chroma_db.exists():
                db_size = chroma_db.stat().st_size
                self.print_ok(f"ChromaDB found ({db_size / 1024:.1f} KB)")
                self.stats['has_semantic_db'] = True
            else:
                self.print_warn("ChromaDB not found in semantic_db_global")
                self.stats['has_semantic_db'] = False
        else:
            self.print_info("No existing semantic database (will be created)")
            self.stats['has_semantic_db'] = False

    def check_dependencies(self):
        """Check Python dependencies"""
        self.print_section("Python Dependencies")

        # Check Python version
        python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        if sys.version_info >= (3, 7):
            self.print_ok(f"Python {python_version} (>= 3.7 required)")
        else:
            self.print_error(f"Python {python_version} (3.7+ required)")

        # Check required packages
        required_packages = {
            'chromadb': 'Vector database for semantic search',
            'sentence_transformers': 'Multilingual embeddings',
        }

        for package, description in required_packages.items():
            try:
                __import__(package)
                self.print_ok(f"{package} installed - {description}")
            except ImportError:
                self.print_warn(f"{package} not installed - {description}")
                self.print_info(f"  Install with: pip install {package}")

    def check_disk_space(self):
        """Check available disk space"""
        self.print_section("Disk Space")

        try:
            import shutil
            disk_usage = shutil.disk_usage(self.claude_dir)
            free = disk_usage.free

            free_gb = free / (1024**3)
            self.print_info(f"Free space: {free_gb:.1f} GB")

            if free_gb < 0.5:
                self.print_error("Less than 500 MB free (embeddings model requires ~500MB)")
            elif free_gb < 1.0:
                self.print_warn("Less than 1 GB free (recommended: 1GB+)")
            else:
                self.print_ok(f"Sufficient disk space ({free_gb:.1f} GB free)")

            self.stats['free_space_gb'] = free_gb
        except Exception as e:
            self.print_warn(f"Could not check disk space: {e}")

    def generate_recommendations(self):
        """Generate installation recommendations"""
        self.print_section("Recommendations")

        if not self.issues and not self.warnings:
            self.print_ok("No issues found! Safe to proceed with installation.")
            return

        if self.issues:
            print(f"\n{Colors.RED}{Colors.BOLD}Critical Issues:{Colors.END}")
            for issue in self.issues:
                print(f"  {Colors.RED}✗{Colors.END} {issue}")
            print(f"\n{Colors.RED}Please resolve these issues before installing.{Colors.END}")

        if self.warnings:
            print(f"\n{Colors.YELLOW}{Colors.BOLD}Warnings:{Colors.END}")
            for warning in self.warnings:
                print(f"  {Colors.YELLOW}⚠{Colors.END} {warning}")
            print(f"\n{Colors.YELLOW}These warnings can be ignored, but review them carefully.{Colors.END}")

    def generate_summary(self):
        """Generate summary report"""
        self.print_header("Installation Readiness Summary")

        print(f"{Colors.BOLD}Current State:{Colors.END}")
        if self.claude_dir.exists():
            print(f"  Claude Code: {Colors.GREEN}Installed{Colors.END}")
        else:
            print(f"  Claude Code: {Colors.RED}Not Found{Colors.END}")

        if self.stats.get('has_memory'):
            print(f"  Memory System: {Colors.GREEN}Exists{Colors.END}")
        else:
            print(f"  Memory System: {Colors.YELLOW}Not Found{Colors.END}")

        print(f"  Projects: {self.stats.get('project_count', 0)} found")

        if self.stats.get('has_semantic_db'):
            print(f"  Semantic DB: {Colors.GREEN}Exists{Colors.END}")
        else:
            print(f"  Semantic DB: {Colors.YELLOW}Not Found{Colors.END}")

        print(f"\n{Colors.BOLD}Statistics:{Colors.END}")
        print(f"  Total memory files: {self.stats.get('total_memory_files', 0)}")
        print(f"  Memory size: {self.stats.get('total_memory_size', 0) / 1024:.1f} KB")
        print(f"  Projects with memory: {self.stats.get('projects_with_memory', 0)}")
        print(f"  Archive files: {self.stats.get('archive_files', 0)}")

        print(f"\n{Colors.BOLD}Installation Impact:{Colors.END}")

        if self.stats.get('has_memory'):
            try:
                print(f"  {Colors.YELLOW}⚠{Colors.END} Existing memory will be preserved")
                print(f"  {Colors.GREEN}✓{Colors.END} New features will be added")
                print(f"  {Colors.GREEN}✓{Colors.END} Existing data will not be modified")
            except UnicodeEncodeError:
                print(f"  {Colors.YELLOW}[!]{Colors.END} Existing memory will be preserved")
                print(f"  {Colors.GREEN}[+]{Colors.END} New features will be added")
                print(f"  {Colors.GREEN}[+]{Colors.END} Existing data will not be modified")
        else:
            try:
                print(f"  {Colors.GREEN}✓{Colors.END} Fresh installation")
                print(f"  {Colors.GREEN}✓{Colors.END} No existing data to preserve")
            except UnicodeEncodeError:
                print(f"  {Colors.GREEN}[+]{Colors.END} Fresh installation")
                print(f"  {Colors.GREEN}[+]{Colors.END} No existing data to preserve")

        print(f"\n{Colors.BOLD}What will be installed:{Colors.END}")
        print("  - L4 SEMANTIC search engine")
        print("  - Auto-discovery system")
        print("  - Cleanup utilities")
        print("  - Cross-platform scripts")
        print("  - Configuration templates")

        print(f"\n{Colors.BOLD}What will NOT be changed:{Colors.END}")
        print("  - Existing memory files")
        print("  - Project directories")
        print("  - GLOBAL_PROJECTS.md (if exists)")
        print("  - Archive data")

    def save_report(self):
        """Save audit report to file"""
        report_file = Path("pre_install_audit_report.json")

        report = {
            'timestamp': datetime.now().isoformat(),
            'claude_dir': str(self.claude_dir),
            'stats': self.stats,
            'issues': self.issues,
            'warnings': self.warnings,
            'info': self.info,
        }

        try:
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2)
            self.print_ok(f"Audit report saved: {report_file}")
        except Exception as e:
            self.print_warn(f"Could not save report: {e}")

    def run(self):
        """Run complete audit"""
        self.print_header("Claude 4-Layer Memory System")
        print(f"{Colors.BOLD}Pre-Installation Audit{Colors.END}")
        print("Analyzing your current Claude Code setup...\n")

        # Run all checks
        if not self.check_claude_installation():
            msg = f"\n{Colors.RED}{Colors.BOLD}Cannot proceed: Claude Code not installed{Colors.END}"
            print(msg)
            return False

        self.analyze_memory_structure()
        self.analyze_projects()
        self.check_global_projects_file()
        self.check_semantic_db()
        self.check_dependencies()
        self.check_disk_space()

        # Generate reports
        self.generate_recommendations()
        self.generate_summary()
        self.save_report()

        # Final decision
        print(f"\n{Colors.BOLD}{'='*70}{Colors.END}")
        if self.issues:
            print(f"{Colors.RED}{Colors.BOLD}Installation NOT recommended{Colors.END}")
            print("Please resolve critical issues first.")
            return False

        print(f"{Colors.GREEN}{Colors.BOLD}Installation READY{Colors.END}")
        print("You can proceed with installation.")
        return True

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Claude 4-Layer Memory System - Pre-Installation Audit',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This tool analyzes your current Claude Code setup and provides
recommendations before installing the 4-Layer Memory System.

What this tool checks:
  • Claude Code installation
  • Existing memory structure
  • Project directories
  • Semantic database
  • Python dependencies
  • Disk space

What this tool does NOT do:
  • Modify any files
  • Install anything
  • Delete data
"""
    )

    parser.parse_args()

    print(f"""
{Colors.BOLD}Claude 4-Layer Memory System - Pre-Installation Audit{Colors.END}
{Colors.CYAN}{'='*70}{Colors.END}

This tool analyzes your current Claude Code setup and provides
recommendations before installing the 4-Layer Memory System.

{Colors.BOLD}What this tool checks:{Colors.END}
  • Claude Code installation
  • Existing memory structure
  • Project directories
  • Semantic database
  • Python dependencies
  • Disk space

{Colors.BOLD}What this tool does NOT do:{Colors.END}
  • Modify any files
  • Install anything
  • Delete data

{Colors.CYAN}{'='*70}{Colors.END}
""")

    audit = PreInstallAudit()
    success = audit.run()

    print(f"\n{Colors.BOLD}Next Steps:{Colors.END}")
    if success:
        print("  1. Review the audit report above")
        print("  2. Run installation script:")
        print(f"     {Colors.CYAN}Windows:{Colors.END} install.bat")
        print(f"     {Colors.CYAN}Linux/Mac:{Colors.END} ./install.sh")
    else:
        print("  1. Resolve critical issues listed above")
        print("  2. Run this audit again")
        print("  3. Proceed with installation when ready")

    print(f"\n{Colors.BOLD}Documentation:{Colors.END}")
    print("  - Installation Guide: docs/INSTALL.md")
    print("  - Usage Guide: docs/guides/USAGE.md")
    print("  - Configuration: docs/guides/CONFIGURATION.md")

    print(f"\n{Colors.CYAN}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}Audit complete!{Colors.END}\n")

    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
