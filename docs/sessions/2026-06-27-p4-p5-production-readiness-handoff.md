# Session — P4/P5 Production Readiness, v1.6.1 Release, and P5-1 Handoff (2026-06-27)

## Purpose

This session continued production-readiness work for `mergelord/claude-4layer-memory` after P3 was merged. The work progressed through P4 documentation, dependency reproducibility, release-gate automation, final `v1.6.1` release prep, post-release installation wording cleanup, and the start of P5-1 CI workflow constraints.

The session is intentionally captured here as a handoff so work can resume tomorrow without losing context.

---

## Repository state at handoff

Repository:

```text
mergelord/claude-4layer-memory
```

Current `main` at the end of the session:

```text
fc28cd33700c2d021f65c3c00bf8417d5c86bff2
```

Latest merged commit on `main`:

```text
docs: refine installation support wording (#77)
```

Release tag:

```text
v1.6.1 -> 92ac72156ca598225c18750759d68abbddfc85de
```

Important detail:

```text
main is now newer than v1.6.1 because #77 is a post-release docs clarification.
```

This is expected and OK.

---

## Completed PR chain

### PR #73 — P4 docs/runbooks baseline

URL:

```text
https://github.com/mergelord/claude-4layer-memory/pull/73
```

Merged at:

```text
2026-06-27T16:36:56Z
```

Merge commit:

```text
8efb5fd3395e1eb836e227b19d78b33ac3ab7aa2
```

Summary:

- Added `docs/PRODUCTION_READINESS.md`.
- Added `docs/OPERATIONS.md`.
- Rewrote `docs/INSTALL.md`.
- Rewrote `docs/guides/CONFIGURATION.md`.
- Updated `MCP_SERVER.md`.
- Refreshed `README.md`.

Notes:

- Attempt to update `.github/workflows/README.md` failed because the GitHub integration lacks workflow-file permissions.
- Error was:

```text
403 Resource not accessible by integration
```

---

### PR #74 — P4-1 dependency reproducibility baseline

URL:

```text
https://github.com/mergelord/claude-4layer-memory/pull/74
```

Merged at:

```text
2026-06-27T17:38:32Z
```

Merge commit:

```text
7acbcb12a2aa3e91238e33674f0b44f7b8c1910b
```

Summary:

- `install.sh` now installs runtime dependencies with constraints:

```bash
pip3 install -r requirements.txt -c constraints.txt
```

- `install.bat` now installs runtime dependencies with constraints:

```bat
pip install -r requirements.txt -c constraints.txt
```

- `docs/INSTALL.md` now recommends constrained installs.
- `docs/PRODUCTION_READINESS.md` was updated to show installer-side reproducibility in place.
- CI workflow constrained installs were left as follow-up because workflow files require additional GitHub permissions.

---

### PR #75 — P4-2 release-gate CLI command

URL:

```text
https://github.com/mergelord/claude-4layer-memory/pull/75
```

Merged at:

```text
2026-06-27T18:24:07Z
```

Merge commit:

```text
d57c18afd403b8e84861d3bf2a5876b88524715b
```

Summary:

- Added:

```bash
node cli/index.js release-gate
```

and the `cm release-gate` command surface.

Quick mode:

```bash
node cli/index.js release-gate --quick --no-semantic
```

Runs:

- guardrail regression tests:
  - `tests/test_p3_guardrails.py`
  - `tests/test_mcp_e2e_smoke.py`
  - `tests/test_soak.py`
- `python scripts/scan_repo_encoding.py`
- `node cli/index.js selftest --no-semantic`
- `node cli/index.js doctor --no-semantic`

Full mode:

```bash
node cli/index.js release-gate --no-semantic
```

Adds:

- full pytest suite
- Pylint
- MyPy
- Ruff
- Bandit
- Radon complexity
- Radon maintainability

Important implementation correction:

- Initial implementation used glob args like `scripts/*.py` with `spawnSync(..., shell: false)`.
- This would not expand globs cross-platform.
- It was fixed by using directory targets such as `scripts` plus `audit.py` for tools where supported.

Updated docs:

- `README.md`
- `docs/PRODUCTION_READINESS.md`
- `docs/OPERATIONS.md`
- `CHANGELOG.md`

CI:

- User reported all 20 checks passed.
- PR was merged.

---

### PR #76 — P4-3 prepare v1.6.1 release

URL:

```text
https://github.com/mergelord/claude-4layer-memory/pull/76
```

Merged at:

```text
2026-06-27T18:38:02Z
```

Merge commit:

```text
92ac72156ca598225c18750759d68abbddfc85de
```

Summary:

- Bumped version `1.6.0 -> 1.6.1` in:
  - `VERSION`
  - `package.json`
  - `pyproject.toml`
  - `README.md`
- Updated README badge/header to `1.6.1`.
- Closed `CHANGELOG.md` as:

```markdown
## [1.6.1] - 2026-06-27
```

- Updated `docs/PRODUCTION_READINESS.md` status to:

```text
v1.6.1 release candidate
```

CI:

- User reported 20 successful checks.
- Assistant verified:
  - `mergeable_state: clean`
  - `20/20` checks success

After merge:

- User tagged release locally from Git Bash.

---

## v1.6.1 release tag

User ran locally:

```bash
git checkout main
git pull origin main
git tag v1.6.1
git push origin v1.6.1
```

Assistant verified:

```text
main:   92ac72156ca598225c18750759d68abbddfc85de
v1.6.1: 92ac72156ca598225c18750759d68abbddfc85de
```

`VERSION` at tag:

```text
1.6.1
```

`CHANGELOG.md` at tag starts with:

```markdown
## [1.6.1] - 2026-06-27
```

Conclusion:

```text
v1.6.1 released
```

---

### PR #77 — docs refine installation support wording

URL:

```text
https://github.com/mergelord/claude-4layer-memory/pull/77
```

Merged at:

```text
2026-06-27T19:59:12Z
```

Merge commit:

```text
fc28cd33700c2d021f65c3c00bf8417d5c86bff2
```

Reason:

The README wording `Installation: git-clone only` was technically correct but too harsh / not aligned with the current project framing.

New meaning:

- Supported setup is a full Git clone plus repository installer.
- This is because the supported setup includes:
  - CLI
  - Python backend
  - hooks
  - constraints
  - docs
  - release-gate checks
  - repository-local runtime files
- Standalone npm/pip package install is not supported yet.

Important state after #77:

```text
main is newer than v1.6.1
```

This is expected because #77 is post-release docs clarification and will naturally be part of a future `v1.6.2` or later release.

---

## Current active work: P5-1 CI workflow constraints

User asked to start:

```text
P5-1: CI workflow constraints
```

Goal:

- Make CI use the same constrained dependency baseline as local installs.
- Close the remaining production-readiness gap where installers use `constraints.txt` but workflows still install unconstrained dependencies.

Branch created by assistant:

```text
p5-1-ci-workflow-constraints
```

Branch was created from current `main`:

```text
fc28cd33700c2d021f65c3c00bf8417d5c86bff2
```

No changes were successfully pushed to that branch because workflow-file writes are blocked for the integration.

---

## P5-1 files inspected

### `.github/workflows/test.yml`

Current problem:

Every Python test job still installs dependencies as:

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

Desired change:

```bash
pip install -r requirements.txt -c constraints.txt
pip install -r requirements-dev.txt -c constraints.txt
```

This should be applied across all test jobs:

- Ubuntu Python 3.10
- Ubuntu Python 3.11
- Ubuntu Python 3.12
- Ubuntu Python 3.13
- Ubuntu Python 3.14 experimental
- Windows Python 3.10
- Windows Python 3.11
- Windows Python 3.12
- Windows Python 3.13
- macOS Python 3.10
- macOS Python 3.11
- macOS Python 3.12
- macOS Python 3.13

Expected number of replacements in current file:

```text
13
```

---

### `.github/workflows/lint.yml`

Current runtime installs:

```bash
pip install -r requirements.txt
pip install pylint
```

and:

```bash
pip install -r requirements.txt
pip install mypy
```

Desired changes:

```bash
pip install -r requirements.txt -c constraints.txt
pip install pylint
```

and:

```bash
pip install -r requirements.txt -c constraints.txt
pip install mypy
```

Notes:

- Ruff job currently installs only `ruff`; no runtime dependency install there.
- Bandit/Radon matrix installs only the selected tool package; no runtime dependency install there.
- EncodingGate intentionally skips pip install because it only needs stdlib plus repo-local helper code.

Potential future improvement:

- Consider using `requirements-dev.txt -c constraints.txt` in lint jobs instead of installing tool packages individually, but for P5-1 the minimal production change is to constrain only runtime dependency installs where `requirements.txt` is used.

---

### `.github/workflows/release.yml`

Current release artifacts include:

```yaml
requirements.txt
requirements-dev.txt
```

Desired addition:

```yaml
constraints.txt
```

Reason:

- Release artifacts should include the constraints file required for reproducible installs.

---

### `.github/workflows/README.md`

Current doc is stale:

- It says Python 3.8–3.12.
- It does not mention Python 3.13 or 3.14 experimental.
- It does not mention constrained installs.
- It does not describe the Code Quality workflow accurately.
- It does not mention `constraints.txt` in release artifacts.

Desired rewrite is included below.

---

## P5-1 attempted push and failure

Assistant attempted to push changes to:

```text
p5-1-ci-workflow-constraints
```

using GitHub MCP `push_files`.

Push failed with:

```text
failed to create tree: POST https://api.github.com/repos/mergelord/claude-4layer-memory/git/trees: 403 Resource not accessible by integration []
```

Conclusion:

- The GitHub integration still lacks `workflows` permission.
- Workflow files must be changed manually by the user using Git Bash or GitHub UI.
- This is the same limitation encountered earlier when editing `.github/workflows/test.yml`.

---

## Manual P5-1 patch to run tomorrow

Run from repository root:

```bash
cd ~/ZCodeProject/claude-4layer-memory
git checkout main
git pull origin main
git checkout -b p5-1-ci-workflow-constraints
```

If the branch already exists locally:

```bash
git checkout p5-1-ci-workflow-constraints
git merge main
```

Create patch file:

```bash
cat > patch_p5_1_workflows.py <<'PY'
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
PY
```

Run patch:

```bash
python patch_p5_1_workflows.py
```

If `python` is not found:

```bash
py -3 patch_p5_1_workflows.py
```

Expected output:

```text
[ok] .github/workflows/test.yml: replaced 13 occurrence(s)
[ok] .github/workflows/lint.yml: replaced 1 occurrence(s)
[ok] .github/workflows/lint.yml: replaced 1 occurrence(s)
[ok] .github/workflows/release.yml: added constraints.txt artifact
[ok] .github/workflows/README.md: rewritten
```

Review:

```bash
git diff -- .github/workflows/test.yml .github/workflows/lint.yml .github/workflows/release.yml .github/workflows/README.md
```

Clean temp file:

```bash
rm patch_p5_1_workflows.py
```

Commit and push:

```bash
git add .github/workflows/test.yml .github/workflows/lint.yml .github/workflows/release.yml .github/workflows/README.md
git commit -m "ci: enforce constraints in workflows"
git push -u origin p5-1-ci-workflow-constraints
```

After push, assistant can inspect the branch and open/check PR.

---

## Important caveat for tomorrow

Because the assistant created remote branch `p5-1-ci-workflow-constraints` before the push failed, tomorrow the user may see one of these situations:

### If local branch creation says branch already exists

Use:

```bash
git checkout p5-1-ci-workflow-constraints
git merge main
```

### If push says remote branch already exists

Use:

```bash
git push -u origin p5-1-ci-workflow-constraints
```

If rejected due non-fast-forward:

```bash
git pull --rebase origin p5-1-ci-workflow-constraints
git push -u origin p5-1-ci-workflow-constraints
```

Remote branch currently contains no P5-1 changes, only the base commit, so it should be safe.

---

## Open issue not addressed

Issue #11 remains open:

```text
Integrate memory_lint_helpers.py during MemoryLinter split
```

This is not part of P5-1 and is not a blocker for the workflow-constraints task.

---

## Next recommended sequence tomorrow

1. Apply manual P5-1 workflow patch using the Python script above.
2. Push branch:

```text
p5-1-ci-workflow-constraints
```

3. Ask assistant to inspect branch and open PR.
4. Let CI run.
5. If green, merge.
6. After merge, production-readiness gap “CI dependency reproducibility” is closed.
7. Next possible P5 tasks:
   - clean clone validation of `v1.6.1`
   - GitHub Release notes verification
   - bootstrap/release artifact installer
   - issue #11 / MemoryLinter helper integration