"""Load and run benchmark scenarios.

Shared by `benchmark.py` (LLM-driven runs) and `tests/test_scenarios.py`
(scripted runs that prove each scenario is both winnable and losable).

A scenario module in `scenarios/` must define:
- CONFIG:   world layout, agents, max_cycles, win_condition, optional fail_condition
- SOLUTION: a list of actions that wins the scenario
- FAILURE:  a list of actions that does not win it
"""
import importlib.util
from pathlib import Path
from typing import Callable, Dict, List, Optional, Union

from text_world import TextWorld

SCENARIO_DIR = Path(__file__).resolve().parent / "scenarios"

Action = Dict[str, Optional[str]]


def list_scenarios() -> List[str]:
    return sorted(p.stem for p in SCENARIO_DIR.glob("*.py") if not p.stem.startswith("_"))


def load_scenario(name: str):
    """Import `scenarios/<name>.py` fresh, so no state leaks between runs."""
    path = SCENARIO_DIR / f"{name}.py"
    if not path.exists():
        raise FileNotFoundError(f"Scenario '{name}' not found at {path}")
    spec = importlib.util.spec_from_file_location(f"scenario_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def outcome(config: Dict, world: TextWorld) -> Optional[str]:
    if config.get("fail_condition") and config["fail_condition"](world):
        return "FAIL"
    if config.get("win_condition") and config["win_condition"](world):
        return "WIN"
    return None


def run_episode(config: Dict, act: Callable[[TextWorld, int], None], seed: int = 0) -> Dict:
    """Run one episode. `act(world, cycle)` performs the agent's move for that cycle."""
    world = TextWorld(seed=seed, scenario_config=config)
    cycles = 0
    result = "TIMEOUT"
    while cycles < config["max_cycles"]:
        cycles += 1
        world.update()
        result = outcome(config, world) or "TIMEOUT"
        if result != "TIMEOUT":
            break
        act(world, cycles)
        result = outcome(config, world) or "TIMEOUT"
        if result != "TIMEOUT":
            break
    return {"outcome": result, "cycles": cycles, "world": world}


def _as_action(step: Union[str, Action]) -> Action:
    if isinstance(step, dict):
        return step
    verb, _, target = step.partition(" ")
    return {"verb": verb, "target": target or None}


def scripted_policy(steps: List[Union[str, Action]], agent_id: str = "adam1", log: Optional[list] = None):
    """Play `steps` in order (strings like "go north" or action dicts), then wait."""
    queue = [_as_action(s) for s in steps]

    def act(world: TextWorld, _cycle: int):
        action = queue.pop(0) if queue else {"verb": "wait", "target": None}
        result = world.process_action(action, agent_id=agent_id)
        if log is not None:
            log.append((action, result))

    return act
