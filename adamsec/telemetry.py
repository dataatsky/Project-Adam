import json
import os
import threading
import time
from pathlib import Path
from typing import Any


class SecurityEmitter:
    """Append-only JSON Lines emitter for security events.

    Designed to stay lightweight; emits to stdout when file path is not
    configured.
    """

    def __init__(self) -> None:
        path = os.getenv("ADAMSEC_LOG", "security_events.log")
        self._path = Path(path)
        self._lock = threading.Lock()
        # Ensure parent dirs exist for custom paths
        if self._path.parent and self._path.parent != Path(""):
            self._path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, event_type: str, **details: Any) -> None:
        payload = {
            "ts": time.time(),
            "event": event_type,
            **details,
        }
        line = json.dumps(payload, ensure_ascii=False)
        with self._lock:
            try:
                with self._path.open("a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except Exception:
                print(line)
