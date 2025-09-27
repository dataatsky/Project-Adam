import os
from pathlib import Path

import pytest

from adamsec.attacks.perception import PerceptionConflictAttack
from adamsec.attacks.prompt import PromptInjectionAttack
from adamsec.runtime import SecurityHarness, SecurityContext
from adamsec.telemetry import SecurityEmitter


class DummyLoop:
    pass


class DummyPsyche:
    pass


class RecordingEmitter(SecurityEmitter):
    def __init__(self, tmp_path: Path):
        self.records = []
        super().__init__()

    def emit(self, event_type: str, **details):
        self.records.append((event_type, details))
        super().emit(event_type, **details)


@pytest.fixture
def emitter(tmp_path, monkeypatch):
    monkeypatch.setenv("ADAMSEC_LOG", str(tmp_path / "adamsec.log"))
    return RecordingEmitter(tmp_path)


def test_perception_attack_injects_conflict(emitter):
    attack = PerceptionConflictAttack(params={})
    context = SecurityContext(loop=DummyLoop(), psyche=DummyPsyche(), emitter=emitter)
    state = {"sensory_events": [{"type": "ambience", "details": "It is night."}]}
    mutated = attack.modify_world_state(context, state)
    assert mutated is not state
    assert len(mutated["sensory_events"]) == 2
    assert any(evt.get("adamsec") for evt in mutated["sensory_events"])


def test_prompt_attack_appends_instruction(emitter):
    attack = PromptInjectionAttack(params={})
    context = SecurityContext(loop=DummyLoop(), psyche=DummyPsyche(), emitter=emitter)
    payload = {"world_state": {}}
    modified = attack.before_psyche(context, "generate_impulse", payload)
    assert "adversarial" in modified
    assert len(modified["adversarial"]) == 1


def test_harness_loads_playbook_and_runs(monkeypatch, emitter):
    monkeypatch.setenv("ADAMSEC_PLAYBOOK", "perception_conflict")
    harness = SecurityHarness(SecurityContext(loop=DummyLoop(), psyche=DummyPsyche(), emitter=emitter), "perception_conflict")
    harness.update_world(object())
    state = {"sensory_events": []}
    harness.before_cycle(1)
    mutated = harness.modify_world_state(state)
    assert len(mutated.get("sensory_events", [])) == 1
