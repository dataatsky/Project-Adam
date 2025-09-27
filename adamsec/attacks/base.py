from dataclasses import dataclass


@dataclass
class AttackMetadata:
    identifier: str
    description: str


class BaseAttack:
    """Base class for synthetic, simulation-only attacks."""

    metadata: AttackMetadata

    def __init__(self, params: dict | None = None):
        self.params = params or {}

    # Optional hooks expected by the harness ---------------------------------
    def on_start(self, context):  # pragma: no cover - optional hook
        return None

    def on_cycle(self, context, cycle_num):  # pragma: no cover - optional
        return None

    def on_stop(self, context):  # pragma: no cover - optional
        return None

