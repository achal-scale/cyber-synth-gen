"""
audit.py - structured security-event audit logging.

Emits one structured JSON line per security-relevant event with actor, action,
resource, outcome, and timestamp. Written to stdout so the container runtime
captures it. Secret contents (passwords, tokens) are never logged.
"""
import json
import logging
import sys
from datetime import datetime

_logger = logging.getLogger("w.audit")
if not _logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(_handler)
    _logger.setLevel(logging.INFO)
    _logger.propagate = False


def audit(action: str, actor=None, resource=None, outcome: str = "success", **extra) -> None:
    """Record one security-relevant event. Never pass secret values in extra."""
    record = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "event": "security_audit",
        "action": action,
        "actor": actor,
        "resource": resource,
        "outcome": outcome,
    }
    if extra:
        record.update(extra)
    _logger.info(json.dumps(record))
