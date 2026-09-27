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

    def fake_structured(prompt, response_model, endpoint):
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
        "world_state": {"agent_location": "kitchen", "perceivable_objects": ["fridge"], "available_exits": ["south"]},
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

    def fake_chat(model, messages, format):
        seen.append(list(messages))
        assert format["properties"]["outcome"]["type"] == "string"
        return FakeMsg(next(replies))

    monkeypatch.setattr(appmod.client, "chat", fake_chat)
    monkeypatch.setattr(appmod.config, "OLLAMA_RETRIES", 2)
    out = appmod._structured("predict", appmod.ImagineResponse, "imagine")
    assert out.outcome == "fine"
    assert len(seen) == 3 and "did not match the schema" in seen[-1][-1]["content"]
