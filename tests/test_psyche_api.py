import pytest
from pydantic import ValidationError

import psyche_ollama as appmod
from text_world import VERBS


@pytest.fixture
def calls():
    return []


@pytest.fixture
def client(monkeypatch, calls):
    """Replace the Ollama call with canned, schema-valid replies."""

    def fake_structured(prompt, response_model, endpoint, seed=None):
        calls.append((endpoint, prompt))
        if response_model is appmod.GenerateImpulseResponse:
            return appmod.GenerateImpulseResponse(
                emotional_shift=appmod.EmotionalShift(mood="neutral"),
                impulses=[appmod.Impulse(verb="wait", urgency=0.1)],
            )
        if response_model is appmod.ImagineResponse:
            return appmod.ImagineResponse(outcome="tested outcome")
        if response_model is appmod.ImagineBatchResponse:
            return appmod.ImagineBatchResponse(outcomes=["outcome 1"])  # one short on purpose
        if response_model is appmod.ReflectResponse:
            return appmod.ReflectResponse(
                final_action=appmod.Action(verb="wait"),
                reasoning="test logic",
                new_goal="Survive",
            )
        if response_model is appmod.ConsolidateResponse:
            return appmod.ConsolidateResponse(insight="Mock insight")
        raise AssertionError(f"unexpected model {response_model}")

    monkeypatch.setattr(appmod, "_structured", fake_structured)
    app = appmod.app
    app.testing = True
    return app.test_client()


def test_generate_impulse(client, calls):
    payload = {
        "current_state": {"needs": {"hunger": 0.2}, "goal": "Find source"},
        "world_state": {"agent_location": "living_room", "sensory_events": [], "perceivable_objects": ["sofa"]},
        "resonant_memories": [],
    }
    r = client.post("/generate_impulse", json=payload)
    assert r.status_code == 200
    data = r.get_json()
    assert data["impulses"][0]["verb"] == "wait"
    # The prompt's toolbox is generated from the world's verb registry
    prompt = calls[0][1]
    assert all(f'"{verb}"' in prompt for verb in VERBS)


def test_imagine(client):
    r = client.post("/imagine", json={"action": {"verb": "wait", "target": None}})
    assert r.status_code == 200
    assert r.get_json()["outcome"] == "tested outcome"


def test_imagine_batch_pads_to_input_length(client):
    payload = {"actions": [{"verb": "wait"}, {"verb": "go", "target": "north"}]}
    r = client.post("/imagine_batch", json=payload)
    assert r.status_code == 200
    data = r.get_json()
    assert data["outcomes"] == ["outcome 1", "(Imagination uncertain)"]


def test_reflect(client, calls):
    r = client.post("/reflect", json={
        "current_state": {"emotional_state": {"mood": "neutral"}},
        "world_state": {"agent_location": "kitchen", "perceivable_objects": ["fridge"],
                        "exit_details": {"south": {"room": "living_room", "visited": True, "door": None}}},
        "hypothetical_outcomes": [],
        "recent_memories": ["I was in the kitchen. I decided to open the fridge. But it failed because it is stuck"],
    })
    assert r.status_code == 200
    data = r.get_json()
    assert data["reasoning"] == "test logic"
    assert data["new_goal"] == "Survive"
    assert data["goal_status"] == "continue"
    prompt = calls[0][1]
    assert "fridge" in prompt and "south" in prompt  # reflection sees what is reachable
    assert "'open fridge' has failed 1 times" in prompt


def test_consolidate(client):
    r = client.post("/consolidate", json={"recent_memories": ["mem1", "mem2"]})
    assert r.status_code == 200
    assert r.get_json()["insight"] == "Mock insight"


def test_invalid_payload_is_400(client):
    r = client.post("/imagine", json={"action": {"target": "x"}})
    assert r.status_code == 400


def test_model_error_returns_marked_fallback(monkeypatch, client):
    def boom(*_a, **_k):
        raise RuntimeError("ollama down")

    monkeypatch.setattr(appmod, "_structured", boom)
    r = client.post("/reflect", json={"current_state": {}, "hypothetical_outcomes": []})
    assert r.status_code == 200
    data = r.get_json()
    assert data["psyche_fallback"] is True
    assert data["final_action"]["verb"] == "wait"


def test_verb_schema_is_an_enum_of_world_verbs():
    schema = appmod.Action.model_json_schema()
    assert set(schema["properties"]["verb"]["enum"]) == set(VERBS)


def test_verb_aliases_normalize_and_unknown_verbs_fail():
    assert appmod.Action(verb="investigate", target="tv").verb == "examine"
    assert appmod.Action(verb="Turn On", target="tv").verb == "toggle"
    with pytest.raises(ValidationError):
        appmod.Action(verb="teleport", target="moon")


def test_structured_reasks_after_invalid_json(monkeypatch):
    replies = iter(['{"outcome": 5}', '{"nope": true}', '{"outcome": "fine"}'])
    seen = []

    class FakeMsg:
        def __init__(self, content):
            self.message = type("M", (), {"content": content})()

    def fake_chat(model, messages, format, think, options):
        assert think is False and options["num_predict"] > 0
        seen.append(list(messages))
        assert format["properties"]["outcome"]["type"] == "string"
        return FakeMsg(next(replies))

    monkeypatch.setattr(appmod.client, "chat", fake_chat)
    monkeypatch.setattr(appmod.config, "OLLAMA_RETRIES", 2)
    monkeypatch.setattr(appmod.config, "OLLAMA_THINK", False)
    out = appmod._structured("predict", appmod.ImagineResponse, "imagine")
    assert out.outcome == "fine"
    assert len(seen) == 3 and "did not match the schema" in seen[-1][-1]["content"]


def test_prompts_share_situation_and_guidance(client, calls):
    world_state = {
        "agent_location": "bedroom",
        "perceivable_objects": ["bed", "drawer", "door"],
        "closed_containers": ["drawer"],
        "exit_details": {"east": {"room": "office", "visited": False, "door": "locked"}},
        "people_here": ["eve"],
        "heard": ["eve said: 'hello'"],
        "sensory_events": [],
    }
    current_state = {"needs": {"hunger": 0.8}, "goal": "Get out"}
    client.post("/generate_impulse", json={"current_state": current_state, "world_state": world_state,
                                            "repetitions": ["wait (5 of the last 8 cycles)"]})
    client.post("/reflect", json={"current_state": current_state, "world_state": world_state,
                                  "hypothetical_outcomes": [], "repetitions": ["wait (5 of the last 8 cycles)"]})
    for _, prompt in calls:
        assert "east -> office (not explored yet) [door: locked]" in prompt
        assert "Closed things that may hide items (open them to look inside): drawer" in prompt
        assert "People here: eve (to talk: \"say\" with the exact words" in prompt and "eve said: 'hello'" in prompt
        assert "I urgently need food" in prompt
        assert "I keep repeating wait (5 of the last 8 cycles)" in prompt
        assert "\n\n\n" not in prompt  # whitespace trimming keeps prompts compact


def test_impulse_and_reflect_prompts_share_a_cacheable_prefix(client, calls):
    import os

    world_state = {
        "agent_location": "kitchen", "perceivable_objects": ["fridge", "stove"],
        "exit_details": {"south": {"room": "living_room", "visited": True, "door": None}},
        "sensory_events": [{"type": "ambience", "details": "I am in the kitchen."}],
    }
    before = {"needs": {"hunger": 0.7}, "emotional_state": {"mood": "calm", "level": 0.2}, "goal": "Eat"}
    after = {**before, "emotional_state": {"mood": "hungry", "level": 0.4}}  # shift applied between calls
    client.post("/generate_impulse", json={"current_state": before, "world_state": world_state})
    client.post("/reflect", json={"current_state": after, "world_state": world_state, "hypothetical_outcomes": []})
    shared = os.path.commonprefix([calls[0][1], calls[1][1]])
    assert "THE CONSTITUTION" in shared and '"unlock"' in shared
    assert "## What I sense" in shared and "I am in the kitchen." in shared
    assert shared.endswith("- My mood: ")  # the prompts only diverge at the (shifted) mood line
