"""Do habits emerge? Run Adam for a long time and watch his behaviour settle (or not).

    python habits_experiment.py --cycles 200
    python habits_experiment.py --cycles 200 --runs 3 --preset curious

Adam lives goal-free in the seeded default apartment with a fresh long-term
memory, so needs, temperament and what he remembers drive him. The run is
split into windows; for each window the script reports how varied his
actions are (entropy), how many actions are new, and how much the action mix
drifted from the previous window. Falling entropy and drift mean habits are
forming. It also lists his favourite actions and recurring routines, and
appends a "habits" record to results/benchmark_results.jsonl.
"""
import argparse
import copy
import os
import sys
import tempfile
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import config
from behavior_metrics import habit_windows, top_actions, top_routines
from constants import LOG_HEADERS
from loop.cognitive_loop import CognitiveLoop
from personality import PRESETS, describe
from results_log import DEFAULT_RESULTS, append_results, run_context
from services.psyche_client import PsycheClient
from text_world import TextWorld


def run_long_episode(cycles, seed, psyche, log_file, preset=None, memory=None, single_call=False, progress=None):
    status = copy.deepcopy(config.AGENT_STATUS)
    status["goal"] = ""
    if preset:
        status["personality"] = dict(PRESETS[preset])
    brain = CognitiveLoop(log_file, LOG_HEADERS, experiment_tag=f"habits_{preset or 'default'}", psyche=psyche,
                          memory=memory, initial_status=status)
    brain.imagine_with_llm = False
    brain.llm_seed = seed
    brain.single_call = single_call or brain.single_call
    world = TextWorld(seed=seed)
    brain.attach_world(world)
    steps = []
    for cycle in range(1, cycles + 1):
        world.update()
        action, result = brain.step(world)
        steps.append({"verb": action.get("verb"), "target": action.get("target"), "success": bool(result.get("success"))})
        if progress and cycle % 10 == 0:
            progress(cycle, steps)
    return steps, brain


def run_experiment(cycles=200, runs=1, seed=0, window=20, preset=None, psyche=None, use_memory=True,
                   memory_factory=None, single_call=False, log_file="habits_log.jsonl", results_path=DEFAULT_RESULTS):
    if psyche is None:
        psyche = PsycheClient(config.PSYCHE_LLM_API_URL, timeout=max(60.0, config.PSYCHE_TIMEOUT),
                              retries=config.PSYCHE_RETRIES, backoff=config.PSYCHE_BACKOFF)
    who = f"{preset} ({describe(PRESETS[preset])})" if preset else "default temperament"
    print(f"Habits: {runs} run(s) x {cycles} cycles | {who} | memory: {'on' if use_memory else 'off'} | window {window}\n")
    started = time.time()
    records = []
    for i in range(runs):
        run_seed = seed + i
        with tempfile.TemporaryDirectory(prefix="adam-habits-") as tmp:
            memory = None
            if use_memory:
                if memory_factory is None:
                    from benchmark import default_memory_factory as memory_factory
                memory = memory_factory(tmp)
            steps, _ = run_long_episode(
                cycles, run_seed, psyche, log_file, preset=preset, memory=memory, single_call=single_call,
                progress=lambda c, s: print(f"  seed {run_seed}: {c}/{cycles} cycles", flush=True))
        windows = habit_windows(steps, window)
        print(f"\n--- Seed {run_seed} ---")
        print(f"{'cycles':<10} {'entropy':>8} {'new':>5} {'drift':>7}   most common")
        for w in windows:
            drift = "" if w["drift"] is None else f"{w['drift']:.3f}"
            print(f"{w['cycles']:<10} {w['entropy']:>8.3f} {w['new_actions']:>5} {drift:>7}   {w['top']}")
        print("Favourite actions:", ", ".join(f"{a} ({p:.0%})" for a, p in top_actions(steps)))
        print("Routines:", "; ".join(f"{' -> '.join(seq)} (x{n})" for seq, n in top_routines(steps)) or "none")
        records.append({"seed": run_seed, "windows": windows, "top_actions": top_actions(steps),
                        "routines": [[list(seq), n] for seq, n in top_routines(steps)]})
    print("\nentropy = how varied actions are (0 = one action only); new = actions never seen before;")
    print("drift = how much the action mix changed from the previous window (0 = identical). Falling values = habits.")
    print(f"Total time: {(time.time() - started) / 60:.1f} min")
    append_results([{**run_context(kind="habits", cycles=cycles, window=window, preset=preset, memory=use_memory,
                                   single_call=bool(single_call or config.SINGLE_CALL)), "runs": records}], results_path)
    print(f"Results appended to {results_path}")
    return records


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cycles", type=int, default=200, help="Cycles per run (default 200)")
    parser.add_argument("--runs", type=int, default=1, help="Independent runs (seeds seed..seed+runs-1)")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--window", type=int, default=20, help="Cycles per analysis window")
    parser.add_argument("--preset", choices=sorted(PRESETS), help="Temperament preset (default: from .env)")
    parser.add_argument("--no-memory", action="store_true", help="Run without long-term memory")
    parser.add_argument("--single-call", action="store_true", help="One LLM call per cycle (faster)")
    args = parser.parse_args()
    run_experiment(args.cycles, args.runs, args.seed, args.window, args.preset, use_memory=not args.no_memory,
                   single_call=args.single_call)
