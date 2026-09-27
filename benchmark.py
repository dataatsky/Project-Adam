"""Run the LLM-driven agent through standardized scenarios.

    python benchmark.py --scenario hunger_test
    python benchmark.py --scenario all --parallel 2 --seed 7
    python benchmark.py --scenario held-out          # only when validating a change
    python benchmark.py --history                    # past results

Each run uses the exact same `CognitiveLoop.step()` as the live simulation.
By default the LLM "imagination" call is skipped (the world simulation still
tells Adam what each option really does); pass --imagine to include it.
--parallel N runs N episodes at once; set OLLAMA_NUM_PARALLEL>=N on the
Ollama server or the requests just queue.

Run i uses seed (--seed + i) for both the world and LLM sampling, so a
benchmark is reproducible while its runs still differ from each other.
(Ollama batching parallel requests can still introduce small differences.)

Scenarios marked `held_out` are left out of `--scenario all`: they are for
checking that a prompt change generalizes, not for tuning against.

Scenarios with `memory_training` first play a training episode that writes
to a fresh long-term memory, then the scored episode with that memory, and
the same scored episode without memory as a control.

Every run appends one record per scenario to results/benchmark_results.jsonl.
"""
import argparse
import os
import sys
import tempfile
import time
import traceback
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from statistics import mean

# Ensure project root is in path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from loop.cognitive_loop import CognitiveLoop
from services.psyche_client import PsycheClient
from constants import LOG_HEADERS
from results_log import DEFAULT_RESULTS, append_results, format_rate, read_results, run_context, wilson_interval
from scenario_runner import list_scenarios, load_scenario, run_episode
import config


def default_memory_factory(directory: str):
    """A fresh, empty long-term memory in `directory` (Chroma + the configured embedding model)."""
    from services.memory_store import MemoryStore

    return MemoryStore(
        api_key=None, environment=None, index_name="benchmark-memory", model_name=config.SENTENCE_MODEL,
        backend="chroma", chroma_path=directory, batch_size=1,
    )


def _play(name, scenario, psyche, log_file, imagine_with_llm, seed, memory=None, tag_suffix=""):
    brain = CognitiveLoop(
        log_filename=log_file,
        log_headers=LOG_HEADERS,
        ui=None,
        experiment_tag=f"bench_{name}{tag_suffix}",
        agent_id="adam1",
        memory=memory,  # None = sterile run with no long-term memory
        psyche=psyche,
    )
    brain.imagine_with_llm = imagine_with_llm
    brain.llm_seed = seed
    episode = run_episode(scenario, lambda world, _cycle: brain.step(world), seed=seed)
    if memory is not None and hasattr(memory, "flush"):
        memory.flush()
    return episode, brain


def _run_one(name, scenario, run_idx, psyche, log_file, imagine_with_llm, seed, memory_factory=None):
    t0 = time.time()
    stats = Counter()
    extra = {}
    try:
        training = scenario.get("memory_training")
        if training:
            with tempfile.TemporaryDirectory(prefix="adam-memory-") as tmp:
                store = (memory_factory or default_memory_factory)(tmp)
                learn, brain = _play(name, {**scenario, **training}, psyche, log_file, imagine_with_llm, seed,
                                     memory=store, tag_suffix="_training")
                stats += brain.stats
                episode, brain = _play(name, scenario, psyche, log_file, imagine_with_llm, seed, memory=store)
                stats += brain.stats
            control, brain_c = _play(name, scenario, psyche, log_file, imagine_with_llm, seed, tag_suffix="_no_memory")
            stats += brain_c.stats
            extra = {"training": learn["outcome"], "without_memory": control["outcome"]}
        else:
            episode, brain = _play(name, scenario, psyche, log_file, imagine_with_llm, seed)
            stats += brain.stats
        outcome, cycles = episode["outcome"], episode["cycles"]
    except Exception as e:
        outcome, cycles = f"ERROR: {e}", 0
        traceback.print_exc()
    return {"scenario": name, "run": run_idx, "seed": seed, "outcome": outcome, "cycles": cycles,
            "seconds": time.time() - t0, "stats": stats, **extra}


def _rate(part, whole):
    return f"{part / whole:4.0%}" if whole else "  n/a"


def run_benchmark(names, runs=5, parallel=1, imagine_with_llm=False, psyche=None, log_file="benchmark_log.jsonl", seed=0,
                  results_path=DEFAULT_RESULTS, memory_factory=None):
    """Run every (scenario, run) pair, `parallel` at a time. Returns {scenario: success rate %}."""
    if isinstance(names, str):
        names = [names]
    modules = {name: load_scenario(name) for name in names}
    scenarios = {name: m.CONFIG for name, m in modules.items()}
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
            pool.submit(_run_one, name, scenarios[name], i, psyche, log_file, imagine_with_llm, seed + i, memory_factory)
            for name, i in jobs
        ]
        for future in as_completed(futures):
            r = future.result()
            results.append(r)
            memo = f" | training: {r['training']}, without memory: {r['without_memory']}" if "training" in r else ""
            print(f"{r['scenario']:<18} run {r['run'] + 1}/{runs}: [{r['outcome']}] in {r['cycles']} cycles ({r['seconds']:.0f}s){memo}", flush=True)

    # Summary
    rates = {}
    records = []
    context = run_context(kind="benchmark", runs=runs, seeds=[seed, seed + runs - 1], parallel=parallel,
                          imagine=imagine_with_llm)
    print("\n--- Summary (success with 95% interval) ---")
    print(f"{'scenario':<18} {'success':>20} {'avg cycles':>11}   {'rejected':>8} {'dropped':>8} {'fallback':>8}")
    total = Counter()
    for name in names:
        mine = sorted((r for r in results if r["scenario"] == name), key=lambda r: r["run"])
        wins = [r for r in mine if r["outcome"] == "WIN"]
        rates[name] = len(wins) / len(mine) * 100
        avg_cycles = mean(r["cycles"] for r in wins) if wins else 0
        stats = sum((r["stats"] for r in mine), Counter())
        total += stats
        others = [r["outcome"] for r in mine if r["outcome"] != "WIN"]
        extra = f"  other outcomes: {others}" if others else ""
        tag = f"{name}{' *' if scenarios[name].get('held_out') else ''}"
        print(f"{tag:<18} {format_rate(len(wins), len(mine)):>13} ({len(wins)}/{len(mine)}) {avg_cycles:11.1f}   "
              f"{_rate(stats['decisions_rejected'], stats['decisions']):>8} "
              f"{_rate(stats['impulses_dropped'], stats['impulses']):>8} "
              f"{_rate(stats['psyche_fallbacks'], stats['psyche_calls']):>8}{extra}")
        record = {**context, "scenario": name, "held_out": bool(scenarios[name].get("held_out")),
                  "wins": len(wins), "n": len(mine), "success_rate": len(wins) / len(mine),
                  "ci95": list(wilson_interval(len(wins), len(mine))), "avg_cycles_wins": avg_cycles,
                  "outcomes": [r["outcome"] for r in mine], "stats": dict(stats)}
        if any("without_memory" in r for r in mine):
            control_wins = sum(1 for r in mine if r.get("without_memory") == "WIN")
            print(f"{'  without memory':<18} {format_rate(control_wins, len(mine)):>13} ({control_wins}/{len(mine)})")
            record["without_memory"] = {"wins": control_wins, "n": len(mine)}
        records.append(record)
    if any(s.get("held_out") for s in scenarios.values()):
        print("* held-out scenario: use to check generalization, don't tune prompts against it")
    print("\nrejected = final decisions the world could not execute (replaced by the best valid impulse)")
    print("dropped  = impulses discarded as impossible before imagining")
    print("fallback = LLM calls that errored and returned a default answer")
    print(f"overall: rejected {_rate(total['decisions_rejected'], total['decisions']).strip()}, "
          f"dropped {_rate(total['impulses_dropped'], total['impulses']).strip()}, "
          f"fallback {_rate(total['psyche_fallbacks'], total['psyche_calls']).strip()}")
    print(f"\nTotal time: {(time.time() - started) / 60:.1f} min")
    if results_path:
        append_results(records, results_path)
        print(f"Results appended to {results_path}")
    return rates


def print_history(path=DEFAULT_RESULTS, scenario=None, last=10):
    """Past benchmark results per scenario, newest last."""
    rows = [r for r in read_results(path, kind="benchmark") if scenario in (None, r["scenario"])]
    if not rows:
        print(f"No benchmark results in {path} yet.")
        return
    by_scenario = defaultdict(list)
    for r in rows:
        by_scenario[r["scenario"]].append(r)
    for name, items in by_scenario.items():
        print(f"\n{name}{' (held out)' if items[-1].get('held_out') else ''}")
        print(f"  {'time':<20} {'git':<16} {'model':<14} {'success':>20}  fallback")
        for r in items[-last:]:
            st = r.get("stats", {})
            fb = _rate(st.get("psyche_fallbacks", 0), st.get("psyche_calls", 0)).strip()
            print(f"  {r['time']:<20} {r['git']:<16} {r['model']:<14} {format_rate(r['wins'], r['n']):>13} ({r['wins']}/{r['n']})  {fb}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scenario", type=str, help=f"Scenario name, 'all' (tuning set) or 'held-out' ({', '.join(list_scenarios())})")
    parser.add_argument("--runs", type=int, default=5, help="Runs per scenario (default 5)")
    parser.add_argument("--seed", type=int, default=0, help="Base seed; run i uses seed+i for the world and the LLM")
    parser.add_argument("--parallel", type=int, default=1, help="Episodes to run at once (needs OLLAMA_NUM_PARALLEL >= this)")
    parser.add_argument("--imagine", action="store_true", help="Also ask the LLM to imagine each option (slower)")
    parser.add_argument("--results", default=DEFAULT_RESULTS, help="Results history file (JSON lines)")
    parser.add_argument("--history", action="store_true", help="Show past results instead of running")
    args = parser.parse_args()

    if args.history:
        print_history(args.results, scenario=None if args.scenario in (None, "all") else args.scenario)
        sys.exit(0)
    if not args.scenario:
        parser.error("--scenario is required (or use --history)")
    if args.scenario == "all":
        names = list_scenarios(held_out=False)
    elif args.scenario == "held-out":
        names = list_scenarios(held_out=True)
    else:
        names = [args.scenario]
    run_benchmark(names, runs=args.runs, parallel=args.parallel, imagine_with_llm=args.imagine, seed=args.seed,
                  results_path=args.results)
