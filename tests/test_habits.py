"""Long-run habit metrics and the habits experiment."""
from behavior_metrics import action_entropy, habit_windows, js_divergence, top_actions, top_routines


def _steps(actions):
    out = []
    for a in actions:
        verb, _, target = a.partition(" ")
        out.append({"verb": verb, "target": target or None, "success": True})
    return out


def test_entropy_and_divergence():
    assert action_entropy(_steps(["wait"] * 5)) == 0.0
    assert action_entropy(_steps(["a x", "b y", "c z", "d w"])) == 1.0
    assert js_divergence({"a": 1.0}, {"a": 1.0}) == 0.0
    assert js_divergence({"a": 1.0}, {"b": 1.0}) == 1.0


def test_windows_show_behaviour_settling_into_a_habit():
    exploring = ["go north", "open fridge", "examine sofa", "go east", "read bookshelf", "sit sofa"] * 2
    settled = ["go north", "eat fridge"] * 6
    rows = habit_windows(_steps(exploring + settled + settled), window=12)
    assert rows[0]["entropy"] > rows[1]["entropy"]      # less varied once settled
    assert rows[2]["drift"] == 0.0                       # same routine two windows running
    assert rows[2]["new_actions"] == 0


def test_routines_and_top_actions():
    steps = _steps(["go north", "eat fridge", "go south", "sit sofa"] * 3)
    assert top_routines(steps, n=1)[0] == (("go north", "eat fridge"), 3)
    assert top_actions(steps, n=1)[0] == ("go north", 0.25)


def test_habits_experiment_smoke(tmp_path):
    from habits_experiment import run_experiment
    from results_log import read_results
    from tests.test_cognitive_loop import StatelessHungerPsyche
    from tests.test_measurement import KeywordMemory

    class Wanderer(StatelessHungerPsyche):
        def generate_impulse(self, payload):
            exits = payload["world_state"]["available_exits"]
            return {"emotional_shift": {}, "impulses": [{"verb": "go", "target": exits[0], "urgency": 0.9}]}

    results = tmp_path / "r.jsonl"
    records = run_experiment(cycles=12, window=4, psyche=Wanderer(), memory_factory=KeywordMemory,
                             log_file=str(tmp_path / "h.jsonl"), results_path=str(results))
    assert len(records[0]["windows"]) == 3
    (row,) = read_results(str(results), kind="habits")
    assert row["cycles"] == 12 and row["memory"] is True
