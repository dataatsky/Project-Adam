import logging
import os

from flask import Flask, jsonify, send_from_directory

log = logging.getLogger(__name__)
VIEWER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "viewer")


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

    @app.get("/world")
    def world():
        """Everything the 3D viewer draws: the world snapshot plus Adam's latest thinking."""
        brain = get_brain()
        snapshot = getattr(brain, "snapshot", None) if brain else None
        if not snapshot:
            return jsonify({"error": "Adam is waking up; no world snapshot yet"}), 503
        return jsonify({**snapshot, "phase": getattr(brain, "phase", ""), "cycle": getattr(brain, "cycle_counter", 0)})

    @app.get("/viewer")
    def viewer():
        return send_from_directory(VIEWER_DIR, "index.html")

    return app


def add_metrics_route(app, get_brain):
    @app.get("/metrics")
    def metrics():
        return _respond(get_brain, full=False)
