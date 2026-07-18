# Agent Instructions

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/) for all commit messages (e.g. `feat: ...`, `fix: ...`, `docs: ...`, `chore: ...`).

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
