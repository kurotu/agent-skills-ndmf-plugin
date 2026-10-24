"""Serial, checkpointed trigger evaluation of one or more descriptions.

Evaluates the old (pre-optimization) description and the new one currently
in SKILL.md against the full eval set, one query at a time, checkpointing
after every run. Re-running the same command resumes where it left off.

Usage:
    python run_eval_serial.py --model haiku            # start or resume
    python run_eval_serial.py --model haiku --status   # progress only
"""

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent
sys.path.insert(0, str(WORKSPACE))

import win_fix

sys.path.insert(0, str(win_fix.find_skill_creator()))

from scripts.utils import parse_skill_md

SKILL_PATH = WORKSPACE.parent / "ndmf-plugin-builder"
EVAL_SET_PATH = SKILL_PATH / "evals" / "trigger-eval.json"
OPT_RESULT_PATH = WORKSPACE / "opt-serial-result.json"

RUNS_PER_QUERY = 3
TIMEOUT = 60
THRESHOLD = 0.5


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    state_path = WORKSPACE / f"eval-serial-state-{args.model}.json"
    result_path = WORKSPACE / f"eval-serial-result-{args.model}.json"

    def save_state(state: dict) -> None:
        tmp = state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        os.replace(tmp, state_path)

    eval_set = json.loads(EVAL_SET_PATH.read_text(encoding="utf-8"))
    skill_name, current_description, _ = parse_skill_md(SKILL_PATH)
    # Not find_project_root(): from inside this repo the eval sessions would
    # see its CLAUDE.md and the skill's own files, unlike a real user.
    project_root = str(Path.home())

    # Always evaluate the description currently in SKILL.md ("new"). If a
    # past optimization result is around, also evaluate the
    # pre-optimization description ("old") for comparison.
    subjects = [("new", current_description)]
    if OPT_RESULT_PATH.exists():
        old_description = json.loads(
            OPT_RESULT_PATH.read_text(encoding="utf-8"))["baseline_description"]
        subjects.insert(0, ("old", old_description))

    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
    else:
        state = {}
    # Checkpoints are only valid for the exact description they were run
    # against — reset a subject's state whenever its description changed.
    for label, description in subjects:
        digest = hashlib.sha256(description.encode("utf-8")).hexdigest()[:12]
        if state.get(label, {}).get("description_sha") != digest:
            state[label] = {"runs": {}, "description_sha": digest}

    total = len(eval_set) * RUNS_PER_QUERY
    if args.status:
        for label, _ in subjects:
            s = state[label]
            if "summary" in s:
                print(f"{label}: done, {s['summary']['passed']}/{s['summary']['total']}")
            else:
                print(f"{label}: {len(s['runs'])}/{total} runs")
        return

    log(f"model={args.model}; {len(eval_set)} queries x {RUNS_PER_QUERY} runs "
        f"x {len(subjects)} descriptions; project_root={project_root}")

    for label, description in subjects:
        s = state[label]
        if "summary" in s:
            continue
        log(f"=== {label} ({len(description)} chars) ===")
        for qidx, item in enumerate(eval_set):
            for ridx in range(RUNS_PER_QUERY):
                key = f"{qidx}|{ridx}"
                if key in s["runs"]:
                    continue
                log(f"{label}: run {len(s['runs']) + 1}/{total} "
                    f"(q{qidx} r{ridx}, expect={item['should_trigger']}): "
                    f"{item['query'][:50]}")
                attempts = 0
                while True:
                    try:
                        triggered = win_fix.run_single_query(
                            item["query"], skill_name, description, TIMEOUT,
                            project_root, args.model,
                        )
                        break
                    except Exception as e:
                        attempts += 1
                        log(f"  WARNING: attempt {attempts}/5 failed: {e}")
                        if attempts >= 5:
                            log("  persistent errors — stopping; state is "
                                "saved, re-run the same command to resume")
                            sys.exit(1)
                        time.sleep(30)
                s["runs"][key] = triggered
                save_state(state)

        results = []
        for qidx, item in enumerate(eval_set):
            triggers = [s["runs"][f"{qidx}|{ridx}"] for ridx in range(RUNS_PER_QUERY)]
            rate = sum(triggers) / len(triggers)
            should = item["should_trigger"]
            results.append({
                "query": item["query"],
                "should_trigger": should,
                "trigger_rate": rate,
                "triggers": sum(triggers),
                "runs": len(triggers),
                "pass": rate >= THRESHOLD if should else rate < THRESHOLD,
            })
        passed = sum(1 for r in results if r["pass"])
        s["results"] = results
        s["summary"] = {"passed": passed, "failed": len(results) - passed,
                        "total": len(results)}
        save_state(state)
        log(f"{label} score: {passed}/{len(results)}")

    result = {
        "model": args.model,
        "subjects": {
            label: {
                "chars": len(description),
                "score": f"{state[label]['summary']['passed']}"
                         f"/{state[label]['summary']['total']}",
                "failures": [
                    {"query": r["query"], "should_trigger": r["should_trigger"],
                     "trigger_rate": r["trigger_rate"]}
                    for r in state[label]["results"] if not r["pass"]
                ],
            }
            for label, description in subjects
        },
    }
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    log(f"DONE: {json.dumps({k: v['score'] for k, v in result['subjects'].items()})}")
    log(f"result written to {result_path}")


if __name__ == "__main__":
    main()
