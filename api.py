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

