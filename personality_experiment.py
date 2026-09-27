"""Does temperament change behaviour? Run the same worlds with different personalities.

    python personality_experiment.py --presets curious cautious --runs 5 --cycles 15
    python personality_experiment.py --presets curious cautious bold --parallel 2

Each preset plays the same seeded worlds (the default apartment, no goal, so
behaviour comes from needs and temperament). The script prints per-metric
means and standard deviations per preset, and appends the results to
results/benchmark_results.jsonl (kind "personality").
"""
import argparse
import copy
import os
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import config
from behavior_metrics import METRICS, METRIC_HELP, episode_metrics, summarize
from constants import LOG_HEADERS
from loop.cognitive_loop import CognitiveLoop
from personality import PRESETS, describe
from results_log import DEFAULT_RESULTS, append_results, run_context
from services.psyche_client import PsycheClient
from text_world import TextWorld


def run_personality_episode(preset: str, seed: int, cycles: int, psyche, log_file: str, trace: bool = False) -> dict:
    """One goal-free episode in the seeded default world; returns the steps taken and their metrics."""
    status = copy.deepcopy(config.AGENT_STATUS)
    status["personality"] = dict(PRESETS[preset])
    status["goal"] = ""
    brain = CognitiveLoop(log_file, LOG_HEADERS, experiment_tag=f"personality_{preset}", psyche=psyche,
                          initial_status=status)
    brain.imagine_with_llm = False
    brain.llm_seed = seed
    brain.trace = trace or brain.trace
    world = TextWorld(seed=seed)
    brain.attach_world(world)
    steps = []
    for _ in range(cycles):
        world.update()
        room_before = world.agent_location
        action, result = brain.step(world)
        steps.append({
            "verb": action.get("verb"), "target": action.get("target"), "success": bool(result.get("success")),
            "room_before": room_before, "room_after": world.agent_location,
        })
    return {"preset": preset, "seed": seed, "steps": steps,
            "metrics": episode_metrics(steps, total_rooms=len(world.map.grid)), "stats": dict(brain.stats)}


def run_experiment(presets, runs=5, cycles=15, parallel=1, seed=0, psyche=None,
                   log_file="personality_log.jsonl", results_path=DEFAULT_RESULTS, trace=False):
    unknown = [p for p in presets if p not in PRESETS]
    if unknown:
        raise SystemExit(f"Unknown preset(s) {unknown}; choose from {sorted(PRESETS)}")
    if psyche is None:
        psyche = PsycheClient(config.PSYCHE_LLM_API_URL, timeout=max(60.0, config.PSYCHE_TIMEOUT) * max(1, parallel),
                              retries=config.PSYCHE_RETRIES, backoff=config.PSYCHE_BACKOFF)
    print(f"Presets: {', '.join(f'{p} ({describe(PRESETS[p])})' for p in presets)}")
    print(f"Runs each: {runs} | Seeds: {seed}..{seed + runs - 1} | Cycles: {cycles} | Parallel: {parallel}\n")

    started = time.time()
    episodes = []
    with ThreadPoolExecutor(max_workers=max(1, parallel)) as pool:
        futures = [pool.submit(run_personality_episode, p, seed + i, cycles, psyche, log_file, trace)
                   for p in presets for i in range(runs)]
        for future in as_completed(futures):
            try:
                ep = future.result()
            except Exception:
                traceback.print_exc()
                continue
            episodes.append(ep)
            verbs = " ".join(s["verb"] for s in ep["steps"])
            print(f"{ep['preset']:<10} seed {ep['seed']}: {verbs}", flush=True)

    summary = {p: summarize([e["metrics"] for e in episodes if e["preset"] == p]) for p in presets}
    print("\n--- Behaviour by temperament (mean ± sd) ---")
    print(f"{'metric':<14}" + "".join(f"{p:>18}" for p in presets))
    for m in METRICS:
        row = "".join(f"{summary[p][m]['mean']:>11.2f} ± {summary[p][m]['sd']:.2f}" for p in presets)
        print(f"{m:<14}{row}")
    print()
    for m in METRICS:
        print(f"{m:<14} {METRIC_HELP[m]}")
    print(f"\nTotal time: {(time.time() - started) / 60:.1f} min")

    context = run_context(kind="personality", runs=runs, cycles=cycles, seeds=[seed, seed + runs - 1])
    append_results(
        [{**context, "preset": p, "personality": PRESETS[p], "summary": summary[p],
          "episodes": [e["metrics"] for e in episodes if e["preset"] == p]} for p in presets],
        results_path,
    )
    print(f"Results appended to {results_path}")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--presets", nargs="+", default=["curious", "cautious"], help=f"Choose from {sorted(PRESETS)}")
    parser.add_argument("--runs", type=int, default=5, help="Episodes per preset (default 5)")
    parser.add_argument("--cycles", type=int, default=15, help="Cycles per episode (default 15)")
    parser.add_argument("--seed", type=int, default=0, help="Base seed; episode i uses seed+i (same worlds for every preset)")
    parser.add_argument("--parallel", type=int, default=1, help="Episodes to run at once (needs OLLAMA_NUM_PARALLEL >= this)")
    parser.add_argument("--trace", action="store_true", help="Log each cycle's prompts and raw LLM replies (large)")
    args = parser.parse_args()
    run_experiment(args.presets, runs=args.runs, cycles=args.cycles, parallel=args.parallel, seed=args.seed, trace=args.trace)
