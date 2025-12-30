
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
            {"name": "living_room", "coords": (0, 0), "desc": "A cozy party room with music."}
        ],
        "objects": {
            (0, 0): {
                "radio": {"type": "device", "state": "on", "desc": "Playing jazz."}
            }
        }
    },
    # Simple win: Say something polite (msg in Eve's inbox) OR trust metric if we had it exposed
    # For now, we'll check if Eve received a message containing "hello" or "friend"
    "win_condition": lambda w: any("hello" in msg["content"].lower() or "friend" in msg["content"].lower() for msg in w.agents["eve"].get("inbox", [])),
    "fail_condition": lambda w: False
}
