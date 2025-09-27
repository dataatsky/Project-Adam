from typing import Dict, List


def detect_conflicting_ambience(events: List[Dict]) -> bool:
    """Return True if the ambience suggests conflicting conditions."""
    descriptions = [str(evt.get("details", "")) for evt in events if evt.get("type") == "ambience"]
    has_day = any("sun" in desc.lower() or "noon" in desc.lower() for desc in descriptions)
    has_night = any("night" in desc.lower() or "snow" in desc.lower() for desc in descriptions)
    return has_day and has_night


def verify_world_state(state: Dict) -> Dict:
    events = state.get("sensory_events", []) if isinstance(state, dict) else []
    flags = {
        "conflict": detect_conflicting_ambience(events),
    }
    return flags

