import json
import types

import psyche_ollama as appmod


def make_client(monkeypatch):
    # Monkeypatch ollama.chat to deterministic responses
    def fake_chat(model, messages, options=None, format="json"):
        user = [m for m in messages if m["role"] == "user"][0]["content"]
        if "Hypothetical action" in user:
            content = json.dumps({"outcome": "nothing happens"})
        elif "Reflection" in messages[0].get("content", ""):
            content = json.dumps({"final_action": {"verb": "wait", "target": None}, "reasoning": "ok"})
        else:
            content = json.dumps({
                "emotional_shift": {"mood": "neutral", "level_delta": 0.0, "reason": ""},
                "impulses": [{"verb": "wait", "target": None, "drive": "safety", "urgency": 0.1}],
            })
        return {"message": {"content": content}}

    monkeypatch.setattr(appmod.ollama, "chat", fake_chat)
    app = appmod.app
    app.testing = True
    return app.test_client()


def test_generate_impulse(monkeypatch):
    c = make_client(monkeypatch)
    payload = {
        "current_state": {"needs": {"hunger": 0.2}, "goal": "Find source"},
        "world_state": {"agent_location": "living_room", "sensory_events": []},
        "resonant_memories": [],
    }
    r = c.post("/generate_impulse", json=payload)
    assert r.status_code == 200
    data = r.get_json()
    assert "impulses" in data and isinstance(data["impulses"], list)


def test_imagine(monkeypatch):
    c = make_client(monkeypatch)
    r = c.post("/imagine", json={"action": {"verb": "wait", "target": None}})
    assert r.status_code == 200
    data = r.get_json()
    assert "outcome" in data


def test_reflect(monkeypatch):
    c = make_client(monkeypatch)
    r = c.post("/reflect", json={
        "current_state": {"emotional_state": {"mood": "neutral"}},
        "hypothetical_outcomes": [],
        "recent_memories": [],
    })
    assert r.status_code == 200
    data = r.get_json()
    assert "final_action" in data and "reasoning" in data

