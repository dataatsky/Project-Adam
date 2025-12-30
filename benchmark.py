
import argparse
import sys
import os
import time
import importlib.util
from statistics import mean

# Ensure project root is in path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from text_world import TextWorld
from loop.cognitive_loop import CognitiveLoop
from services.psyche_client import PsycheClient
from constants import LOG_HEADERS
import config

def load_scenario(name):
    path = os.path.join("scenarios", f"{name}.py")
    if not os.path.exists(path):
        print(f"Error: Scenario '{name}' not found at {path}")
        sys.exit(1)
        
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.CONFIG

def run_benchmark(scenario_name, runs):
    config_data = load_scenario(scenario_name)
    print(f"Starting Benchmark: {config_data['name']} ({config_data['description']})")
    print(f"Runs: {runs} | Max Cycles: {config_data['max_cycles']}\n")

    results = []
    
    # Use real psyche client or mock? Ideally real for full system test.
    # Updated to Port 5001 to avoid AirPlay conflict
    psyche = PsycheClient(
        getattr(config, 'PSYCHE_LLM_API_URL', 'http://127.0.0.1:5001/'),
        timeout=60
    )

    for i in range(runs):
        print(f"Run {i+1}/{runs}...", end=" ", flush=True)
        
        # Initialize
        seed = i # Deterministic seeding per run index
        world = TextWorld(seed=seed, scenario_config=config_data)
        
        # Headless loop
        brain = CognitiveLoop(
            log_filename="benchmark.log", # Dump to temp log
            log_headers=LOG_HEADERS,
            ui=None,
            experiment_tag=f"bench_{scenario_name}",
            agent_id="adam1",
            memory=None, # Disable long-term memory for sterile benchmark
            psyche=psyche,
            world_factory=lambda: world 
        )
        
        cycles = 0
        outcome = "TIMEOUT"
        
        try:
            # Setup similar to run_loop
            if brain.security: brain.security.update_world(world)
            
            while cycles < config_data['max_cycles']:
                cycles += 1
                
                # 1. Update World
                world.update()
                
                # 2. Check Win/Fail Conditions
                if config_data.get("win_condition") and config_data["win_condition"](world):
                    outcome = "WIN"
                    break
                if config_data.get("fail_condition") and config_data["fail_condition"](world):
                    outcome = "FAIL"
                    break
                
                # 3. Cognitive Step
                # Simplified OODA from CognitiveLoop.run_loop logic
                brain.cycle_counter = cycles
                
                # We need to make sure brain uses THIS world instance
                ws = world.get_world_state(agent_id=brain.agent_id)
                full = brain.observe(ws)
                impulses = brain.orient(full)
                
                if impulses:
                    reflection = brain.imagine_and_reflect(impulses, world)
                    # Apply mood updates from reflection/impulses
                    shift = impulses.get("emotional_shift", {})
                    if shift:
                        brain.agent_status["emotional_state"]["mood"] = shift.get("mood", "neutral")
                    
                    final_action = reflection.get('final_action', {'verb': 'wait', 'target': 'null'})
                    reasoning = reflection.get('reasoning', 'benchmark')
                    
                    action, _ = brain.decide(final_action, reasoning)
                    brain.act(world, action, reasoning, full, impulses)
                else:
                    action = {"verb": "wait", "target": "null"}
                    brain.act(world, action, "No impulses", full, {})

                # Check conditions again after act
                if config_data.get("win_condition") and config_data["win_condition"](world):
                    outcome = "WIN"
                    break
                if config_data.get("fail_condition") and config_data["fail_condition"](world):
                    outcome = "FAIL"
                    break
                    
        except Exception as e:
            outcome = f"ERROR: {e}"
            import traceback
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
        fails = [r for r in results if r["outcome"] != "WIN"]
        print(f"Failed Outcomes: {[f['outcome'] for f in fails]}")
        
    return success_rate

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", type=str, required=True, help="Name of scenario (e.g. hunger_test)")
    parser.add_argument("--runs", type=int, default=1, help="Number of runs")
    args = parser.parse_args()
    
    run_benchmark(args.scenario, args.runs)
