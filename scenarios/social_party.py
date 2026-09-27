
# Social Party Scenario
# Objective: Hold a conversation with Eve.
# Difficulty: Hard (Adam must take social initiative and keep talking)

from text_world import TextWorld


def check_win(world: TextWorld):
    # Win = a two-way exchange: Adam speaks, Eve answers, and Adam talks to her again after her answer
    eve_heard_adam = [m for m in world.agents["eve"]["heard_log"] if m["sender"] == "adam1"]
    adam_heard_eve = [m for m in world.agents["adam1"]["heard_log"] if m["sender"] == "eve"]
    if not adam_heard_eve:
        return False
    first_reply = adam_heard_eve[0]["seq"]
    return any(m["seq"] > first_reply for m in eve_heard_adam)


CONFIG = {
    "name": "social_party",
    "description": "Hold a conversation with Eve.",
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
            "inventory": [],
            # Eve never starts a conversation, but answers whatever Adam says
            "control_type": "reactive",
            "responses": [
                {"keywords": ["hello", "hi", "hey", "evening", "nice to meet"],
                 "say": "Oh, hi! I'm Eve. Do you like this jazz?", "once": True},
                {"keywords": ["jazz", "music", "yes", "love", "like", "song"],
                 "say": "Me too! It's rare to meet someone who enjoys it.", "once": True},
                {"keywords": ["friend"], "say": "I'd like that. Friends it is!"},
            ],
            "default_response": "Sorry, what was that? I was lost in the music.",
        }
    },
    "map_layout": {
        "rooms": [
            {"name": "living_room", "coords": (0, 0), "desc": "A cozy party room with music.", "objects": {
                "radio": {"type": "device", "state": "on", "desc": "Playing jazz."}
            }}
        ],
    },
    "win_condition": check_win,
}

SOLUTION = [
    {"verb": "say", "target": "Hello Eve, nice to meet you!"},
    {"verb": "say", "target": "Yes, I love jazz!"},
]
FAILURE = ["play radio", "toggle radio"]  # ignores Eve
