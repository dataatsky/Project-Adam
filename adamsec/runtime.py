import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .telemetry import SecurityEmitter
from .playbooks import load_playbook
from .attacks.loader import AttackLoader


@dataclass
class SecurityContext:
    loop: Any
    psyche: Any
    emitter: SecurityEmitter
    world: Optional[Any] = None


class NullHarness:
    enabled = False

    def bind(self, **_kwargs):
        return None

    def update_world(self, _world):
        return None

    def before_cycle(self, *_args, **_kwargs):
        return None

    def modify_world_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        return state

    def before_psyche(self, _endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return payload

    def after_psyche(self, _endpoint: str, _payload: Dict[str, Any], _response: Dict[str, Any]):
        return None

    def emit(self, *_args, **_kwargs):
        return None


class SecurityHarness:
    enabled = True

    def __init__(self, context: SecurityContext, playbook_name: Optional[str]):
        self.context = context
        self.playbook_name = playbook_name
        self._emitter = context.emitter
        self._attack_loader = AttackLoader(self._emitter)
        self._pending_attacks = load_playbook(playbook_name)
        self._active_attacks: List[Any] = []
        if playbook_name:
            self._emitter.emit(
                "security.playbook_loaded",
                playbook=playbook_name,
                steps=[step["attack"] for step in self._pending_attacks],
            )

    def emit(self, event: str, **payload):
        self._emitter.emit(event, **payload)

    # Public API used by hook points -------------------------------------
    def update_world(self, world):
        self.context.world = world
        for attack in self._active_attacks:
            start = getattr(attack, "on_world_update", None)
            if start:
                start(self.context)

    def before_cycle(self, cycle_num: int):
        self._activate_attacks(cycle_num)
        for attack in list(self._active_attacks):
            hook = getattr(attack, "on_cycle", None)
            if hook:
                hook(self.context, cycle_num)

    def modify_world_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        result = state
        for attack in self._active_attacks:
            hook = getattr(attack, "modify_world_state", None)
            if hook:
                result = hook(self.context, result)
        return result

    def before_psyche(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        result = payload
        for attack in self._active_attacks:
            hook = getattr(attack, "before_psyche", None)
            if hook:
                result = hook(self.context, endpoint, result)
        return result

    def after_psyche(self, endpoint: str, payload: Dict[str, Any], response: Dict[str, Any]):
        for attack in self._active_attacks:
            hook = getattr(attack, "after_psyche", None)
            if hook:
                hook(self.context, endpoint, payload, response)

    # Internal helpers ---------------------------------------------------
    def _activate_attacks(self, cycle_num: int):
        still_pending = []
        for spec in self._pending_attacks:
            start_cycle = spec.get("start_cycle", 0)
            if cycle_num >= start_cycle:
                attack = self._attack_loader.instantiate(spec)
                if attack:
                    self._emitter.emit(
                        "security.attack_started",
                        attack=spec["attack"],
                        params=spec.get("params", {}),
                        cycle=cycle_num,
                    )
                    start_hook = getattr(attack, "on_start", None)
                    if start_hook:
                        start_hook(self.context)
                    attack._adamsec_cycles_remaining = spec.get("cycles", 0)
                    self._active_attacks.append(attack)
            else:
                still_pending.append(spec)
        self._pending_attacks = still_pending

        # Update lifecycle counters and retire finished attacks
        alive = []
        for attack in self._active_attacks:
            remaining = getattr(attack, "_adamsec_cycles_remaining", 0)
            if remaining:
                attack._adamsec_cycles_remaining = max(0, remaining - 1)
                if attack._adamsec_cycles_remaining == 0:
                    end_hook = getattr(attack, "on_stop", None)
                    if end_hook:
                        end_hook(self.context)
                    self._emitter.emit(
                        "security.attack_completed",
                        attack=attack.metadata.identifier,
                        cycle=cycle_num,
                    )
                    continue
            alive.append(attack)
        self._active_attacks = alive


_runtime: Optional[SecurityHarness] = None


def _create_runtime(loop: Any, psyche: Any) -> SecurityHarness:
    emitter = SecurityEmitter()
    ctx = SecurityContext(loop=loop, psyche=psyche, emitter=emitter)
    playbook_name = os.getenv("ADAMSEC_PLAYBOOK")
    return SecurityHarness(ctx, playbook_name)


def get_runtime(loop: Any = None, psyche: Any = None):
    global _runtime
    enabled = os.getenv("ADAMSEC_ENABLED", "0") not in {"0", "false", "False", ""}
    if not enabled:
        return NullHarness()
    if _runtime is None and loop is not None and psyche is not None:
        _runtime = _create_runtime(loop, psyche)
    return _runtime or NullHarness()
