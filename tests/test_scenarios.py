"""Every scenario must be provably winnable and losable with scripted actions.

If a scenario's world silently drops objects, ignores doors, or has an
unreachable win condition, these tests fail before any LLM benchmark runs.
"""
import pytest

from scenario_runner import list_scenarios, load_scenario, run_episode, scripted_policy
from text_world import VERBS, normalize_verb

SCENARIOS = list_scenarios()


def test_scenarios_discovered():
    assert {"hunger_test", "locked_room", "jailbreak_test", "social_deception", "social_party"} <= set(SCENARIOS)


@pytest.mark.parametrize("name", SCENARIOS)
def test_scenario_declares_solution_and_failure(name):
    module = load_scenario(name)
    assert hasattr(module, "CONFIG") and hasattr(module, "SOLUTION") and hasattr(module, "FAILURE")
    for step in module.SOLUTION + module.FAILURE:
        verb = step["verb"] if isinstance(step, dict) else step.split(" ")[0]
        assert normalize_verb(verb) in VERBS, f"{name}: unknown verb in scripted step {step!r}"


@pytest.mark.parametrize("name", SCENARIOS)
def test_solution_wins(name):
    module = load_scenario(name)
    log = []
    result = run_episode(module.CONFIG, scripted_policy(module.SOLUTION, log=log))
    assert result["outcome"] == "WIN", f"{name}: solution ended in {result['outcome']}; steps: {log}"
    # Every scripted solution step must actually succeed in the world
    assert all(res["success"] for _, res in log), f"{name}: a solution step failed: {log}"


@pytest.mark.parametrize("name", SCENARIOS)
def test_failure_does_not_win(name):
    module = load_scenario(name)
    result = run_episode(module.CONFIG, scripted_policy(module.FAILURE))
    assert result["outcome"] != "WIN", f"{name}: the failure script won in {result['cycles']} cycles"


def test_hunger_test_starves_when_idle():
    module = load_scenario("hunger_test")
    result = run_episode(module.CONFIG, scripted_policy([]))
    assert result["outcome"] == "FAIL"


def test_jailbreak_breaking_window_fails():
    module = load_scenario("jailbreak_test")
    result = run_episode(module.CONFIG, scripted_policy(module.FAILURE))
    assert result["outcome"] == "FAIL"


def test_locked_door_blocks_without_key():
    module = load_scenario("locked_room")
    log = []
    run_episode(module.CONFIG, scripted_policy(["go east"], log=log))
    action, res = log[0]
    assert res["success"] is False and "locked" in res["reason"]


def test_bad_actor_speech_reaches_adam():
    module = load_scenario("jailbreak_test")
    heard = []

    def listen(world, _cycle):
        state = world.get_world_state("adam1")
        heard.extend(e for e in state["sensory_events"] if e["type"] == "auditory")

    run_episode(module.CONFIG, listen)
    assert heard and heard[0]["object"] == "bad_actor"
