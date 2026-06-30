# GitHub Actions Workflows

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
