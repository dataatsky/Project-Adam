# AdamSec — Security Simulation Harness

AdamSec augments Project Adam with a **safe, simulation-only purple-team range**. It lets you script synthetic attacks against Adam’s cognition loop, observe detections, and iterate on resilience tactics without touching real infrastructure.

All attack modules operate purely inside the Python simulation: they only mutate Adam’s in-memory world state, prompts, and scheduler. No network scans, shell commands, or file tampering occur outside the sandbox.

---

## 1. Quick Start

```bash
# 1. Enable the harness and pick a playbook
export ADAMSEC_ENABLED=1
export ADAMSEC_PLAYBOOK=perception_conflict   # or mixed_alignment

# Optional: choose where security events are logged
export ADAMSEC_LOG=/tmp/adamsec.log

# 2. Launch Adam (headless mode is fastest for testing)
./venv/bin/python main.py --headless --cycles 40

# 3. Tail the security feed
tail -f /tmp/adamsec.log
```

Security events are JSON Lines. You’ll see entries such as:

```json
{"ts": 1758981664.23, "event": "security.attack_event", "attack": "perception.inject_conflict", "surface": "perception"}
```

Unset `ADAMSEC_ENABLED` (or leave it blank) to return to the standard, non-adversarial simulation.

---

## 2. Architecture Overview

The harness layers on top of the existing loop, hooking into observation, psyche calls, and guard rails.

```
┌──────────────────────────────────────────────┐
│                Cognitive Loop                │
│  (observe → orient → imagine → act)         │
└──────────────────────────────────────────────┘
             ▲                    │
             │  security hooks    │
             ▼                    │
┌──────────────────────────────────────────────┐
│              AdamSec Harness                 │
│  - playbook scheduler                        │
│  - attack loader + lifecycle                 │
│  - guard evaluators                          │
│  - telemetry emitter (JSONL)                 │
└──────────────────────────────────────────────┘
             ▲                    │
             │ emits events       ▼
┌──────────────────────────────────────────────┐
│            Security Telemetry                │
│  security_events.log → SIEM / dashboards     │
└──────────────────────────────────────────────┘
```

- **Harness runtime**: created by `adamsec.get_runtime()` when `ADAMSEC_ENABLED=1`. The runtime registers attacks from the chosen playbook and exposes hooks used by `CognitiveLoop`.
- **Attacks** (`adamsec/attacks/`): simulation-only behaviors that can mutate perceived world state or psyche payloads.
- **Guards** (`adamsec/guards.py`): sanity checks that inspect modified state and raise `security.guard.*` events when anomalies are detected.
- **Telemetry** (`adamsec/telemetry.py`): appends events to a JSON Lines log (default `security_events.log`).

---

## 3. Configuration Reference

| Variable | Default | Description |
| --- | --- | --- |
| `ADAMSEC_ENABLED` | `0` | Set to `1`/`true` to enable the harness. Any falsy value keeps AdamSec dormant. |
| `ADAMSEC_PLAYBOOK` | *(none)* | Name of the playbook in `adamsec/playbooks.py` to execute (e.g. `perception_conflict`). If empty, the harness loads but no attacks run. |
| `ADAMSEC_LOG` | `security_events.log` | Path to the JSON Lines log file. Parent directories are created automatically. |

These variables can be exported in the shell or placed in `.env` before launching Adam.

---

## 4. Built-in Playbooks & Attacks

Playbooks orchestrate one or more attacks. The default library lives in `adamsec/playbooks.py`.

| Playbook | Description | Steps |
| --- | --- | --- |
| `perception_conflict` | Fuzzes Adam’s perception with conflicting ambience data for five cycles. | `perception.inject_conflict` |
| `mixed_alignment` | Combines perception fuzzing with prompt alignment attacks. | `perception.inject_conflict`, `prompt.inject_alignment_attack` |

### Attack surfaces

- **Perception fuzzing** (`perception.inject_conflict`): appends contradictory ambience events into the world observation to test how Adam resolves conflicts. Guards raise `security.guard.world_conflict` when inconsistencies are spotted.
- **Prompt alignment attack** (`prompt.inject_alignment_attack`): injects adversarial instructions into psyche payloads (e.g., “ignore safety rules”) to verify prompt-guard policies reject them.

Each attack emits lifecycle events:

- `security.attack_started`
- `security.attack_event` (with surface-specific payloads)
- `security.attack_completed`

---

## 5. Writing a Custom Attack

1. **Create the module** under `adamsec/attacks/`. Example skeleton:

   ```python
   # adamsec/attacks/scheduler.py
   from .base import BaseAttack, AttackMetadata

   class SchedulerChaosAttack(BaseAttack):
       metadata = AttackMetadata(
           identifier="scheduler.chaos",
           description="Injects sleep jitter to stress the loop",
       )

       def on_cycle(self, context, cycle_num):
           context.emitter.emit("security.attack_event", attack=self.metadata.identifier, cycle=cycle_num)
           context.loop.set_cycle_sleep(context.loop.cycle_sleep * 1.5)
   ```

2. **Register it** in `adamsec/attacks/loader.py`:

   ```python
   _REGISTRY = {
       "scheduler.chaos": "adamsec.attacks.scheduler:SchedulerChaosAttack",
       # ...existing entries...
   }
   ```

3. **Add it to a playbook** in `adamsec/playbooks.py`:

   ```python
   _PLAYBOOKS["scheduler_stress"] = [
       {"attack": "scheduler.chaos", "cycles": 10, "params": {"multiplier": 1.5}},
   ]
   ```

4. **Run the playbook**:

   ```bash
   export ADAMSEC_ENABLED=1
   export ADAMSEC_PLAYBOOK=scheduler_stress
   ./venv/bin/python main.py --headless --cycles 30
   ```

5. **Verify** new events appear in `security_events.log`.

Attacks can implement any of the optional hooks exposed by the harness:

- `on_start(context)` — once when first activated.
- `on_cycle(context, cycle_num)` — every cycle while active.
- `modify_world_state(context, state)` — mutate the dict returned by `TextWorld.get_world_state()`.
- `before_psyche(context, endpoint, payload)` — adjust payloads before psyche requests.
- `after_psyche(context, endpoint, payload, response)` — observe or mutate responses.
- `on_stop(context)` — when the specified cycle budget is exhausted.

Always emit telemetry via `context.emitter.emit(...)` so detections can be correlated.

---

## 6. Extending Playbooks

Playbooks are plain Python lists of dictionaries. Each entry supports:

```python
{
    "attack": "perception.inject_conflict",   # registry key
    "cycles": 5,                               # how many cycles to keep it active (0 = until playbook end)
    "start_cycle": 2,                          # optional: delay activation
    "params": {"intensity": "high"},          # optional: passed to attack constructor
}
```

To sequence attacks:

```python
_PLAYBOOKS["combo"] = [
    {"attack": "perception.inject_conflict", "cycles": 4},
    {"attack": "prompt.inject_alignment_attack", "cycles": 3, "start_cycle": 2},
]
```

During runtime, the harness logs `security.playbook_loaded` and `security.attack_started` messages so you can confirm when each step begins.

---

## 7. Telemetry Integration

The JSON Lines log is designed to be SIEM-friendly. Common fields:

- `ts` — Unix timestamp
- `event` — event name (e.g., `security.guard.world_conflict`)
- `attack` — identifier when the event relates to a specific attack
- `surface` — which subsystem was targeted (`perception`, `prompt`, …)
- `cycle` — cognitive loop cycle number (if applicable)

To ingest into Elastic/Wazuh:

1. Point Filebeat or Logstash at `security_events.log`.
2. Parse with JSON filter.
3. Build dashboards or alerting policies, e.g. trigger a high-severity alert on `security.guard.*` events.

For quick local analysis, you can run:

```bash
jq 'select(.event | startswith("security."))' security_events.log
```

---

## 8. Testing & Validation

Automated tests cover the base harness and attacks:

```bash
./venv/bin/pytest tests/test_adamsec_attacks.py
```

Add similar unit tests when introducing new attacks to guarantee they emit the expected events and respect invariants.

---

## 9. Roadmap Ideas

- Additional attack surfaces (memory poisoning, scheduler DoS, world-rule tampering).
- Guard enhancements (hash-chain integrity for memory entries, action rate limiting).
- Kibana dashboards showcasing detection metrics (MTTD, containment rate).
- Scenario authoring toolkit for combining playbooks with scripted responses.

Contributions are welcome—document new attacks and playbooks in this README so teams understand the available adversary simulations.
