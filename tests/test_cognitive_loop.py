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

    def imagine_batch(self, actions, seed=None, trace=False):
        return {"outcomes": ["imagined"] * len(actions)}

    def reflect(self, payload):
        self.reflect_payloads.append(payload)
        decision = self.decisions.pop(0) if self.decisions else {"verb": "wait", "target": None}
        return {"final_action": decision, "reasoning": "scripted", **self.reflection_extra}

    def theory_of_mind(self, **kwargs):
        self.tom_calls.append(kwargs)
        return {"beliefs": ["b"], "predicted_goal": "g", "trust_level": 0.5, "potential_threat": False}

    def consolidate(self, memories, seed=None, trace=False):
        return {"insight": "insight"}


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
    assert world.agents["adam1"]["mood"] == "happy"  # "joyful" normalized to the fixed vocabulary
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


class StatelessHungerPsyche(FakePsyche):
    """Decides from the payload alone, so one instance can serve parallel runs."""

    def generate_impulse(self, payload):
        here = payload["world_state"]["agent_location"]
        action = {"verb": "eat", "target": "fridge"} if here == "kitchen" else {"verb": "go", "target": "north"}
        return {"emotional_shift": {}, "impulses": [{**action, "urgency": 0.9}]}

    def imagine_batch(self, actions, seed=None, trace=False):
        raise AssertionError("LLM imagination should be skipped")

    def reflect(self, payload):
        return {"final_action": payload["hypothetical_outcomes"][0]["action"], "reasoning": "follow the plan"}


def test_loop_can_skip_llm_imagination(brain_factory):
    world = TextWorld(seed=0, scenario_config=load_scenario("hunger_test").CONFIG)
    brain = brain_factory(StatelessHungerPsyche())
    brain.imagine_with_llm = False
    brain.step(world)
    hypo = brain.last_hypothetical[0]
    assert hypo["imagined"] is None
    assert "walked north" in hypo["simulated"]  # the world simulation still runs


def test_benchmark_runs_episodes_in_parallel(tmp_path):
    from benchmark import run_benchmark

    rates = run_benchmark(
        ["hunger_test"], runs=4, parallel=2,
        psyche=StatelessHungerPsyche(), log_file=str(tmp_path / "bench.csv"),
        results_path=str(tmp_path / "results.jsonl"),
    )
    assert rates == {"hunger_test": 100.0}
    lines = (tmp_path / "bench.csv").read_text().strip().splitlines()
    assert len(lines) == 1 + 4 * 2  # header + 4 runs x 2 cycles, no interleaved rows


def test_repetitions_flag_repeated_actions(brain_factory):
    brain = brain_factory()
    for _ in range(5):
        brain.insight.add_cycle(action={"verb": "examine", "target": "radio"}, success=True, impulses=[], triggers=[], mood="calm")
    for _ in range(3):
        brain.insight.add_cycle(action={"verb": "wait", "target": None}, success=True, impulses=[], triggers=[], mood="calm")
    # Waiting is reported separately: it can be the right choice, so it is never "repetition"
    assert brain._repetitions() == ["examine radio (5 of the last 8 cycles)"]
    assert brain._waiting() == "3 of the last 8 cycles"


def test_repetitions_reach_both_prompts(brain_factory):
    world = TextWorld(seed=0, scenario_config=load_scenario("social_party").CONFIG)
    psyche = FakePsyche(decisions=[{"verb": "examine", "target": "radio"}] * 4)
    brain = brain_factory(psyche)
    for _ in range(4):
        brain.step(world)
    assert psyche.impulse_payloads[-1]["repetitions"] == ["examine radio (3 of the last 3 cycles)"]
    assert psyche.reflect_payloads[-1]["repetitions"] == ["examine radio (3 of the last 3 cycles)"]


def test_rejected_decision_is_remembered_and_counted(brain_factory):
    world = TextWorld(seed=0, scenario_config=load_scenario("hunger_test").CONFIG)
    psyche = FakePsyche(
        decisions=[{"verb": "examine", "target": "walls"}],
        impulses=[{"verb": "go", "target": "north", "urgency": 0.6}],
    )
    brain = brain_factory(psyche)
    brain.step(world)
    assert any(m.startswith("I decided to examine the walls. But it failed because it was impossible")
               for m in brain.recent_memories)
    assert brain.stats["decisions"] == 1 and brain.stats["decisions_rejected"] == 1
    # The next reflection sees it, and the failed-action counter parses it
    brain.step(world)
    assert any("examine the walls" in m for m in psyche.reflect_payloads[-1]["recent_memories"])


def test_stats_count_dropped_impulses_and_fallbacks(brain_factory):
    class FallbackPsyche(FakePsyche):
        def generate_impulse(self, payload):
            return {"emotional_shift": {}, "psyche_fallback": True,
                    "impulses": [{"verb": "wait", "urgency": 0.1}, {"verb": "take", "target": "moon", "urgency": 0.5}]}

    world = TextWorld(seed=0, scenario_config=load_scenario("hunger_test").CONFIG)
    brain = brain_factory(FallbackPsyche())
    brain.step(world)
    # impulse (fallback) + imagination + reflection: every LLM call is counted
    assert brain.stats["psyche_calls"] == 3 and brain.stats["psyche_fallbacks"] == 1
    assert brain.stats["impulses"] == 2 and brain.stats["impulses_dropped"] == 1


def test_goal_progress_kpi_counts_real_step_completions(brain_factory):
    world = TextWorld(seed=0, scenario_config=load_scenario("hunger_test").CONFIG)
    world.set_goal("Eat", steps=["go kitchen", "eat fridge"])
    psyche = FakePsyche(decisions=[{"verb": "sit", "target": "sofa"}, {"verb": "go", "target": "north"},
                                   {"verb": "eat", "target": "fridge"}])
    brain = brain_factory(psyche)
    brain.step(world)
    assert brain.insight.compute_kpis()["goal_progress"] == 0.0   # sitting is not a goal step
    brain.step(world)
    brain.step(world)
    assert brain.insight.compute_kpis()["goal_progress"] == round(2 / 3, 2)  # 2 of 3 goal-directed cycles advanced
    assert brain.agent_status["goal"] is None  # plan finished, goal completed


def test_llm_seed_is_sent_per_cycle(brain_factory):
    world = TextWorld(seed=0, scenario_config=load_scenario("hunger_test").CONFIG)
    psyche = FakePsyche()
    brain = brain_factory(psyche)
    brain.llm_seed = 3
    brain.step(world)
    brain.step(world)
    assert [p["seed"] for p in psyche.impulse_payloads] == [3001, 3002]
    assert [p["seed"] for p in psyche.reflect_payloads] == [3001, 3002]


def test_goal_without_steps_adopts_adams_plan(brain_factory):
    world = TextWorld(seed=0, scenario_config=load_scenario("locked_room").CONFIG)
    psyche = FakePsyche(reflection_extra={"new_goal_plan": ["open drawer", "take key", "unlock door", "go east"]})
    brain = brain_factory(psyche)
    brain.step(world)
    goal = world.agents["adam1"]["active_goal"]
    assert goal["name"] == "Get out of the bedroom"
    assert [s["desc"] for s in goal["steps"]] == ["open drawer", "take key", "unlock door", "go east"]


def test_goal_adopted_this_cycle_counts_its_first_step(brain_factory):
    world = TextWorld(seed=0, scenario_config=load_scenario("hunger_test").CONFIG)
    psyche = FakePsyche(decisions=[{"verb": "go", "target": "north"}],
                        reflection_extra={"new_goal": "Eat", "new_goal_plan": ["go kitchen", "eat fridge"]})
    brain = brain_factory(psyche)
    brain.step(world)
    assert brain.insight.compute_kpis()["goal_progress"] == 1.0


def test_every_llm_call_is_seeded_and_counted(brain_factory):
    class RecordingPsyche(FakePsyche):
        seeds = []

        def imagine_batch(self, actions, seed=None, trace=False):
            self.seeds.append(("imagine", seed))
            return {"outcomes": ["x"] * len(actions)}

        def theory_of_mind(self, **kwargs):
            self.seeds.append(("tom", kwargs.get("seed")))
            return {"psyche_fallback": True}  # e.g. Ollama timed out

    world = TextWorld(seed=0, scenario_config=load_scenario("social_party").CONFIG)
    psyche = RecordingPsyche()
    brain = brain_factory(psyche)
    brain.llm_seed = 2
    brain.step(world)
    assert ("imagine", 2001) in psyche.seeds and ("tom", 2001) in psyche.seeds
    # impulse + imagination + ToM + reflection; the failed ToM call is a fallback
    assert brain.stats["psyche_calls"] == 4 and brain.stats["psyche_fallbacks"] == 1
    assert not brain.tom_cache  # a fallback answer is not treated as insight


def test_jsonl_log_records_corrections_and_analysis_reads_it(tmp_path):
    import json as _json
    from analysis_utils import prepare_dataframe

    log = tmp_path / "adam.jsonl"
    world = TextWorld(seed=0, scenario_config=load_scenario("hunger_test").CONFIG)
    psyche = FakePsyche(
        decisions=[{"verb": "examine", "target": "walls"}, {"verb": "eat", "target": "fridge"}],
        impulses=[{"verb": "take", "target": "moon", "urgency": 0.9}, {"verb": "go", "target": "north", "urgency": 0.6}],
    )
    brain = CognitiveLoop(str(log), LOG_HEADERS, psyche=psyche)
    brain.step(world)
    brain.step(world)
    rows = [_json.loads(line) for line in log.read_text().splitlines()]
    assert len(rows) == 2
    first = rows[0]
    assert isinstance(first["action_result"], dict) and isinstance(first["impulses"], list)  # real objects, not strings
    assert first["dropped_impulses"][0]["target"] == "moon" and "moon" in first["dropped_impulses"][0]["reason"]
    assert first["rejected_decision"]["target"] == "walls"
    assert rows[1]["rejected_decision"] is None
    df = prepare_dataframe(str(log))
    assert df["chosen_verb"].tolist() == ["go", "eat"]
    assert df["action_success"].tolist() == [1.0, 1.0]  # went north, then ate from the kitchen fridge
    assert "frustration" in df.columns


def test_csv_log_still_supported(tmp_path):
    from analysis_utils import prepare_dataframe

    log = tmp_path / "adam.csv"
    world = TextWorld(seed=0, scenario_config=load_scenario("hunger_test").CONFIG)
    brain = CognitiveLoop(str(log), LOG_HEADERS, psyche=FakePsyche(decisions=[{"verb": "go", "target": "north"}]))
    brain.step(world)
    header = log.read_text().splitlines()[0]
    assert header == ",".join(LOG_HEADERS)  # JSONL-only fields are not added as CSV columns
    df = prepare_dataframe(str(log))
    assert df["chosen_verb"].tolist() == ["go"] and df["action_result_parsed"][0]["success"] is True


def test_trace_is_logged_with_the_cycle(tmp_path):
    import json as _json

    class TracingPsyche(FakePsyche):
        def generate_impulse(self, payload):
            assert payload["trace"] is True
            out = super().generate_impulse(payload)
            return {**out, "_trace": {"prompt": "impulse prompt", "replies": ["{...}"]}}

        def reflect(self, payload):
            return {**super().reflect(payload), "_trace": {"prompt": "reflect prompt", "replies": ["{...}"]}}

    log = tmp_path / "t.jsonl"
    world = TextWorld(seed=0, scenario_config=load_scenario("hunger_test").CONFIG)
    brain = CognitiveLoop(str(log), LOG_HEADERS, psyche=TracingPsyche(decisions=[{"verb": "go", "target": "north"}]))
    brain.trace = True
    brain.step(world)
    record = _json.loads(log.read_text().splitlines()[0])
    assert [t["endpoint"] for t in record["trace"]] == ["generate_impulse", "reflect"]
    assert record["trace"][1]["prompt"] == "reflect prompt"
    assert "_trace" not in record["emotional_delta"]


def test_no_trace_field_by_default(tmp_path):
    import json as _json

    log = tmp_path / "t.jsonl"
    world = TextWorld(seed=0, scenario_config=load_scenario("hunger_test").CONFIG)
    brain = CognitiveLoop(str(log), LOG_HEADERS, psyche=FakePsyche())
    brain.trace = False
    brain.step(world)
    assert "trace" not in _json.loads(log.read_text().splitlines()[0])
