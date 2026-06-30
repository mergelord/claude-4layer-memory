# Session — P5 Production Readiness / Bootstrap Handoff (2026-06-30)

## Status

Context captured at the end of the 2026-06-30 production-readiness session.

- Project: `mergelord/claude-4layer-memory`
- Latest `main`: `e1f558f9fed3aaa8f09ba00833c2bb465b4e69d8`
- Latest `main` commit: `docs: add installer bootstrap story`
- Latest release tag: `v1.6.2 -> 27dc537aff93e64f67ff0443af848960aaef32e0`
- Open pull requests at handoff: none
- Current production-readiness estimate: **8.5 / 10**

`main` is newer than `v1.6.2` because PR #82 and PR #83 were documentation cleanups merged after the tag.

## Completed in this continuation

### PR #78 — P5-1 CI workflow constraints

- URL: https://github.com/mergelord/claude-4layer-memory/pull/78
- Status: merged
- Goal: make CI use the same constrained dependency baseline as local installs.
- Result: 20/20 checks passed after the ChromaDB constraint refresh.

Key changes:

- `.github/workflows/test.yml` now installs runtime and dev dependencies with `-c constraints.txt`.
- `.github/workflows/lint.yml` uses `constraints.txt` where runtime dependencies are installed.
- `.github/workflows/release.yml` includes `constraints.txt` in release artifacts.
- `.github/workflows/README.md` was updated to reflect Python 3.10-3.13 blocking jobs, Python 3.14 experimental, and constrained installs.

Issue encountered:

- Initial PR #78 CI failed in all 13 Python test jobs.
- Root cause: `chromadb==0.4.24` imported `np.float_`, removed in NumPy 2.x.
- Fix: `constraints.txt` was updated to `chromadb==1.5.9`.

### PR #79 — docs/changelog follow-up for P5-1

- URL: https://github.com/mergelord/claude-4layer-memory/pull/79
- Status: merged
- Merge commit: `3471fbebd95d30f04bfefda93526fca1f1d6dae8`

Captured the CI constraints work in docs and changelog.

### P5-2 — clean clone validation

Clean clone validation passed on Windows with Python 3.14.5.

Validated flow:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -c constraints.txt
python -m pip install -r requirements-dev.txt -c constraints.txt
npm install
python scripts/health_memory_size.py
python scripts/memory_lint.py --help
python audit.py --help
python -m pytest tests/ -v --tb=short
node cli/index.js release-gate --quick --no-semantic
```

Observed results:

- Health check passed, including ChromaDB probe.
- Full pytest passed: `571 passed, 2 skipped in 9.46s`.
- Release gate passed in quick/no-semantic mode.

The temporary clean clone directory was removed after validation.

### PR #80 — document Node dependency install

- URL: https://github.com/mergelord/claude-4layer-memory/pull/80
- Status: merged
- Merge time: 2026-06-30 22:42 MSK

Reason:

- Clean clone release-gate initially failed with `Cannot find module 'commander'` because fresh clone docs did not say to run `npm install` before repository-local Node CLI checks.

Result:

- README, install docs, production-readiness docs, and changelog now document `npm install` before Node CLI checks.

### PR #81 — prepare v1.6.2 release

- URL: https://github.com/mergelord/claude-4layer-memory/pull/81
- Status: merged
- Merge commit: `27dc537aff93e64f67ff0443af848960aaef32e0`
- Checks: 20/20 successful

Updated release metadata:

- `VERSION`: `1.6.2`
- `package.json`: `1.6.2`
- `README.md`: visible version/badge to `1.6.2`
- `CHANGELOG.md`: added `## [1.6.2] - 2026-06-30`

The user then tagged and pushed:

```bash
git tag v1.6.2
git push origin v1.6.2
```

Verified tag:

- `v1.6.2 -> 27dc537aff93e64f67ff0443af848960aaef32e0`

### PR #82 — remove top README install warning

- URL: https://github.com/mergelord/claude-4layer-memory/pull/82
- Status: merged
- Merge commit: `2268f869ca2a59b6b3533985a85a699ab4905846`
- Checks: 20/20 successful

Removed the prominent top README callout:

```text
Install from a full repository clone.
```

The detailed installation-section note about supported clone + repository installer mode was intentionally kept.

### PR #83 — installer/bootstrap story

- URL: https://github.com/mergelord/claude-4layer-memory/pull/83
- Status: merged
- Merge commit: `e1f558f9fed3aaa8f09ba00833c2bb465b4e69d8`
- Checks: 20/20 successful

Added a clean bootstrap guide:

- New file: `docs/BOOTSTRAP.md`
- Updated:
  - `README.md`
  - `docs/INSTALL.md`
  - `docs/PRODUCTION_READINESS.md`
  - `CHANGELOG.md`

Supported bootstrap story now documented as:

```text
git clone
 -> install Python deps with constraints.txt
 -> npm install
 -> audit
 -> install hook runtime
 -> verify
```

The docs now explicitly separate:

- Repository toolchain: cloned repository, release gate, audit, tests, MCP/dev tools, hybrid search, memory lint, docs.
- Installed hook runtime: files deployed under `~/.claude` or `<L4_HOME>`, semantic runtime wrappers, built-in hooks, memory templates, local directories.

Important note captured in docs:

- Use `npm install`, not `npm ci`, because the repository currently does not commit `package-lock.json`.

## Current repository state

- Latest `main`: `e1f558f9fed3aaa8f09ba00833c2bb465b4e69d8`
- Latest `main` commit message:

```text
docs: add installer bootstrap story
```

- `v1.6.2` tag remains at:

```text
27dc537aff93e64f67ff0443af848960aaef32e0
```

- Therefore these docs-only commits are on `main` but not in `v1.6.2`:

```text
2268f869ca2a59b6b3533985a85a699ab4905846 docs: remove top install warning
e1f558f9fed3aaa8f09ba00833c2bb465b4e69d8 docs: add installer bootstrap story
```

## Production readiness assessment

Current assessment: **8.5 / 10**.

Meaning:

- Production-ready for technical/full-clone repository users: yes.
- Production-ready for public repository release: yes.
- Production-ready as a packaged product: not yet.

Remaining gap to 9/10:

- GitHub Release notes polishing/verification for `v1.6.2`.
- Decide whether to keep post-release docs only on `main` or cut a future docs-only patch tag.
- More package-like installer/bootstrap artifact story if a standalone installation path becomes a goal.

## Pending / follow-up

### Manual GitHub repository description update

The repository description should be updated manually in GitHub UI because the current toolset does not expose repo settings updates.

Recommended description:

```text
Production-ready 4-layer memory system for Claude Code with hybrid search, MCP tools, and reproducible installs.
```

Previous/current description discussed during the session:

```text
Intelligent memory management system for Claude Code with semantic search and cross-project knowledge sharing
```

### Release/tag decision

No urgent new tag is required just for PR #82/#83 docs cleanup.

If desired later, a docs-only patch release could include:

- top README warning cleanup
- bootstrap story
- any additional GitHub Release notes polish

Potential tag would likely be `v1.6.3`, but only if the user wants post-`v1.6.2` docs included in a tag.

### Optional next production-readiness tasks

- Verify/polish GitHub Release notes for `v1.6.2`.
- Improve release artifact/bootstrap installer polish if moving toward a more productized install path.
- Issue #11: `Integrate memory_lint_helpers.py during MemoryLinter split`.

## Important constraints and known limitations

### GitHub workflow file permissions

The GitHub integration could not write `.github/workflows/*` directly.

Observed error:

```text
failed to create tree: POST https://api.github.com/repos/mergelord/claude-4layer-memory/git/trees: 403 Resource not accessible by integration []
```

Workaround used for PR #78:

- Assistant generated a temporary patch helper.
- User ran it locally.
- User committed workflow changes manually.

### GitHub repository settings

The current GitHub tools do not expose a repository description/settings update action.

Repo description update remains manual via GitHub UI.

## Resume instructions

When continuing:

1. Verify latest `main` and open PRs.
2. Treat `e1f558f9fed3aaa8f09ba00833c2bb465b4e69d8` as the latest known good `main` from this handoff.
3. Remember that `v1.6.2` points to `27dc537aff93e64f67ff0443af848960aaef32e0`, so post-tag docs updates are not included in that tag.
4. If the user asks “what next for production,” recommend either:
   - GitHub Release notes verification/polish, or
   - leave release as-is and move to Issue #11 / MemoryLinter helper integration, depending on priority.
