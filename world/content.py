"""What the default apartment is made of, and the rates at which needs change."""
from typing import Dict

# Core room templates that always exist; objects include properties to gate actions
BASE_ROOMS: Dict[str, Dict] = {
    "living_room": {
        "sofa": {"state": "tidy", "properties": ["sit", "rest"]},
        "window": {"state": "closed", "properties": ["openable"]},
        "tv": {"state": "off", "properties": ["toggleable", "watchable"]},
        "radio": {"state": "off", "properties": ["toggleable"]},
        "bookshelf": {"state": "arranged", "properties": ["readable", "takeable"], "items": ["mystery_novel"]},
    },
    "kitchen": {
        "fridge": {
            "state": "closed",
            "contains": {"food": 2, "fresh_ingredients": 1},
            "properties": ["openable", "eatable"]
        },
        "stove": {"state": "off", "properties": ["cookable", "toggleable"]},
        "kettle": {"state": "idle", "properties": ["useable", "fill", "heat"]},
        "sink": {"state": "clean", "properties": ["water_source", "cleanable"]},
    },
    "bedroom": {
        "bed": {"state": "made", "properties": ["sleepable"]},
        "desk": {"state": "tidy", "properties": ["workable"], "items": ["journal", "pen"]},
        "wardrobe": {"state": "closed", "properties": ["openable"], "items": ["blanket"]},
    },
    "office": {
        "computer": {"state": "off", "properties": ["toggleable", "investigatable", "repairable"]},
        "plant": {"state": "healthy", "properties": ["waterable"]},
        "whiteboard": {"state": "blank", "properties": ["writeable", "cleanable"]},
    },
}

# Optional rooms randomly grafted onto the base layout each run
OPTIONAL_ROOMS: Dict[str, Dict] = {
    "balcony": {
        "chair": {"state": "empty", "properties": ["sit"]},
        "telescope": {"state": "covered", "properties": ["useable", "openable"]},
    },
    "bathroom": {
        "mirror": {"state": "clear", "properties": ["lookable", "cleanable"]},
        "shower": {"state": "off", "properties": ["useable"]},
        "cabinet": {"state": "closed", "properties": ["openable"], "items": ["first_aid", "towel"]},
    },
    "basement": {
        "generator": {"state": "idle", "properties": ["repairable", "useable"]},
        "storage_box": {"state": "closed", "properties": ["openable"], "items": ["toolkit", "spare_fuse"]},
    },
}

# High-level ambience presets to seed lighting/temperature/noise
ENVIRONMENT_PRESETS = {
    "calm_morning": {"lighting": "day", "temperature": 21.0, "noise": 0.1},
    "storm_night": {"lighting": "night", "temperature": 18.0, "noise": 0.4},
    "winter_evening": {"lighting": "evening", "temperature": 16.0, "noise": 0.2},
}

DEFAULT_HUNGER_RATE = 0.005
DEFAULT_FATIGUE_RATE = 0.01
DEFAULT_LONELINESS_RATE = 0.01
# Needs, all on one scale: 0 = fine, 1 = desperate
NEEDS = ("hunger", "fatigue", "cold", "loneliness")
# Messages kept per agent in heard_log (the world is deep-copied for every imagined option)
HEARD_LOG_LIMIT = 50
