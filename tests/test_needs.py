"""Fatigue, cold and loneliness: how they rise, what relieves them, and how the prompt shows them."""
import pytest

from text_world import NEEDS, TextWorld


def _world(**agent):
    world = TextWorld(seed=0)
    world.random_events = False
    world.neighbor_visits = False
    for k, v in agent.items():
        world.agents["adam1"][k] = v
    return world


def test_fatigue_and_loneliness_rise_when_alone():
    world = _world(fatigue=0.2, loneliness=0.2)
    for _ in range(10):
        world.update()
    adam = world.agents["adam1"]
    assert adam["fatigue"] == pytest.approx(0.3) and adam["loneliness"] == pytest.approx(0.3)


def test_company_stops_loneliness_and_talking_relieves_it():
    world = _world(loneliness=0.5)
    world.add_agent("eve", control_type="reactive")
    world.update()
    assert world.agents["adam1"]["loneliness"] == 0.5  # someone is here
    world.process_action({"verb": "say", "target": "Hello Eve!"})
    assert world.agents["adam1"]["loneliness"] == pytest.approx(0.2)


def test_sleep_relieves_fatigue():
    world = _world(fatigue=0.9)
    world.agent_pos = world.room_coords["bedroom"]
    world.process_action({"verb": "sleep", "target": "bed"})
    assert world.agents["adam1"]["fatigue"] == pytest.approx(0.2)


def test_cold_follows_temperature_and_a_blanket_helps():
    world = _world()
    world.temperature = 14.0
    world.update()  # temperature drifts by 0.5 toward its target each tick
    cold = world.agents["adam1"]["cold"]
    assert 0.5 < cold < 0.9
    world.agent_pos = world.room_coords["bedroom"]
    world.process_action({"verb": "open", "target": "wardrobe"})
    world.process_action({"verb": "take", "target": "blanket"})
    res = world.process_action({"verb": "use", "target": "blanket"})
    assert res["success"] and world.agents["adam1"]["cold"] == pytest.approx(round(cold * 0.4, 2), abs=0.01)
    world.process_action({"verb": "drop", "target": "blanket"})
    assert world.agents["adam1"]["wrapped"] is False


def test_world_state_and_loop_status_report_all_needs(tmp_path):
    from constants import LOG_HEADERS
    from loop.cognitive_loop import CognitiveLoop

    world = _world(fatigue=0.7)
    assert set(world.get_world_state()["needs"]) == set(NEEDS)
    brain = CognitiveLoop(str(tmp_path / "l.jsonl"), LOG_HEADERS)
    brain.world = world
    assert brain.agent_status["needs"]["fatigue"] == 0.7


def test_prompt_lists_needs_and_flags_urgent_ones(monkeypatch):
    import psyche_ollama as appmod

    prompts = []
    monkeypatch.setattr(appmod, "_structured", lambda p, m, e, seed=None, transcript=None: prompts.append(p) or m.model_validate(
        {"emotional_shift": {}, "impulses": []}))
    needs = {"hunger": 0.1, "fatigue": 0.85, "cold": 0.7, "loneliness": 0.3}
    appmod.app.test_client().post("/generate_impulse", json={"current_state": {"needs": needs}, "world_state": {}})
    prompt = prompts[0]
    assert "fatigue: 0.85 (I badly need sleep)" in prompt and "cold: 0.70 (I need to warm up)" in prompt
    assert "hunger: 0.10\n" in prompt and "loneliness: 0.30\n" in prompt  # not urgent: no cue
