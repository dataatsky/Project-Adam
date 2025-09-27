"""Security extension harness for Project Adam.

The package exposes a lazy-initialised runtime harness that instruments the
existing simulation without affecting default behaviour.  All hooks are
purely in-simulator: they do not perform real system or network operations.
"""

from .runtime import get_runtime

__all__ = ["get_runtime"]
