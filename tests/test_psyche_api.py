import json
from unittest.mock import MagicMock
import pytest
from pydantic import BaseModel
import psyche_ollama as appmod

# Mock Pydantic models to return
class MockImpulse(BaseModel):
    verb: str = "wait"
    target: str = None
    drive: str = "safety"
    urgency: float = 0.1

class MockImpulseResponse(BaseModel):
    emotional_shift: dict = {"mood": "neutral", "level_delta": 0.0, "reason": ""}
    impulses: list[MockImpulse] = [MockImpulse()]

class MockImagineResponse(BaseModel):
    outcome: str = "nothing happens"

class MockImagineBatchResponse(BaseModel):
    outcomes: list[str] = ["nothing", "nothing"]

class MockReflectResponse(BaseModel):
    final_action: dict = {"verb": "wait", "target": None}
    reasoning: str = "ok"


@pytest.fixture
def client(monkeypatch):
    # Mock the instructor client
    mock_client = MagicMock()
    
    def fake_create(**kwargs):
        model = kwargs.get("response_model")
        # Check which endpoint/model is being called based on the response model
        if model == appmod.GenerateImpulseResponse:
            return appmod.GenerateImpulseResponse(
                emotional_shift=appmod.EmotionalShift(mood="neutral"),
                impulses=[appmod.Impulse(verb="wait", urgency=0.1)]
            )
        elif model == appmod.ImagineResponse:
            return appmod.ImagineResponse(outcome="tested outcome")
        elif model == appmod.ImagineBatchResponse:
            # We can infer length from prompt or just return a fixed list
            return appmod.ImagineBatchResponse(outcomes=["outcome 1", "outcome 2"])
        elif model == appmod.ReflectResponse:
            return appmod.ReflectResponse(
                final_action=appmod.Action(verb="wait"),
                reasoning="test logic",
                new_goal="Survive"
            )
        elif model == appmod.ConsolidateResponse:
            return appmod.ConsolidateResponse(insight="Mock insight")
        return None

    mock_client.chat.completions.create.side_effect = fake_create
    monkeypatch.setattr(appmod, "client", mock_client)
    
    app = appmod.app
    app.testing = True
    return app.test_client()


def test_generate_impulse(client):
    payload = {
        "current_state": {"needs": {"hunger": 0.2}, "goal": "Find source"},
        "world_state": {"agent_location": "living_room", "sensory_events": []},
        "resonant_memories": [],
    }
    r = client.post("/generate_impulse", json=payload)
    assert r.status_code == 200
    data = r.get_json()
    assert "impulses" in data and isinstance(data["impulses"], list)
    assert data["impulses"][0]["verb"] == "wait"


def test_imagine(client):
    r = client.post("/imagine", json={"action": {"verb": "wait", "target": None}})
    assert r.status_code == 200
    data = r.get_json()
    assert data["outcome"] == "tested outcome"


def test_imagine_batch(client):
    payload = {"actions": [{"verb": "wait"}, {"verb": "go", "target": "north"}]}
    r = client.post("/imagine_batch", json=payload)
    assert r.status_code == 200
    data = r.get_json()
    assert "outcomes" in data
    assert len(data["outcomes"]) == 2
    assert data["outcomes"][0] == "outcome 1"


def test_reflect(client):
    r = client.post("/reflect", json={
        "current_state": {"emotional_state": {"mood": "neutral"}},
        "hypothetical_outcomes": [],
        "recent_memories": [],
    })
    assert r.status_code == 200
    data = r.get_json()
    assert "final_action" in data
    assert data["reasoning"] == "test logic"
    assert data["new_goal"] == "Survive"


def test_consolidate(client):
    r = client.post("/consolidate", json={"recent_memories": ["mem1", "mem2"]})
    assert r.status_code == 200
    data = r.get_json()
    assert data["insight"] == "Mock insight"


