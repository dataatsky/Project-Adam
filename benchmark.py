"""Run the LLM-driven agent through standardized scenarios.

    python benchmark.py --scenario hunger_test --runs 5
    python benchmark.py --scenario all

Each run uses the exact same `CognitiveLoop.step()` as the live simulation.
"""
import argparse
import os
import sys
import traceback
from statistics import mean

# Ensure project root is in path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from loop.cognitive_loop import CognitiveLoop
from services.psyche_client import PsycheClient
from constants import LOG_HEADERS
from scenario_runner import list_scenarios, load_scenario, run_episode
import config


def run_benchmark(scenario_name, runs, psyche=None, log_file="benchmark.log"):
    scenario = load_scenario(scenario_name).CONFIG
    print(f"Starting Benchmark: {scenario['name']} ({scenario['description']})")
    print(f"Runs: {runs} | Max Cycles: {scenario['max_cycles']}\n")

    if psyche is None:
        print(f"Connecting to Psyche at: {config.PSYCHE_LLM_API_URL}")
        psyche = PsycheClient(
            config.PSYCHE_LLM_API_URL,
            timeout=max(60.0, config.PSYCHE_TIMEOUT),
            retries=config.PSYCHE_RETRIES,
            backoff=config.PSYCHE_BACKOFF,
        )

    results = []
    for i in range(runs):
        print(f"Run {i+1}/{runs}...", end=" ", flush=True)
        brain = CognitiveLoop(
            log_filename=log_file,
            log_headers=LOG_HEADERS,
            ui=None,
            experiment_tag=f"bench_{scenario_name}",
            agent_id="adam1",
            memory=None, # Disable long-term memory for sterile benchmark
            psyche=psyche,
        )
        try:
            # Deterministic seeding per run index
            episode = run_episode(scenario, lambda world, _cycle: brain.step(world), seed=i)
            outcome, cycles = episode["outcome"], episode["cycles"]
        except Exception as e:
            outcome, cycles = f"ERROR: {e}", brain.cycle_counter
            traceback.print_exc()

        print(f"[{outcome}] in {cycles} cycles.")
        results.append({"outcome": outcome, "cycles": cycles})

    # Summary
    wins = [r for r in results if r["outcome"] == "WIN"]
    success_rate = (len(wins) / runs) * 100
    avg_cycles = mean([r["cycles"] for r in wins]) if wins else 0

    print("\n--- Summary ---")
    print(f"Scenario: {scenario_name}")
    print(f"Success Rate: {success_rate:.1f}% ({len(wins)}/{runs})")
    print(f"Avg Cycles (Wins): {avg_cycles:.1f}")
    if success_rate < 100:
        print(f"Failed Outcomes: {[r['outcome'] for r in results if r['outcome'] != 'WIN']}")

    return success_rate


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", type=str, required=True, help=f"Scenario name or 'all' ({', '.join(list_scenarios())})")
    parser.add_argument("--runs", type=int, default=1, help="Number of runs")
    args = parser.parse_args()

    names = list_scenarios() if args.scenario == "all" else [args.scenario]
    rates = {name: run_benchmark(name, args.runs) for name in names}
    if len(rates) > 1:
        print("\n=== Overall ===")
        for name, rate in rates.items():
            print(f"{name:<20} {rate:5.1f}%")
