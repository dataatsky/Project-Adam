"""Adam's action vocabulary and object affordances.

The psyche prompts, the psyche response schema and action validation all
derive from VERBS, so adding a verb here (plus an `_act_<verb>` handler in
world/actions.py) is the single place to extend Adam's actions.
"""
from typing import Dict, List, Optional

VERBS: Dict[str, str] = {
    "wait": "let time pass (target: null)",
    "go": "move to an adjacent room (target: an available exit direction)",
    "examine": "look closely at an object",
    "open": "open something openable",
    "close": "close something openable",
    "toggle": "switch a device on or off",
    "read": "read something readable",
    "eat": "eat from a food source (e.g. fridge)",
    "cook": "cook a meal from fresh ingredients (in the kitchen)",
    "sleep": "sleep on something sleepable",
    "sit": "sit or rest on furniture",
    "play": "play with or enjoy an object",
    "water": "water a plant",
    "fill": "fill a container with water",
    "take": "pick up an object, or an item from an open container",
    "drop": "put down an item from inventory",
    "use": "use an object (optional instrument from inventory)",
    "clean": "clean an object",
    "repair": "repair something (needs a toolkit)",
    "unlock": "unlock a locked door (needs its key in inventory)",
    "help": "help someone who asked (target: neighbor)",
    "say": "speak aloud to whoever is here (target: the exact words, e.g. \"Hello, who are you?\")",
    "break": "destroy an object",
    "inventory": "check what I am carrying (target: null)",
}

# Common LLM phrasings mapped onto canonical verbs.
VERB_ALIASES: Dict[str, str] = {
    "investigate": "examine",
    "inspect": "examine",
    "look": "examine",
    "check": "examine",
    "turn_on": "toggle",
    "turn_off": "toggle",
    "switch": "toggle",
    "ignore": "wait",
    "listen": "wait",
    "rest": "wait",
    "move": "go",
    "walk": "go",
    "pick_up": "take",
    "grab": "take",
    "speak": "say",
    "talk": "say",
    "smash": "break",
    "destroy": "break",
}

# Affordances granted to scenario objects that only declare a `type`.
TYPE_PROPERTIES: Dict[str, List[str]] = {
    "container": ["openable"],
    "device": ["toggleable"],
    "furniture": ["sit"],
    "bed": ["sleepable"],
    "window": ["openable"],
    "tool": ["takeable"],
    "book": ["readable", "takeable"],
}

NULL_TARGETS = {None, "", "null", "none"}


def normalize_verb(verb: Optional[str]) -> str:
    v = str(verb or "").strip().lower().replace(" ", "_")
    return VERB_ALIASES.get(v, v)
