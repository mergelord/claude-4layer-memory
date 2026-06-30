from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    Path(path).write_text(content, encoding="utf-8", newline="\n")


def replace_all(path: str, old: str, new: str, expected_min: int = 1) -> int:
    content = read(path)
    count = content.count(old)

    if count == 0:
        if new in content:
            print(f"[skip] {path}: already patched")
            return 0
        raise SystemExit(
            f"[error] {path}: pattern not found.\n"
            f"Expected to find:\n{old}"
        )

    if count < expected_min:
        raise SystemExit(
            f"[error] {path}: expected at least {expected_min} matches, found {count}"
        )

    content = content.replace(old, new)
    write(path, content)
    print(f"[ok] {path}: replaced {count} occurrence(s)")
    return count


replace_all(
    ".github/workflows/test.yml",
    "pip install -r requirements.txt\n          pip install -r requirements-dev.txt",
    "pip install -r requirements.txt -c constraints.txt\n          pip install -r requirements-dev.txt -c constraints.txt",
    expected_min=10,
)

replace_all(
    ".github/workflows/lint.yml",
    "pip install -r requirements.txt\n        pip install pylint",
    "pip install -r requirements.txt -c constraints.txt\n        pip install pylint",
    expected_min=1,
)

replace_all(
    ".github/workflows/lint.yml",
    "pip install -r requirements.txt\n        pip install mypy",
    "pip install -r requirements.txt -c constraints.txt\n        pip install mypy",
    expected_min=1,
)

release_path = ".github/workflows/release.yml"
release = read(release_path)

if "          constraints.txt\n" in release:
    print(f"[skip] {release_path}: constraints.txt already included")
else:
    old = "          requirements-dev.txt\n"
    new = "          requirements-dev.txt\n          constraints.txt\n"
    if old not in release:
        raise SystemExit(
            f"[error] {release_path}: could not find requirements-dev.txt artifact line"
        )
    release = release.replace(old, new, 1)
    write(release_path, release)
    print(f"[ok] {release_path}: added constraints.txt artifact")


workflow_readme = """# GitHub Actions Workflows

Automated CI/CD workflows for claude-4layer-memory.

## Workflows

### 1. Python Tests (`test.yml`)
**Trigger:** Push and Pull Request to `main`

**What it does:**
- Tests on 3 operating systems: Ubuntu, Windows, macOS
- Tests blocking Python versions 3.10, 3.11, 3.12, 3.13
- Tests Python 3.14 on Ubuntu as a non-blocking experimental job
- Installs runtime and dev dependencies with `constraints.txt`
- Runs the full pytest suite
- Checks script help surfaces (`memory_lint.py --help`, `audit.py --help`)
- Verifies executable bits on Linux/macOS

**Why:** Guarantees supported OS/Python compatibility with reproducible dependency resolution.

### 2. Code Quality (`lint.yml`)
**Trigger:** Push and Pull Request to `main`

**What it does:**
- Runs Pylint, MyPy, Ruff, Bandit, Radon, and EncodingGate
- Installs runtime dependencies with `constraints.txt` where runtime dependencies are needed
- Keeps standalone tool installs explicit for lightweight jobs

**Why:** Maintains static quality, type-checking, security, complexity, and UTF-8 hygiene.

### 3. Shellcheck (`shellcheck.yml`)
**Trigger:** Push and Pull Request to `main`

**What it does:**
- Checks bash scripts in `scripts/linux/`
- Checks `install.sh` and `audit.sh`
- Finds shell errors and portability issues

**Why:** Maintains bash script quality.

### 4. Release (`release.yml`)
**Trigger:** Push tag matching `v*.*.*` (for example, `v1.6.1`)

**What it does:**
- Generates release notes from git commits
- Creates a GitHub Release
- Attaches scripts, templates, installers, audit scripts, requirements, and `constraints.txt`

**Why:** Publishes tagged releases with the files required for reproducible installs.

## How to use

### Run tests locally
```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -c constraints.txt
python -m pip install -r requirements-dev.txt -c constraints.txt
python -m pytest tests/ -v --tb=short
python scripts/memory_lint.py --help
python audit.py --help
```

### Run the release gate locally
```bash
node cli/index.js release-gate --quick --no-semantic
```

### Create a release
```bash
git tag v1.6.1
git push origin v1.6.1
```

GitHub Actions automatically creates the Release.

### Check bash scripts locally
```bash
# Install shellcheck first:
# Ubuntu: sudo apt install shellcheck
# macOS: brew install shellcheck
# Windows: scoop install shellcheck

shellcheck scripts/linux/*.sh
shellcheck install.sh
shellcheck audit.sh
```

## Status badges

Badges can be added to README.md:

```markdown
![Python Tests](https://github.com/mergelord/claude-4layer-memory/actions/workflows/test.yml/badge.svg)
![Code Quality](https://github.com/mergelord/claude-4layer-memory/actions/workflows/lint.yml/badge.svg)
![Shellcheck](https://github.com/mergelord/claude-4layer-memory/actions/workflows/shellcheck.yml/badge.svg)
```

## Troubleshooting

**Tests fail on Windows:**
- Check paths; prefer `/` in cross-platform scripts.
- Check file encoding; files should be UTF-8.

**Dependency resolution changes unexpectedly:**
- Ensure workflow and local installs use `-c constraints.txt` with runtime requirements.
- Bump constraints deliberately, not implicitly.

**Shellcheck finds errors:**
- Fix per recommendations.
- Or add a targeted `# shellcheck disable=SC####` comment for false positives.

**Release is not created:**
- Check tag format: it must match `v1.2.3`.
- Check permissions: `GITHUB_TOKEN` is provided automatically.
"""

write(".github/workflows/README.md", workflow_readme)
print("[ok] .github/workflows/README.md: rewritten")

print("\nDone. Review changes with:")
print("  git diff -- .github/workflows/test.yml .github/workflows/lint.yml .github/workflows/release.yml .github/workflows/README.md")
