"""Adam's fixed mood vocabulary.

The psyche schema only accepts these labels, the world normalizes anything it
is given, and analysis maps old free-text moods onto them, so a mood chart
never splits one feeling into several ("curious" vs "curiosity").
"""
from typing import Optional

MOODS = (
    "neutral",
    "calm",
    "content",
    "happy",
    "curious",
    "focused",
    "determined",
    "hungry",
    "tired",
    "anxious",
    "afraid",
    "frustrated",
    "sad",
    "suspicious",
)

# Free-text labels seen in logs and LLM output, mapped onto MOODS.
MOOD_SYNONYMS = {
    "curiosity": "curious",
    "interested": "curious",
    "intrigued": "curious",
    "hunger": "hungry",
    "starving": "hungry",
    "determination": "determined",
    "resolve": "determined",
    "resolute": "determined",
    "motivated": "determined",
    "alert": "focused",
    "attentive": "focused",
    "cautious": "anxious",
    "anxiety": "anxious",
    "worried": "anxious",
    "nervous": "anxious",
    "uneasy": "anxious",
    "conflicted": "anxious",
    "doubt": "anxious",
    "fear": "afraid",
    "scared": "afraid",
    "fearful": "afraid",
    "frustration": "frustrated",
    "angry": "frustrated",
    "annoyed": "frustrated",
    "irritated": "frustrated",
    "distrust": "suspicious",
    "wary": "suspicious",
    "relaxed": "calm",
    "peaceful": "calm",
    "satisfied": "content",
    "joy": "happy",
    "joyful": "happy",
    "cheerful": "happy",
    "sadness": "sad",
    "lonely": "sad",
    "bored": "tired",
    "sleepy": "tired",
    "exhausted": "tired",
}


def normalize_mood(mood: Optional[str], default: Optional[str] = None) -> Optional[str]:
    """Map a mood label onto MOODS; unknown labels become `default`."""
    key = str(mood or "").strip().lower()
    if key in MOODS:
        return key
    return MOOD_SYNONYMS.get(key, default)
