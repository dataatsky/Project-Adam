from flask import Flask, jsonify
import logging


def create_app(get_brain):
    app = Flask(__name__)

    @app.get("/get_state")
    def get_state():
        brain = get_brain()
        if not brain:
            return jsonify({"error": "Cognitive loop not running"}), 500
        try:
            recent_memories = getattr(brain, "recent_memories", []) or []
            recent_impulses = getattr(brain, "last_impulses", []) or []
            state = {
                "cycle": getattr(brain, "cycle_counter", 0),
                "location": brain.current_world_state.get("agent_location", "unknown") if getattr(brain, "current_world_state", None) else "unknown",
                "mood": brain.agent_status['emotional_state']['mood'],
                "hunger": brain.agent_status['needs']['hunger'],
                "recent_impulses": recent_impulses[:3],
                "recent_memories": recent_memories[-3:],
                "recent_diaries": [entry.get("text") for entry in getattr(brain, "diary_entries", [])[-3:]],
                "current_goal": getattr(brain, "active_goal", {}).get("name") if hasattr(brain, "active_goal") else None,
                "kpis": brain.insight.compute_kpis() if getattr(brain, "insight", None) else {},
                "relationships": brain.current_world_state.get("relationships", {}) if getattr(brain, "current_world_state", None) else {},
            }
            return jsonify(state)
        except Exception as exc:
            logging.getLogger(__name__).warning("State serialization failed: %s", exc, exc_info=True)
            return jsonify({"error": "Unable to serialize state"}), 500

    return app
    
def _safe_brain_state(brain):
    try:
        state = {
            "cycle": getattr(brain, "cycle_counter", 0),
            "mood": brain.agent_status['emotional_state']['mood'],
            "hunger": brain.agent_status['needs']['hunger'],
            "kpis": brain.insight.compute_kpis() if getattr(brain, "insight", None) else {},
            "current_goal": getattr(brain, "active_goal", {}).get("name") if hasattr(brain, "active_goal") else None,
            "relationships": brain.current_world_state.get("relationships", {}) if getattr(brain, "current_world_state", None) else {},
        }
        return state
    except Exception:
        return {"cycle": 0, "mood": None, "hunger": None, "kpis": {}}

def add_metrics_route(app, get_brain):
    @app.get("/metrics")
    def metrics():
        brain = get_brain()
        if not brain:
            return jsonify({"error": "Cognitive loop not running"}), 500
        return jsonify(_safe_brain_state(brain))
