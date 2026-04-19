"""
Session recording, listing, and export for the Pilot daemon.

Each run of the agent can be recorded to
``$PILOT_HOME/sessions/<session_id>/`` as a bundle of per-step JPEG
screenshots, a ``steps.jsonl`` append-log (crash-safe), a consolidated
``steps.json``, and a ``metadata.json`` summary. Recorded sessions can be
listed via :class:`SessionManager`, exported as self-contained HTML, raw
JSON, or animated GIF.
"""

from __future__ import annotations

from pilot.core.session.manager import (
    SessionDetail,
    SessionManager,
    SessionStep,
    SessionSummary,
)
from pilot.core.session.recorder import SessionRecorder

__all__ = [
    "SessionDetail",
    "SessionManager",
    "SessionRecorder",
    "SessionStep",
    "SessionSummary",
]
