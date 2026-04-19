# Code Quality Tools

This project uses multiple automated code quality tools to ensure high standards. All tools run automatically in CI/CD on every push and pull request.

## Tools Overview

### 1. Pylint - Code Style & Quality
**Purpose:** Checks Python code style, detects errors, enforces coding standards

**Run locally:**
```bash
python -m pylint scripts/*.py audit.py \
  --disable=C0114,C0115,C0116,R0913,R0914,R0915,R0903,R0904,W0718,R1702,C0415,R0902,R0912 \
  --max-line-length=110 \
  --good-names=i,j,k,e,f,_,rc
```

**Target:** 10.00/10 score

---

### 2. MyPy - Type Checking
**Purpose:** Static type checker, validates type hints

**Run locally:**
```bash
mypy scripts/*.py audit.py \
  --ignore-missing-imports \
  --no-strict-optional \
  --allow-untyped-defs \
  --allow-incomplete-defs
```

**Configuration:** Type hints required for all functions

---

### 3. Ruff - Fast Linter
**Purpose:** Modern, fast linter combining Flake8, isort, and more

**Run locally:**
```bash
ruff check scripts/*.py audit.py
```

**Speed:** 10-100x faster than traditional linters

---

### 4. Bandit - Security Scanner
**Purpose:** Finds common security issues in Python code

**Run locally:**
```bash
bandit -r scripts/ audit.py -l
```

**Target:** 0 security issues

**Severity levels:** LOW, MEDIUM, HIGH (all reported with `-l` flag)

**Common checks:**
- Hardcoded passwords
- SQL injection risks
- Use of unsafe functions
- Shell injection vulnerabilities

---

### 5. Radon - Complexity Analysis
**Purpose:** Measures cyclomatic complexity and maintainability index

**Run locally:**
```bash
# Cyclomatic complexity
radon cc scripts/*.py audit.py -a -nb

# Maintainability index
radon mi scripts/*.py audit.py -nb
```

**Targets:**
- Cyclomatic Complexity: A-B grade (< 10)
- Maintainability Index: A-B grade (> 20)

---

## CI/CD Integration

All tools run automatically via GitHub Actions:
- **Workflow file:** `.github/workflows/lint.yml`
- **Triggers:** Push to `main`, Pull Requests
- **View results:** [Actions tab](https://github.com/mergelord/claude-4layer-memory/actions)

### Workflow Jobs

1. `lint` - Pylint check
2. `typecheck` - MyPy type validation
3. `ruff` - Fast linting
4. `bandit` - Security scan
5. `radon` - Complexity analysis

---

## Running All Checks Locally

```bash
# Install all tools
pip install pylint mypy ruff bandit radon

# Run full check suite
python -m pylint scripts/*.py audit.py --disable=C0114,C0115,C0116,R0913,R0914,R0915,R0903,R0904,W0718,R1702,C0415,R0902,R0912 --max-line-length=110 --good-names=i,j,k,e,f,_,rc
mypy scripts/*.py audit.py --ignore-missing-imports --no-strict-optional --allow-untyped-defs --allow-incomplete-defs
ruff check scripts/*.py audit.py
bandit -r scripts/ audit.py -l
radon cc scripts/*.py audit.py -a -nb
radon mi scripts/*.py audit.py -nb
```

---

## Pre-commit Hook (Optional)

Add to `.git/hooks/pre-commit`:

```bash
#!/bin/bash
set -e

echo "Running code quality checks..."

# Quick checks only (fast)
ruff check scripts/*.py audit.py
bandit -r scripts/ audit.py -l

echo "✅ All checks passed!"
```

Make executable: `chmod +x .git/hooks/pre-commit`

---

## Configuration Files

- **Pylint:** Inline flags in workflow (no config file)
- **MyPy:** Inline flags in workflow (no config file)
- **Ruff:** Uses defaults (can add `ruff.toml` if needed)
- **Bandit:** Uses defaults (can add `.bandit` if needed)
- **Radon:** Uses defaults (no config needed)

---

## Troubleshooting

### Pylint fails with low score
- Check specific warnings in output
- Fix issues or add `# pylint: disable=XXXX` comments for false positives

### MyPy type errors
- Add type hints to function signatures
- Use `# type: ignore` for unavoidable issues

### Bandit security warnings
- Review code for actual vulnerabilities
- Use `# nosec` comment only if false positive

### Radon high complexity
- Refactor complex functions into smaller ones
- Extract helper functions
- Simplify conditional logic

---

## Current Status

All tools passing ✅

Last updated: 2026-04-19
