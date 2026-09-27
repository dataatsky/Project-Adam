from flask import Flask, jsonify
import logging

log = logging.getLogger(__name__)


def _brain_state(brain, full: bool = True) -> dict:
    """Snapshot of the loop for the API. `full` adds recent impulses, memories and diaries."""
    status = brain.agent_status
    world_state = getattr(brain, "current_world_state", None) or {}
    state = {
        "cycle": getattr(brain, "cycle_counter", 0),
        "location": world_state.get("agent_location", "unknown"),
        "mood": status["emotional_state"]["mood"],
        "hunger": status["needs"]["hunger"],
        "current_goal": status.get("goal"),
        "kpis": brain.insight.compute_kpis() if getattr(brain, "insight", None) else {},
        "relationships": world_state.get("relationships", {}),
    }
    if full:
        state.update({
            "recent_impulses": (getattr(brain, "last_impulses", []) or [])[:3],
            "recent_memories": (getattr(brain, "recent_memories", []) or [])[-3:],
            "recent_diaries": [entry.get("text") for entry in getattr(brain, "diary_entries", [])[-3:]],
        })
    return state


def _respond(get_brain, full: bool):
    brain = get_brain()
    if not brain:
        return jsonify({"error": "Cognitive loop not running"}), 500
    try:
        return jsonify(_brain_state(brain, full=full))
    except Exception as exc:
        log.warning("State serialization failed: %s", exc, exc_info=True)
        return jsonify({"error": "Unable to serialize state"}), 500


def create_app(get_brain):
    app = Flask(__name__)

    @app.get("/get_state")
    def get_state():
        return _respond(get_brain, full=True)

    return app


def add_metrics_route(app, get_brain):
    @app.get("/metrics")
    def metrics():
        return _respond(get_brain, full=False)
