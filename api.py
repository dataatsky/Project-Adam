from flask import Flask, jsonify


def create_app(get_brain):
    app = Flask(__name__)

    @app.get("/get_state")
    def get_state():
        brain = get_brain()
        if brain:
            try:
                return jsonify({
                    "location": brain.current_world_state.get("agent_location", "unknown"),
                    "mood": brain.agent_status['emotional_state']['mood']
                })
            except Exception:
                pass
        return jsonify({"error": "Cognitive loop not running"}), 500

    return app
    
def _safe_brain_state(brain):
    try:
        state = {
            "cycle": getattr(brain, "cycle_counter", 0),
            "mood": brain.agent_status['emotional_state']['mood'],
            "hunger": brain.agent_status['needs']['hunger'],
            "kpis": brain.insight.compute_kpis() if getattr(brain, "insight", None) else {},
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
