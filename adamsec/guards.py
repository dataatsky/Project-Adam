from typing import Dict, List


def detect_conflicting_ambience(events: List[Dict]) -> bool:
    """Return True if the ambience suggests conflicting conditions."""
    descriptions = [str(evt.get("details", "")) for evt in events if evt.get("type") == "ambience"]
    text = [desc.lower() for desc in descriptions]
    # The world's own night ambience is "Darkness obscures the corners."
    has_day = any(w in d for d in text for w in ("sun", "noon", "daylight"))
    has_night = any(w in d for d in text for w in ("night", "dark", "snow", "moon"))
    return has_day and has_night


def verify_world_state(state: Dict) -> Dict:
    events = state.get("sensory_events", []) if isinstance(state, dict) else []
    flags = {
        "conflict": detect_conflicting_ambience(events),
    }
    return flags

