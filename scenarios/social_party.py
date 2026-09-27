
# Social Party Scenario
# Objective: Socialize with Eve.
# Difficulty: Hard (Requires Theory of Mind)

CONFIG = {
    "name": "social_party",
    "description": "Make friends with Eve.",
    "max_cycles": 25,
    "agents": {
        "adam1": {
            "pos": (0, 0),
            "hunger": 0.2,
            "inventory": []
        },
        "eve": {
            "pos": (0, 0),
            "hunger": 0.2,
            "inventory": []
        }
    },
    "map_layout": {
        "rooms": [
            {"name": "living_room", "coords": (0, 0), "desc": "A cozy party room with music.", "objects": {
                "radio": {"type": "device", "state": "on", "desc": "Playing jazz."}
            }}
        ],
    },
    # Win once Eve has heard a friendly greeting from Adam
    "win_condition": lambda w: any(
        msg["sender"] == "adam1" and ("hello" in msg["content"].lower() or "friend" in msg["content"].lower())
        for msg in w.agents["eve"].get("inbox", [])
    ),
}

SOLUTION = [{"verb": "say", "target": "Hello Eve, nice to meet you!"}]
FAILURE = ["play radio", "toggle radio"]  # ignores Eve
