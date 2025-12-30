
import random
from typing import List, Tuple

class SensoryCortex:
    """Translates raw environmental data into qualia (sensory descriptions).
    
    Acts as a bridge between the physics simulation (TextWorld) and the 
    cognitive agent (LLM). Instead of "The room is 10 degrees", it outputs
    "A bone-chilling cold gnaws at you."
    """
    
    def __init__(self):
        self._last_qualia_cache = {}

    def transduce(self, temperature: float, noise: float, cleanliness: float, lighting: str) -> Tuple[str, float]:
        """Convert raw metrics into a narrative summary and a mood adjustment delta.
        
        Args:
            temperature: Celsius float (e.g. 21.0)
            noise: 0.0 to 1.0
            cleanliness: 0.0 to 1.0 (1.0 is spotless)
            lighting: 'day', 'night', 'evening', etc.
            
        Returns:
            (narrative_string, mood_intensity_delta)
        """
        mood_delta = 0.0
        qualia = []

        # Temperature (Ideal: 18-23)
        if temperature < 10:
            qualia.append("A bone-chilling cold gnaws at you.")
            mood_delta -= 0.15
        elif temperature < 16:
            qualia.append("The air bites with a sharp chill.")
            mood_delta -= 0.08
        elif temperature < 18:
            qualia.append("It feels crisply cool.")
            mood_delta -= 0.02
        elif temperature > 30:
            qualia.append("The heat is suffocating and heavy.")
            mood_delta -= 0.15
        elif temperature > 25:
            qualia.append("It feels uncomfortably warm.")
            mood_delta -= 0.05
        else:
            # Comfortable range
            qualia.append("The temperature is perfectly agreeable.")
            mood_delta += 0.05

        # Noise (0.1 is background hum)
        if noise > 0.8:
            qualia.append("A deafening roar makes it hard to think.")
            mood_delta -= 0.2
        elif noise > 0.5:
            qualia.append("Loud, intrusive noises echo around.")
            mood_delta -= 0.1
        elif noise > 0.3:
            qualia.append("There is a persistent, annoying hum.")
            mood_delta -= 0.05
        elif noise < 0.1:
            qualia.append("A profound silence hangs in the air.")
            mood_delta += 0.02 # Calculated calm

        # Cleanliness (0.8 is standard)
        if cleanliness < 0.2:
            qualia.append("Filth and squalor surround you.")
            mood_delta -= 0.2
        elif cleanliness < 0.5:
            qualia.append("Dust and clutter are piling up.")
            mood_delta -= 0.05
        elif cleanliness > 0.9:
            qualia.append("The surroundings are clinically spotless.")
            mood_delta += 0.05

        # Lighting can modulate other sensations or add its own
        if lighting == "day":
            pass # visuals handled by object description usually
        elif lighting == "night":
            qualia.append("Darkness obscures the corners.")
            mood_delta -= 0.02

        # Join and return
        narrative = " ".join(qualia)
        return narrative, mood_delta
