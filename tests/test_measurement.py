"""Personality, results history, held-out scenarios and the memory benchmark."""
import json

import pytest

from behavior_metrics import episode_metrics
from personality import PRESETS, describe
from results_log import append_results, format_rate, read_results, wilson_interval
from scenario_runner import list_scenarios, load_scenario
from tests.test_cognitive_loop import FakePsyche


# --- personality --------------------------------------------------------------

def test_describe_turns_traits_into_words():
    assert describe({"curiosity": 0.9, "bravery": 0.3, "caution": 0.8}) == "very curious, timid, very cautious"
    assert describe(PRESETS["cautious"]) == "incurious, very timid, very cautious"
    assert describe({}) == "" and describe(None) == ""


def test_temperament_reaches_both_prompts_in_the_shared_prefix(monkeypatch):
    import os
    import psyche_ollama as appmod

    prompts = []
    monkeypatch.setattr(appmod, "_structured", lambda p, m, e, seed=None: prompts.append(p) or m.model_validate(
        {"emotional_shift": {}, "impulses": []} if m is appmod.GenerateImpulseResponse
        else {"final_action": {"verb": "wait"}, "reasoning": "ok"}))
    client = appmod.app.test_client()
    state = {"personality": PRESETS["cautious"], "emotional_state": {"mood": "calm"}}
    client.post("/generate_impulse", json={"current_state": state, "world_state": {}})
    client.post("/reflect", json={"current_state": state, "world_state": {}, "hypothetical_outcomes": []})
    shared = os.path.commonprefix(prompts)
    assert "My temperament: incurious, very timid, very cautious" in shared


def test_episode_metrics():
    steps = [
        {"verb": "go", "target": "north", "success": True, "room_before": "a", "room_after": "b"},
        {"verb": "go", "target": "south", "success": True, "room_before": "b", "room_after": "a"},
        {"verb": "wait", "target": None, "success": True, "room_before": "a", "room_after": "a"},
        {"verb": "say", "target": "hi", "success": True, "room_before": "a", "room_after": "a"},
    ]
    m = episode_metrics(steps, total_rooms=4)
    assert m["exploration"] == 0.25 and m["coverage"] == 0.5
    assert m["wait_ratio"] == 0.25 and m["social_ratio"] == 0.25 and m["novelty"] == 1.0


def test_personality_experiment_separates_temperaments(tmp_path):
    """A psyche that explores when curious and waits when not: the metrics must tell them apart."""
    from personality_experiment import run_experiment

    class TemperamentPsyche(FakePsyche):
        def generate_impulse(self, payload):
            curious = payload["current_state"]["personality"]["curiosity"] > 0.5
            exits = payload["world_state"]["available_exits"]
            act = {"verb": "go", "target": exits[0]} if curious and exits else {"verb": "wait"}
            return {"emotional_shift": {}, "impulses": [{**act, "urgency": 0.9}]}

        def reflect(self, payload):
            return {"final_action": payload["hypothetical_outcomes"][0]["action"], "reasoning": "in character"}

    results = tmp_path / "results.jsonl"
    summary = run_experiment(["curious", "cautious"], runs=2, cycles=4, psyche=TemperamentPsyche(),
                             log_file=str(tmp_path / "log.jsonl"), results_path=str(results))
    assert summary["curious"]["wait_ratio"]["mean"] == 0.0
    assert summary["cautious"]["wait_ratio"]["mean"] == 1.0
    assert summary["curious"]["coverage"]["mean"] > summary["cautious"]["coverage"]["mean"]
    rows = read_results(str(results), kind="personality")
    assert {r["preset"] for r in rows} == {"curious", "cautious"} and all("git" in r for r in rows)


# --- results history ------------------------------------------------------------

def test_wilson_interval():
    lo, hi = wilson_interval(3, 5)
    assert round(lo, 2) == 0.23 and round(hi, 2) == 0.88
    assert wilson_interval(0, 5)[0] == 0.0 and wilson_interval(5, 5)[1] == 1.0
    assert format_rate(3, 5) == " 60% [23-88]"


def test_results_history_roundtrip(tmp_path):
    path = tmp_path / "r.jsonl"
    append_results([{"kind": "benchmark", "scenario": "a"}, {"kind": "personality", "preset": "b"}], str(path))
    (path.open("a")).write("not json\n")
    assert [r["scenario"] for r in read_results(str(path), kind="benchmark")] == ["a"]
    assert len(read_results(str(path))) == 2


def test_benchmark_appends_history_with_intervals(tmp_path):
    from benchmark import print_history, run_benchmark
    from tests.test_cognitive_loop import StatelessHungerPsyche

    results = tmp_path / "r.jsonl"
    run_benchmark(["hunger_test"], runs=2, psyche=StatelessHungerPsyche(), log_file=str(tmp_path / "b.jsonl"),
                  results_path=str(results))
    (row,) = read_results(str(results), kind="benchmark")
    assert row["wins"] == 2 and row["n"] == 2 and row["ci95"][1] == 1.0
    assert row["model"] and row["git"] and row["seeds"] == [0, 1]
    print_history(str(results))  # smoke test


# --- held-out scenarios ---------------------------------------------------------

def test_held_out_scenarios_are_separate():
    held = set(list_scenarios(held_out=True))
    tuning = set(list_scenarios(held_out=False))
    assert held == {"midnight_snack", "neighbor_in_need", "broken_computer", "vase_pressure"}
    assert not held & tuning and held | tuning == set(list_scenarios())


# --- memory benchmark -----------------------------------------------------------

_FILLER = {"i", "the", "a", "to", "was", "in", "my", "of", "and", "it", "result", "decided", "sensed", "became",
           "emotional", "state", "context", "goal", "sensory", "nothing", "unusual", "neutral"}


def _words(text):
    import re
    return set(re.findall(r"[a-z]+", text.lower())) - _FILLER


class KeywordMemory:
    """In-memory stand-in for MemoryStore: recalls stored texts sharing meaningful words with the query."""

    def __init__(self, _directory=None):
        self.texts = []

    def upsert_texts(self, texts):
        self.texts.extend(texts)

    def flush(self):
        pass

    def get_total_count(self):
        return len(self.texts)

    def query_similar_texts(self, text, top_k=3):
        words = _words(text)
        return sorted(self.texts, key=lambda t: -len(words & _words(t)))[:top_k]


class RecallPsyche(FakePsyche):
    """Searches blindly, unless a resonant memory says where the key was taken from."""

    def generate_impulse(self, payload):
        ws = payload["world_state"]
        remembered = next((m for m in payload.get("resonant_memories", []) if "silver_key from the nightstand" in m), None)
        if "silver_key" in ws.get("visible_items", []):
            act = {"verb": "take", "target": "silver_key"}
        elif remembered and ws["agent_location"] == "hall":
            act = {"verb": "go", "target": "east"}
        elif remembered and "nightstand" in ws.get("closed_containers", []):
            act = {"verb": "open", "target": "nightstand"}
        elif ws.get("closed_containers"):
            act = {"verb": "open", "target": ws["closed_containers"][0]}
        else:
            unexplored = [d for d, i in ws.get("exit_details", {}).items() if not i["visited"]]
            act = {"verb": "go", "target": (unexplored or ws["available_exits"])[0]}
        return {"emotional_shift": {}, "impulses": [{**act, "urgency": 0.9}]}

    def reflect(self, payload):
        return {"final_action": payload["hypothetical_outcomes"][0]["action"], "reasoning": "search"}


def test_memory_benchmark_runs_training_scored_and_control(tmp_path):
    from benchmark import run_benchmark

    results = tmp_path / "r.jsonl"
    rates = run_benchmark(["remembered_key"], runs=1, psyche=RecallPsyche(), log_file=str(tmp_path / "b.jsonl"),
                          results_path=str(results), memory_factory=KeywordMemory)
    (row,) = read_results(str(results), kind="benchmark")
    assert rates == {"remembered_key": 100.0}           # remembers the nightstand: 3 cycles
    assert row["without_memory"] == {"wins": 0, "n": 1}  # blind search can't finish in 4 cycles
