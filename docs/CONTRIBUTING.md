# Contributing to Claude 4-Layer Memory System

Thank you for your interest in contributing! This document provides guidelines and instructions for contributing to the project.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Contribution Workflow](#contribution-workflow)
- [Code Standards](#code-standards)
- [Testing](#testing)
- [Documentation](#documentation)
- [Pull Request Process](#pull-request-process)

---

## Code of Conduct

### Our Pledge

We are committed to providing a welcoming and inclusive environment for all contributors, regardless of:
- Experience level
- Gender identity and expression
- Sexual orientation
- Disability
- Personal appearance
- Body size
- Race
- Ethnicity
- Age
- Religion
- Nationality

### Expected Behavior

- Use welcoming and inclusive language
- Be respectful of differing viewpoints
- Accept constructive criticism gracefully
- Focus on what is best for the community
- Show empathy towards other community members

### Unacceptable Behavior

- Trolling, insulting/derogatory comments, and personal attacks
- Public or private harassment
- Publishing others' private information without permission
- Other conduct which could reasonably be considered inappropriate

---

## Getting Started

### Prerequisites

- Python 3.10 or higher
- Git
- GitHub account
- Basic understanding of:
  - Python programming
  - Git workflow
  - Markdown documentation

### Finding Issues to Work On

1. **Good First Issues:**
   - Look for issues labeled `good first issue`
   - These are beginner-friendly tasks

2. **Help Wanted:**
   - Issues labeled `help wanted` need community support

3. **Bug Reports:**
   - Check issues labeled `bug`
   - Reproduce and fix reported bugs

4. **Feature Requests:**
   - Issues labeled `enhancement`
   - Implement new features

### Reporting Bugs

Before creating a bug report:
1. Check existing issues
2. Verify it's reproducible
3. Collect system information

**Bug Report Template:**
```markdown
**Description:**
Clear description of the bug

**Steps to Reproduce:**
1. Step one
2. Step two
3. ...

**Expected Behavior:**
What should happen

**Actual Behavior:**
What actually happens

**Environment:**
- OS: [e.g., Windows 11, Ubuntu 22.04]
- Python Version: [e.g., 3.11.2]
- Project Version: [e.g., 1.4.0]

**Additional Context:**
Screenshots, logs, etc.
```

### Suggesting Features

**Feature Request Template:**
```markdown
**Feature Description:**
Clear description of the feature

**Use Case:**
Why is this feature needed?

**Proposed Solution:**
How should it work?

**Alternatives Considered:**
Other approaches you've thought about

**Additional Context:**
Mockups, examples, etc.
```

---

## Development Setup

### 1. Fork and Clone

```bash
# Fork the repository on GitHub
# Then clone your fork
git clone https://github.com/YOUR_USERNAME/claude-4layer-memory.git
cd claude-4layer-memory

# Add upstream remote
git remote add upstream https://github.com/mergelord/claude-4layer-memory.git
```

### 2. Create Virtual Environment

```bash
# Create venv
python -m venv venv

# Activate
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate
```

### 3. Install Dependencies

```bash
# Install project dependencies
pip install -r requirements.txt

# Install development dependencies
pip install -r requirements-dev.txt
```

### 4. Install Pre-commit Hooks

```bash
# Install pre-commit
pip install pre-commit

# Setup hooks
pre-commit install
```

### 5. Verify Setup

```bash
# Run tests
pytest tests/ -v

# Run linters
ruff check .
pylint scripts/*.py

# Run type checker
mypy scripts/
```

---

## Contribution Workflow

### 1. Create a Branch

```bash
# Update main branch
git checkout main
git pull upstream main

# Create feature branch
git checkout -b feature/your-feature-name
# or
git checkout -b fix/bug-description
```

**Branch Naming Convention:**
- `feature/` - New features
- `fix/` - Bug fixes
- `docs/` - Documentation changes
- `refactor/` - Code refactoring
- `test/` - Test additions/changes

### 2. Make Changes

- Write clean, readable code
- Follow code standards (see below)
- Add tests for new features
- Update documentation

### 3. Commit Changes

```bash
# Stage changes
git add .

# Commit with descriptive message
git commit -m "feat: add hybrid search caching"
```

**Commit Message Format:**
```
<type>: <subject>

<body>

<footer>
```

**Types:**
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation changes
- `style:` - Code style changes (formatting)
- `refactor:` - Code refactoring
- `test:` - Test additions/changes
- `chore:` - Build/tooling changes

**Example:**
```
feat: add parallel search execution

Implement ThreadPoolExecutor-based parallel search across
multiple collections for 2-3x performance improvement.

- Add MAX_WORKERS configuration
- Implement concurrent collection queries
- Add benchmark tests

Closes #123
```

### 4. Push Changes

```bash
# Push to your fork
git push origin feature/your-feature-name
```

### 5. Create Pull Request

1. Go to your fork on GitHub
2. Click "New Pull Request"
3. Select your branch
4. Fill in PR template
5. Submit PR

---

## Code Standards

### Python Style Guide

We follow **PEP 8** with some modifications:

```python
# Maximum line length: 110 characters
MAX_LINE_LENGTH = 110

# Use 4 spaces for indentation
def example_function():
    pass

# Use snake_case for functions and variables
def calculate_total(items):
    total_sum = sum(items)
    return total_sum

# Use PascalCase for classes
class MemoryLint:
    pass

# Use UPPER_CASE for constants
MAX_CHUNK_SIZE = 1000
DEFAULT_MODEL = "all-MiniLM-L6-v2"
```

### Type Hints

Use type hints for all public functions:

```python
from typing import List, Dict, Optional

def search_memory(
    query: str,
    n_results: int = 10,
    collections: Optional[List[str]] = None
) -> List[Dict[str, any]]:
    """Search memory with type hints."""
    pass
```

### Docstrings

Use Google-style docstrings:

```python
def complex_function(param1: str, param2: int) -> bool:
    """Short description of function.
    
    Longer description if needed. Explain what the function does,
    any important details, and edge cases.
    
    Args:
        param1: Description of param1
        param2: Description of param2
        
    Returns:
        Description of return value
        
    Raises:
        ValueError: When param2 is negative
        
    Example:
        >>> complex_function("test", 5)
        True
    """
    pass
```

### Code Quality Tools

#### Ruff (Linter)

```bash
# Check code
ruff check .

# Auto-fix issues
ruff check . --fix

# Format code
ruff format .
```

#### Pylint

```bash
# Run pylint
pylint scripts/*.py --max-line-length=110
```

#### MyPy (Type Checker)

```bash
# Check types
mypy scripts/ --ignore-missing-imports
```

#### Bandit (Security)

```bash
# Security scan
bandit -r scripts/ -ll
```

#### Radon (Complexity)

```bash
# Check complexity
radon cc scripts/*.py -a -nb

# Check maintainability
radon mi scripts/*.py -nb
```

### Code Quality Targets

- **Pylint Score:** ≥ 9.0/10
- **Cyclomatic Complexity:** ≤ 10 per function
- **Maintainability Index:** ≥ 20 (rank A or B)
- **Test Coverage:** ≥ 80%
- **Type Coverage:** ≥ 70%

---

## Testing

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_memory_lint.py -v

# Run with coverage
pytest tests/ --cov=scripts --cov-report=html

# Run specific test
pytest tests/test_memory_lint.py::test_ghost_links -v
```

### Writing Tests

Use pytest with clear test names:

```python
import pytest
from scripts.memory_lint import MemoryLint

class TestMemoryLint:
    """Test suite for MemoryLint class."""
    
    @pytest.fixture
    def temp_memory_dir(self, tmp_path):
        """Create temporary memory directory."""
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()
        return memory_dir
    
    def test_ghost_links_detection(self, temp_memory_dir):
        """Test that ghost links are correctly detected."""
        # Arrange
        lint = MemoryLint(temp_memory_dir)
        
        # Act
        ghost_links = lint.check_ghost_links()
        
        # Assert
        assert len(ghost_links) == 0
```

### Test Categories

1. **Unit Tests:** Test individual functions
2. **Integration Tests:** Test component interactions
3. **End-to-End Tests:** Test complete workflows
4. **Performance Tests:** Test speed and resource usage

---

## Documentation

### Documentation Standards

- Use Markdown for all documentation
- Keep line length ≤ 100 characters
- Use clear, concise language
- Include code examples
- Add screenshots when helpful

### Documentation Structure

```
docs/
├── README.md              # Overview
├── INSTALL.md            # Installation guide
├── FAQ.md                # Frequently asked questions
├── TROUBLESHOOTING.md    # Common issues
├── CONTRIBUTING.md       # This file
├── guides/
│   ├── USAGE.md         # Usage guide
│   └── CONFIGURATION.md # Configuration guide
└── architecture/
    └── ARCHITECTURE.md  # System architecture
```

### Updating Documentation

When adding features:
1. Update relevant documentation files
2. Add examples to guides
3. Update FAQ if needed
4. Add troubleshooting entries for common issues

---

## Pull Request Process

### Before Submitting

- [ ] Code follows style guidelines
- [ ] All tests pass
- [ ] New tests added for new features
- [ ] Documentation updated
- [ ] Commit messages follow convention
- [ ] No merge conflicts with main

### PR Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] Manual testing performed

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] No new warnings generated

## Related Issues
Closes #123
```

### Review Process

1. **Automated Checks:**
   - CI/CD pipeline runs
   - All tests must pass
   - Code quality checks pass

2. **Code Review:**
   - At least one maintainer reviews
   - Address review comments
   - Request re-review if needed

3. **Approval:**
   - Maintainer approves PR
   - PR is merged to main

### After Merge

- Delete your feature branch
- Update your fork:
  ```bash
  git checkout main
  git pull upstream main
  git push origin main
  ```

---

## Release Process

### Version Numbering

We use Semantic Versioning (SemVer):

```
MAJOR.MINOR.PATCH

1.4.0
│ │ │
│ │ └─ Patch: Bug fixes
│ └─── Minor: New features (backward compatible)
└───── Major: Breaking changes
```

### Creating a Release

1. Update VERSION file
2. Update CHANGELOG.md
3. Create git tag:
   ```bash
   git tag -a v1.4.0 -m "Release version 1.4.0"
   git push origin v1.4.0
   ```
4. GitHub Actions creates release automatically

---

## Community

### Communication Channels

- **GitHub Issues:** Bug reports and feature requests
- **GitHub Discussions:** General questions and ideas
- **Pull Requests:** Code contributions

### Getting Help

- Read documentation first
- Search existing issues
- Ask in GitHub Discussions
- Create new issue if needed

---

## Recognition

Contributors are recognized in:
- CREDITS.md file
- Release notes
- GitHub contributors page

Thank you for contributing! 🎉

---

**Last Updated:** 2026-05-22  
**Version:** 1.4.0