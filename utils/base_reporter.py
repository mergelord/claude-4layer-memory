"""Base class for reporting with colored output"""
from typing import List

from .colors import Colors


class BaseReporter:
    """Base class for tools that report with colored output"""
    
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []
    
    def print_header(self, text: str):
        """Print a header"""
        print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*70}{Colors.END}")
        print(f"{Colors.BOLD}{Colors.CYAN}{text:^70}{Colors.END}")
        print(f"{Colors.BOLD}{Colors.CYAN}{'='*70}{Colors.END}\n")
    
    def print_section(self, text: str):
        """Print a section header"""
        print(f"\n{Colors.BOLD}{Colors.CYAN}## {text}{Colors.END}")
        print(f"{Colors.CYAN}{'-'*70}{Colors.END}")
    
    def print_ok(self, text: str):
        """Print success message"""
        try:
            print(f"{Colors.GREEN}✓{Colors.END} {text}")
        except UnicodeEncodeError:
            print(f"{Colors.GREEN}[OK]{Colors.END} {text}")
    
    def print_warn(self, text: str):
        """Print warning message"""
        try:
            print(f"{Colors.YELLOW}⚠{Colors.END} {text}")
        except UnicodeEncodeError:
            print(f"{Colors.YELLOW}[WARN]{Colors.END} {text}")
        self.warnings.append(text)
    
    def print_error(self, text: str):
        """Print error message"""
        try:
            print(f"{Colors.RED}✗{Colors.END} {text}")
        except UnicodeEncodeError:
            print(f"{Colors.RED}[ERROR]{Colors.END} {text}")
        self.errors.append(text)
    
    def print_info(self, text: str):
        """Print info message"""
        try:
            print(f"{Colors.CYAN}ℹ{Colors.END} {text}")
        except UnicodeEncodeError:
            print(f"{Colors.CYAN}[INFO]{Colors.END} {text}")
        self.info.append(text)
