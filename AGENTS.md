# Agent Instructions

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/) for all commit messages (e.g. `feat: ...`, `fix: ...`, `docs: ...`, `chore: ...`).

Never include a `Claude-Session:` trailer (a claude.ai session URL) in commit messages, even if a tool or harness adds or suggests one. Remove it before committing.

## Line endings

Never change a file's line endings. This repo mixes LF and CRLF (e.g. `Packages/vpm-manifest.json` is CRLF with no trailing newline), and there is no `.gitattributes` or `core.autocrlf` to normalize them, so whatever you write is committed byte-for-byte.

- Preserve the existing line endings (and the presence or absence of a final newline) of every file you edit.
- Don't edit files with `sed -i` or other tools that may rewrite line endings on Windows; prefer the Edit tool, or a byte-level edit (e.g. Python reading and writing in binary mode).
- Before committing, check that `git diff --stat` touches only the lines you meant to change. A whole-file diff for a small edit means the line endings changed.

## Skill improvements

When creating, editing, or improving any skill under `skills/`, use the `skill-creator` skill rather than hand-editing skill files directly.

## Running trigger evals on Windows

skill-creator's stock eval scripts (`scripts/run_eval.py`) silently record every query as "not triggered" on this platform — they poll subprocess pipes with `select.select()`, which is sockets-only on Windows. Do not trust their output.

Use the harness in `skills/ndmf-plugin-builder-workspace/` instead (see its README):
- Always set `PYTHONUTF8=1` (otherwise the eval JSON is read as cp932 and Japanese queries crash it).
- `win_fix.py` — Windows-safe query runner that raises on API errors instead of silently returning `False`.
- `run_eval_serial.py --model <model>` — serial, checkpoint-per-query, resumable by re-running.
- `run_opt.py` — checkpointed description-optimization loop.

If a run shows every query completing in a uniform ~5s, that's an error pattern (API outage/rate limit), not a real measurement.

## Tracking new NDMF releases

`.github/workflows/ndmf-release-check.yml` runs weekly and opens (or refreshes) an issue when a stable NDMF release newer than the `Last verified: X.Y.Z` marker in `skills/ndmf-plugin-builder/references/version-compatibility.md` is published. That marker is the single source of truth the workflow parses — keep its format intact. Prereleases are listed in the issue for reference only and never trigger it.

When handling such an issue:

1. Read the release notes in the issue (or the upstream `CHANGELOG.md`) for anything that changes what the skill teaches: a new API worth documenting, or an existing one deprecated, moved, or removed (see "Known breaking/removed APIs" in `version-compatibility.md` for what that looks like). Most patch releases change nothing.
2. Before writing a version gate into the skill, confirm it against real source. Update NDMF in this Unity project (`Packages/vpm-manifest.json`) and verify empirically where behavior matters, rather than trusting the changelog wording alone.
3. Edit the skill with `skill-creator` (see "Skill improvements" above). Bump the `Last verified` marker and the file title's version range, plus any other "1.3.0 and X.Y.Z" ranges in `SKILL.md` and `references/` if new gated APIs were added. If `SKILL.md`'s `description` changed, re-run description optimization.
4. Even when nothing needs documenting, bump the marker so the issue doesn't come back; then close the issue from the commit (`Closes #N`).
