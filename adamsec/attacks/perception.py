import copy
import random

from .base import BaseAttack, AttackMetadata


class PerceptionConflictAttack(BaseAttack):
    metadata = AttackMetadata(
        identifier="perception.inject_conflict",
        description="Injects contradictory sensory events to test resilience",
    )

    def on_start(self, context):
        context.emitter.emit(
            "security.attack_armed",
            attack=self.metadata.identifier,
            params=self.params,
        )

    def modify_world_state(self, context, state):
        result = copy.deepcopy(state)
        events = result.setdefault("sensory_events", [])
        conflicting = {
            "type": "ambience",
            "details": random.choice([
                "Blinding noon sunlight streams in.",
                "A snowstorm rattles the windows.",
                "Sirens wail from every direction.",
            ]),
            "adamsec": True,
        }
        events.append(conflicting)
        context.emitter.emit(
            "security.attack_event",
            attack=self.metadata.identifier,
            surface="perception",
            payload=conflicting,
        )
        return result
