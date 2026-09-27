"""Run the LLM-driven agent through standardized scenarios.

    python benchmark.py --scenario hunger_test
    python benchmark.py --scenario all --parallel 2 --seed 7

Each run uses the exact same `CognitiveLoop.step()` as the live simulation.
By default the LLM "imagination" call is skipped (the world simulation still
tells Adam what each option really does); pass --imagine to include it.
--parallel N runs N episodes at once; set OLLAMA_NUM_PARALLEL>=N on the
Ollama server or the requests just queue.

Run i uses seed (--seed + i) for both the world and LLM sampling, so a
benchmark is reproducible while its runs still differ from each other.
(Ollama batching parallel requests can still introduce small differences.)
"""
import argparse
import os
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from statistics import mean

# Ensure project root is in path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from loop.cognitive_loop import CognitiveLoop
from services.psyche_client import PsycheClient
from constants import LOG_HEADERS
from scenario_runner import list_scenarios, load_scenario, run_episode
import config


def _run_one(name, scenario, run_idx, psyche, log_file, imagine_with_llm, seed):
    brain = CognitiveLoop(
        log_filename=log_file,
        log_headers=LOG_HEADERS,
        ui=None,
        experiment_tag=f"bench_{name}",
        agent_id="adam1",
        memory=None, # Disable long-term memory for sterile benchmark
        psyche=psyche,
    )
    brain.imagine_with_llm = imagine_with_llm
    brain.llm_seed = seed
    t0 = time.time()
    try:
        episode = run_episode(scenario, lambda world, _cycle: brain.step(world), seed=seed)
        outcome, cycles = episode["outcome"], episode["cycles"]
    except Exception as e:
        outcome, cycles = f"ERROR: {e}", brain.cycle_counter
        traceback.print_exc()
    return {"scenario": name, "run": run_idx, "outcome": outcome, "cycles": cycles,
            "seconds": time.time() - t0, "stats": Counter(brain.stats)}


def _rate(part, whole):
    return f"{part / whole:4.0%}" if whole else "  n/a"


def run_benchmark(names, runs=5, parallel=1, imagine_with_llm=False, psyche=None, log_file="benchmark.log", seed=0):
    """Run every (scenario, run) pair, `parallel` at a time. Returns {scenario: success rate %}."""
    if isinstance(names, str):
        names = [names]
    scenarios = {name: load_scenario(name).CONFIG for name in names}
    parallel = max(1, int(parallel))

    if psyche is None:
        print(f"Connecting to Psyche at: {config.PSYCHE_LLM_API_URL}")
        psyche = PsycheClient(
            config.PSYCHE_LLM_API_URL,
            # Parallel requests may queue behind each other on the Ollama server
            timeout=max(60.0, config.PSYCHE_TIMEOUT) * parallel,
            retries=config.PSYCHE_RETRIES,
            backoff=config.PSYCHE_BACKOFF,
        )

    jobs = [(name, i) for name in names for i in range(runs)]
    print(f"Scenarios: {', '.join(names)} | Runs each: {runs} | Seeds: {seed}..{seed + runs - 1} | Parallel: {parallel} | LLM imagination: {'on' if imagine_with_llm else 'off'}")
    if runs < 5:
        print("Note: fewer than 5 runs per scenario; success rates will be noisy.")
    print()
    started = time.time()
    results = []
    with ThreadPoolExecutor(max_workers=parallel) as pool:
        futures = [
            pool.submit(_run_one, name, scenarios[name], i, psyche, log_file, imagine_with_llm, seed + i)
            for name, i in jobs
        ]
        for future in as_completed(futures):
            r = future.result()
            results.append(r)
            print(f"{r['scenario']:<18} run {r['run'] + 1}/{runs}: [{r['outcome']}] in {r['cycles']} cycles ({r['seconds']:.0f}s)", flush=True)

    # Summary
    rates = {}
    print("\n--- Summary ---")
    print(f"{'scenario':<18} {'success':>14} {'avg cycles':>11}   {'rejected':>8} {'dropped':>8} {'fallback':>8}")
    total = Counter()
    for name in names:
        mine = [r for r in results if r["scenario"] == name]
        wins = [r for r in mine if r["outcome"] == "WIN"]
        rates[name] = len(wins) / len(mine) * 100
        avg_cycles = mean(r["cycles"] for r in wins) if wins else 0
        stats = sum((r["stats"] for r in mine), Counter())
        total += stats
        others = [r["outcome"] for r in mine if r["outcome"] != "WIN"]
        extra = f"  other outcomes: {others}" if others else ""
        print(f"{name:<18} {rates[name]:6.1f}% ({len(wins)}/{len(mine)}) {avg_cycles:11.1f}   "
              f"{_rate(stats['decisions_rejected'], stats['decisions']):>8} "
              f"{_rate(stats['impulses_dropped'], stats['impulses']):>8} "
              f"{_rate(stats['psyche_fallbacks'], stats['psyche_calls']):>8}{extra}")
    print("\nrejected = final decisions the world could not execute (replaced by the best valid impulse)")
    print("dropped  = impulses discarded as impossible before imagining")
    print("fallback = LLM calls that errored and returned a default answer")
    print(f"overall: rejected {_rate(total['decisions_rejected'], total['decisions']).strip()}, "
          f"dropped {_rate(total['impulses_dropped'], total['impulses']).strip()}, "
          f"fallback {_rate(total['psyche_fallbacks'], total['psyche_calls']).strip()}")
    print(f"\nTotal time: {(time.time() - started) / 60:.1f} min")
    return rates


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", type=str, required=True, help=f"Scenario name or 'all' ({', '.join(list_scenarios())})")
    parser.add_argument("--runs", type=int, default=5, help="Runs per scenario (default 5)")
    parser.add_argument("--seed", type=int, default=0, help="Base seed; run i uses seed+i for the world and the LLM")
    parser.add_argument("--parallel", type=int, default=1, help="Episodes to run at once (needs OLLAMA_NUM_PARALLEL >= this)")
    parser.add_argument("--imagine", action="store_true", help="Also ask the LLM to imagine each option (slower)")
    args = parser.parse_args()

    names = list_scenarios() if args.scenario == "all" else [args.scenario]
    run_benchmark(names, runs=args.runs, parallel=args.parallel, imagine_with_llm=args.imagine, seed=args.seed)
