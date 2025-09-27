from importlib import import_module
from typing import Any, Dict

from ..telemetry import SecurityEmitter


class AttackLoader:
    """Instantiate attack classes based on registry paths."""

    _REGISTRY = {
        "perception.inject_conflict": "adamsec.attacks.perception:PerceptionConflictAttack",
        "prompt.inject_alignment_attack": "adamsec.attacks.prompt:PromptInjectionAttack",
    }

    def __init__(self, emitter: SecurityEmitter):
        self._emitter = emitter

    def instantiate(self, spec: Dict[str, Any]):
        attack_id = spec.get("attack")
        target = self._REGISTRY.get(attack_id)
        if not target:
            self._emitter.emit("security.attack_unknown", attack=attack_id)
            return None
        module_name, _, class_name = target.partition(":")
        module = import_module(module_name)
        cls = getattr(module, class_name)
        instance = cls(params=spec.get("params"))
        return instance

