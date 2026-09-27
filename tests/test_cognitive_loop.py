from pathlib import Path

import pytest

from loop.cognitive_loop import CognitiveLoop
from constants import LOG_HEADERS
from scenario_runner import load_scenario, run_episode
from text_world import TextWorld


class DummyInsight:
    def __init__(self):
        self.causal_args = None
        self.cards_args = None

    def add_cycle(self, **kwargs):
        pass

    def compute_kpis(self):
        return {}

    def causal_line(self, **kwargs):
        self.causal_args = kwargs
        return "causal"

    def cards(self, **kwargs):
        self.cards_args = kwargs
        return []

    def badges(self, _):
        return []

    def threads(self):
        return []


class FakePsyche:
    """Scripted psyche: replays impulses/decisions and records every payload."""

    def __init__(self, decisions=None, impulses=None, shift=None, reflection_extra=None):
        self.decisions = list(decisions or [])
        self.impulses = impulses
        self.shift = shift or {}
        self.reflection_extra = reflection_extra or {}
        self.impulse_payloads = []
        self.reflect_payloads = []
        self.tom_calls = []

    def generate_impulse(self, payload):
        self.impulse_payloads.append(payload)
        decision = self.decisions[0] if self.decisions else {"verb": "wait", "target": None}
        imps = self.impulses or [{**decision, "urgency": 0.8, "drive": "need"}]
        return {"emotional_shift": self.shift, "impulses": imps}

    def imagine_batch(self, actions):
        return ["imagined"] * len(actions)

    def reflect(self, payload):
        self.reflect_payloads.append(payload)
        decision = self.decisions.pop(0) if self.decisions else {"verb": "wait", "target": None}
        return {"final_action": decision, "reasoning": "scripted", **self.reflection_extra}

    def theory_of_mind(self, **kwargs):
        self.tom_calls.append(kwargs)
        return {"beliefs": ["b"], "predicted_goal": "g", "trust_level": 0.5, "potential_threat": False}

    def consolidate(self, memories):
        return "insight"


@pytest.fixture
def brain_factory(tmp_path: Path, monkeypatch):
    def make(psyche=None):
        brain = CognitiveLoop(str(tmp_path / "loop.csv"), LOG_HEADERS, psyche=psyche)
        brain.cycle_sleep = 0
        return brain
    return make


def test_cognitive_loop_passes_imagination_details(brain_factory):
    brain = brain_factory()
    brain.insight = DummyInsight()
    brain.last_hypothetical = [
        {"action": {"verb": "open", "target": "window"}, "imagined": "window opens", "simulated": "window opens"}
    ]
    world = TextWorld(seed=1)
    brain.attach_world(world)
    impulses = {"impulses": [{"verb": "open", "target": "window", "urgency": 0.9}], "emotional_shift": {}}
    brain.act(world, {"verb": "open", "target": "window"}, "because", world.get_world_state(), impulses)

    assert brain.insight.causal_args["imagined"] == "open window: window opens"
    assert brain.insight.cards_args["imagined"] == "open window: window opens"


def test_agent_status_reads_from_world(brain_factory):
    world = TextWorld(scenario_config=load_scenario("hunger_test").CONFIG)
    psyche = FakePsyche()
    brain = brain_factory(psyche)
    brain.step(world)
    # The scenario says Adam is starving; the prompt must say so too
    sent = psyche.impulse_payloads[0]["current_state"]["needs"]["hunger"]
    assert sent == pytest.approx(0.8)
    world.agents["adam1"]["hunger"] = 0.33
    assert brain.agent_status["needs"]["hunger"] == 0.33


def test_fresh_world_is_seeded_from_config(brain_factory, monkeypatch):
    brain = brain_factory()
    brain._initial_status = {
        "emotional_state": {"mood": "anxious", "level": 0.6},
        "personality": {"curiosity": 0.1},
        "needs": {"hunger": 0.42},
        "goal": "Tidy up",
    }
    world = TextWorld(seed=3)
    brain.attach_world(world)
    status = brain.agent_status
    assert status["needs"]["hunger"] == 0.42
    assert status["emotional_state"] == {"mood": "anxious", "level": 0.6}
    assert status["goal"] == "Tidy up"


def test_emotional_shift_applied_once_per_cycle(brain_factory):
    world = TextWorld(seed=0, scenario_config=load_scenario("social_party").CONFIG)
    brain = brain_factory(FakePsyche(shift={"mood": "joyful", "level_delta": 0.1}))
    before = world.agents["adam1"]["mood_intensity"]
    brain.step(world)
    assert world.agents["adam1"]["mood"] == "joyful"
    assert world.agents["adam1"]["mood_intensity"] == pytest.approx(before + 0.1)


def test_ungrounded_decision_falls_back_to_grounded_impulse(brain_factory):
    world = TextWorld(seed=0, scenario_config=load_scenario("hunger_test").CONFIG)
    psyche = FakePsyche(
        decisions=[{"verb": "examine", "target": "walls"}],
        impulses=[
            {"verb": "inspect", "target": "walls", "urgency": 0.9},  # not in this room
            {"verb": "go", "target": "north", "urgency": 0.6},
        ],
    )
    brain = brain_factory(psyche)
    action, result = brain.step(world)
    assert action == {"verb": "go", "target": "north"}
    assert result["success"]
    # The ungrounded impulse never reached imagination
    imagined = [h["action"]["verb"] for h in brain.last_hypothetical]
    assert imagined == ["go"]


def test_goal_is_adopted_only_when_free_and_can_be_abandoned(brain_factory):
    world = TextWorld(seed=0, scenario_config=load_scenario("hunger_test").CONFIG)
    psyche = FakePsyche(reflection_extra={"new_goal": "Eat", "new_goal_plan": ["go kitchen", "eat fridge"]})
    brain = brain_factory(psyche)
    brain.step(world)
    assert brain.agent_status["goal"] == "Eat"
    psyche.reflection_extra = {"new_goal": "Something else"}
    brain.step(world)
    assert brain.agent_status["goal"] == "Eat"  # not replaced mid-way
    psyche.reflection_extra = {"goal_status": "abandoned", "new_goal": "Rest"}
    brain.step(world)
    assert brain.agent_status["goal"] == "Rest"
    assert any(h.get("status") == "abandoned" for h in world.agents["adam1"]["goal_history"])


def test_go_step_completes_by_arriving(brain_factory):
    world = TextWorld(seed=0, scenario_config=load_scenario("hunger_test").CONFIG)
    world.set_goal("Eat", steps=["go kitchen", "eat fridge"])
    world.process_action({"verb": "go", "target": "north"})
    assert world.agents["adam1"]["goal_progress_index"] == 1


def test_theory_of_mind_throttled(brain_factory):
    world = TextWorld(seed=0, scenario_config=load_scenario("social_party").CONFIG)
    psyche = FakePsyche()
    brain = brain_factory(psyche)
    brain.tom_interval = 5
    for _ in range(4):
        world.update()
        brain.step(world)
    assert len(psyche.tom_calls) == 1  # Eve is silent: modelled once, then cached
    world.process_action({"verb": "say", "target": "Hi Adam"}, agent_id="eve")
    brain.step(world)
    assert len(psyche.tom_calls) == 2
    assert "Hi Adam" in psyche.tom_calls[-1]["recent_actions"]


def test_benchmark_path_wins_with_scripted_psyche(brain_factory):
    config = load_scenario("hunger_test").CONFIG
    brain = brain_factory(FakePsyche(decisions=[{"verb": "go", "target": "north"}, {"verb": "eat", "target": "fridge"}]))
    episode = run_episode(config, lambda world, _c: brain.step(world))
    assert episode["outcome"] == "WIN"
    assert episode["cycles"] == 2
