"""Run the LLM-driven agent through standardized scenarios.

    python benchmark.py --scenario hunger_test --runs 5
    python benchmark.py --scenario all --parallel 2

Each run uses the exact same `CognitiveLoop.step()` as the live simulation.
By default the LLM "imagination" call is skipped (the world simulation still
tells Adam what each option really does); pass --imagine to include it.
--parallel N runs N episodes at once; set OLLAMA_NUM_PARALLEL>=N on the
Ollama server or the requests just queue.
"""
import argparse
import os
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from statistics import mean

# Ensure project root is in path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from loop.cognitive_loop import CognitiveLoop
from services.psyche_client import PsycheClient
from constants import LOG_HEADERS
from scenario_runner import list_scenarios, load_scenario, run_episode
import config


def _run_one(name, scenario, run_idx, psyche, log_file, imagine_with_llm):
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
    t0 = time.time()
    try:
        # Deterministic seeding per run index
        episode = run_episode(scenario, lambda world, _cycle: brain.step(world), seed=run_idx)
        outcome, cycles = episode["outcome"], episode["cycles"]
    except Exception as e:
        outcome, cycles = f"ERROR: {e}", brain.cycle_counter
        traceback.print_exc()
    return {"scenario": name, "run": run_idx, "outcome": outcome, "cycles": cycles, "seconds": time.time() - t0}


def run_benchmark(names, runs=1, parallel=1, imagine_with_llm=False, psyche=None, log_file="benchmark.log"):
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
    print(f"Scenarios: {', '.join(names)} | Runs each: {runs} | Parallel: {parallel} | LLM imagination: {'on' if imagine_with_llm else 'off'}\n")
    started = time.time()
    results = []
    with ThreadPoolExecutor(max_workers=parallel) as pool:
        futures = [
            pool.submit(_run_one, name, scenarios[name], i, psyche, log_file, imagine_with_llm)
            for name, i in jobs
        ]
        for future in as_completed(futures):
            r = future.result()
            results.append(r)
            print(f"{r['scenario']:<18} run {r['run'] + 1}/{runs}: [{r['outcome']}] in {r['cycles']} cycles ({r['seconds']:.0f}s)", flush=True)

    # Summary
    rates = {}
    print("\n--- Summary ---")
    for name in names:
        mine = [r for r in results if r["scenario"] == name]
        wins = [r for r in mine if r["outcome"] == "WIN"]
        rates[name] = len(wins) / len(mine) * 100
        avg_cycles = mean(r["cycles"] for r in wins) if wins else 0
        others = [r["outcome"] for r in mine if r["outcome"] != "WIN"]
        extra = f" | other outcomes: {others}" if others else ""
        print(f"{name:<18} success {rates[name]:5.1f}% ({len(wins)}/{len(mine)}) | avg cycles (wins) {avg_cycles:4.1f}{extra}")
    print(f"\nTotal time: {(time.time() - started) / 60:.1f} min")
    return rates


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", type=str, required=True, help=f"Scenario name or 'all' ({', '.join(list_scenarios())})")
    parser.add_argument("--runs", type=int, default=1, help="Runs per scenario")
    parser.add_argument("--parallel", type=int, default=1, help="Episodes to run at once (needs OLLAMA_NUM_PARALLEL >= this)")
    parser.add_argument("--imagine", action="store_true", help="Also ask the LLM to imagine each option (slower)")
    args = parser.parse_args()

    names = list_scenarios() if args.scenario == "all" else [args.scenario]
    run_benchmark(names, runs=args.runs, parallel=args.parallel, imagine_with_llm=args.imagine)
