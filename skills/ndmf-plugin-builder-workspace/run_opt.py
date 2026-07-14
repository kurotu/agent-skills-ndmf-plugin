"""Serial, checkpointed description-optimization loop.

Replicates scripts/run_loop.py (same train/test split, scoring, and
improvement prompt) but runs queries one at a time and checkpoints after
every single query run, so a killed process resumes exactly where it left
off by re-running the same command.

Usage:
    python run_opt.py            # start or resume
    python run_opt.py --status   # print progress without running anything
"""

import hashlib
import json
import os
import sys
import time
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent
SKILL_CREATOR = Path(
    r"C:\Users\yuya-oc\.claude\plugins\cache\claude-plugins-official"
    r"\skill-creator\unknown\skills\skill-creator"
)
sys.path.insert(0, str(SKILL_CREATOR))
sys.path.insert(0, str(WORKSPACE))

import win_fix
from scripts.improve_description import improve_description
from scripts.run_eval import find_project_root
from scripts.run_loop import split_eval_set
from scripts.utils import parse_skill_md

SKILL_PATH = WORKSPACE.parent / "ndmf-plugin-builder"
EVAL_SET_PATH = SKILL_PATH / "evals" / "trigger-eval.json"
DRAFT_PATH = WORKSPACE / "draft-description.txt"
STATE_PATH = WORKSPACE / "opt-serial-state.json"
RESULT_PATH = WORKSPACE / "opt-serial-result.json"
IMPROVE_LOG_DIR = WORKSPACE / "opt-serial-improve-logs"

MODEL = "sonnet"
RUNS_PER_QUERY = 3
TIMEOUT = 60
MAX_ITERATIONS = 5
THRESHOLD = 0.5
HOLDOUT = 0.4


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


def save_state(state: dict) -> None:
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, STATE_PATH)


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"baseline": {"runs": {}, "done": False}, "iterations": [], "done": False}


def eval_description(label: str, description: str, all_queries: list[dict],
                     runs: dict, state: dict, skill_name: str,
                     project_root: str) -> list[dict]:
    """Evaluate a description over all queries, checkpointing every run."""
    total_runs = len(all_queries) * RUNS_PER_QUERY
    for qidx, item in enumerate(all_queries):
        for ridx in range(RUNS_PER_QUERY):
            key = f"{qidx}|{ridx}"
            if key in runs:
                continue
            done_count = len(runs)
            log(f"{label}: run {done_count + 1}/{total_runs} "
                f"(q{qidx} r{ridx}, expect={item['should_trigger']}): {item['query'][:50]}")
            try:
                triggered = win_fix.run_single_query(
                    item["query"], skill_name, description, TIMEOUT,
                    project_root, MODEL,
                )
            except Exception as e:
                log(f"  WARNING: query failed ({e}); recording as not triggered")
                triggered = False
            runs[key] = triggered
            save_state(state)

    results = []
    for qidx, item in enumerate(all_queries):
        triggers = [runs[f"{qidx}|{ridx}"] for ridx in range(RUNS_PER_QUERY)]
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
    return results


def summarize(results: list[dict]) -> dict:
    passed = sum(1 for r in results if r["pass"])
    return {"passed": passed, "failed": len(results) - passed, "total": len(results)}


def print_status(state: dict, n_queries: int) -> None:
    total = n_queries * RUNS_PER_QUERY
    b = state["baseline"]
    print(f"baseline: {'done' if b['done'] else f'{len(b['runs'])}/{total} runs'}")
    for i, it in enumerate(state["iterations"], start=1):
        if "train_summary" in it:
            ts = it["train_summary"]
            xs = it["test_summary"]
            status = f"train {ts['passed']}/{ts['total']}, test {xs['passed']}/{xs['total']}"
        else:
            status = f"{len(it['runs'])}/{total} runs"
        print(f"iteration {i}: {status} (desc {len(it['description'])} chars)")
    print(f"done: {state['done']}")


def main() -> None:
    eval_set = json.loads(EVAL_SET_PATH.read_text(encoding="utf-8"))
    train_set, test_set = split_eval_set(eval_set, HOLDOUT)
    all_queries = train_set + test_set
    train_queries = {q["query"] for q in train_set}

    skill_name, original_description, skill_content = parse_skill_md(SKILL_PATH)
    # Optimization starts from a hand-written draft when one is provided;
    # otherwise from the description currently in SKILL.md.
    if DRAFT_PATH.exists():
        draft_description = DRAFT_PATH.read_text(encoding="utf-8").strip()
    else:
        draft_description = original_description
    project_root = str(find_project_root())

    state = load_state()

    if "--status" in sys.argv:
        print_status(state, len(all_queries))
        return

    # Checkpoints are only valid for the descriptions they were run against.
    config_sha = hashlib.sha256(
        (original_description + "\n---\n" + draft_description).encode("utf-8")
    ).hexdigest()[:12]
    if state.get("config_sha") not in (None, config_sha):
        sys.exit(
            f"{STATE_PATH.name} belongs to a different description "
            f"configuration — delete it to start a fresh optimization run"
        )
    state["config_sha"] = config_sha

    log(f"split: {len(train_set)} train / {len(test_set)} test; "
        f"project_root={project_root}; model={MODEL}")

    # Phase 1: baseline score of the current (long) description in SKILL.md
    if not state["baseline"]["done"]:
        log("=== baseline: evaluating current SKILL.md description ===")
        results = eval_description("baseline", original_description, all_queries,
                                   state["baseline"]["runs"], state,
                                   skill_name, project_root)
        state["baseline"]["results"] = results
        state["baseline"]["summary"] = summarize(results)
        state["baseline"]["done"] = True
        save_state(state)
        log(f"baseline score: {state['baseline']['summary']['passed']}"
            f"/{state['baseline']['summary']['total']}")

    # Phase 2: optimization iterations starting from the short draft
    if not state["iterations"]:
        state["iterations"].append({"description": draft_description, "runs": {}})
        save_state(state)

    while not state["done"]:
        i = len(state["iterations"])
        cur = state["iterations"][-1]

        if "train_summary" not in cur:
            log(f"=== iteration {i}/{MAX_ITERATIONS}: evaluating "
                f"({len(cur['description'])} chars) ===")
            results = eval_description(f"iter{i}", cur["description"], all_queries,
                                       cur["runs"], state, skill_name, project_root)
            cur["train_results"] = [r for r in results if r["query"] in train_queries]
            cur["test_results"] = [r for r in results if r["query"] not in train_queries]
            cur["train_summary"] = summarize(cur["train_results"])
            cur["test_summary"] = summarize(cur["test_results"])
            save_state(state)
            log(f"iteration {i} score: train {cur['train_summary']['passed']}"
                f"/{cur['train_summary']['total']}, test {cur['test_summary']['passed']}"
                f"/{cur['test_summary']['total']}")

        if cur["train_summary"]["failed"] == 0:
            state["exit_reason"] = f"all_train_passed (iteration {i})"
            state["done"] = True
            save_state(state)
            break
        if i >= MAX_ITERATIONS:
            state["exit_reason"] = f"max_iterations ({MAX_ITERATIONS})"
            state["done"] = True
            save_state(state)
            break

        if "next_description" not in cur:
            log(f"iteration {i}: improving description...")
            # History for the improver: train data only (test stays blind)
            history = [
                {
                    "description": it["description"],
                    "train_passed": it["train_summary"]["passed"],
                    "train_total": it["train_summary"]["total"],
                    "passed": it["train_summary"]["passed"],
                    "failed": it["train_summary"]["failed"],
                    "total": it["train_summary"]["total"],
                    "results": it["train_results"],
                }
                for it in state["iterations"]
            ]
            cur["next_description"] = improve_description(
                skill_name=skill_name,
                skill_content=skill_content,
                current_description=cur["description"],
                eval_results={"results": cur["train_results"],
                              "summary": cur["train_summary"]},
                history=history,
                model=MODEL,
                log_dir=IMPROVE_LOG_DIR,
                iteration=i,
            )
            save_state(state)
            log(f"iteration {i}: proposed ({len(cur['next_description'])} chars): "
                f"{cur['next_description'][:120]}...")

        state["iterations"].append({"description": cur["next_description"], "runs": {}})
        save_state(state)

    # Final: pick best iteration by test score (ties -> earlier/shorter wins
    # via max() keeping the first maximum)
    best = max(state["iterations"], key=lambda it: it["test_summary"]["passed"])
    result = {
        "exit_reason": state["exit_reason"],
        "model": MODEL,
        "baseline_description": original_description,
        "baseline_score": f"{state['baseline']['summary']['passed']}"
                          f"/{state['baseline']['summary']['total']}",
        "best_description": best["description"],
        "best_train_score": f"{best['train_summary']['passed']}"
                            f"/{best['train_summary']['total']}",
        "best_test_score": f"{best['test_summary']['passed']}"
                           f"/{best['test_summary']['total']}",
        "iterations_run": len(state["iterations"]),
        "iteration_scores": [
            {
                "iteration": idx + 1,
                "chars": len(it["description"]),
                "train": f"{it['train_summary']['passed']}/{it['train_summary']['total']}",
                "test": f"{it['test_summary']['passed']}/{it['test_summary']['total']}",
            }
            for idx, it in enumerate(state["iterations"])
        ],
    }
    RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    log(f"DONE: {json.dumps(result['iteration_scores'])}")
    log(f"result written to {RESULT_PATH}")


if __name__ == "__main__":
    main()
