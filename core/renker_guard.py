from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

RENKER_CORE_AVAILABLE = False
try:
    from renker_core_authz.audit import AuditLog
    from renker_core_authz.capabilities import Capability, CapabilityStore, PathScope
    from renker_core_authz.identity import Actor
    from renker_core_authz.integration import GuardedFilesystem
    from renker_core_authz.policy import evaluate

    RENKER_CORE_AVAILABLE = True
except ImportError:
    try:
        from renker_core.audit import AuditLog
        from renker_core.capabilities import Capability, CapabilityStore, PathScope
        from renker_core.identity import Actor
        from renker_core.integration import GuardedFilesystem
        from renker_core.policy import evaluate

        RENKER_CORE_AVAILABLE = True
    except ImportError:
        AuditLog = Capability = CapabilityStore = PathScope = Actor = GuardedFilesystem = None
        evaluate = None


def is_available() -> bool:
    return RENKER_CORE_AVAILABLE


def session_actor(session_id: str):
    _require()
    return Actor("agent", session_id)


def load_grants(config_path: str | Path) -> list[dict]:
    path = Path(config_path)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.get("grants", []))


def build_store(grants: list[dict]):
    _require()
    store = CapabilityStore()
    now = datetime.now(timezone.utc)
    for grant in grants:
        store.grant(
            Capability(
                capability=grant["capability"],
                scope=PathScope(base=str(Path(grant["scope"]).expanduser())),
                granted_to=grant["granted_to"],
                granted_by=grant.get("granted_by", "human:sebastian"),
                issued_at=now,
                expires_at=None,
                approval_policy=grant.get("approval_policy", "auto"),
                risk_tier=grant.get("risk_tier", "low"),
            )
        )
    return store


class RencoraFileGuard:
    def __init__(self, audit_path: str | Path, grants: list[dict]):
        _require()
        self._fs = GuardedFilesystem(build_store(grants), AuditLog(audit_path))

    def write(self, session_id: str, target: str, content: str):
        return self._fs.write(session_actor(session_id), target, content)

    def read(self, session_id: str, target: str):
        return self._fs.read(session_actor(session_id), target)


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def default_config_path() -> Path:
    return _base_dir() / "config" / "renker_capabilities.json"


def _audit_path(config: dict, config_file: Path) -> Path:
    configured = config.get("audit_path")
    if configured:
        return Path(configured)
    return config_file.parent / "renker_audit.log"


def _record_decision(config, config_file, actor, action, target, result) -> None:
    try:
        log = AuditLog(_audit_path(config, config_file))
        outcome = "allowed" if result.decision.value == "ALLOW" else "blocked"
        log.record(
            actor=actor.urn,
            action=action,
            target=str(target),
            capability=result.capability_id,
            policy_decision=result.decision.value,
            reason=result.reason,
            outcome=outcome,
        )
    except Exception:
        pass


def enforce_capability(target, action: str, config_path=None) -> str | None:
    path = Path(config_path) if config_path else default_config_path()
    if not path.exists():
        return None
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return f"Access denied: capability config present but unreadable: {error}"
    if not isinstance(config, dict):
        return "Access denied: capability config is malformed"
    if not config.get("enforce", False):
        return None
    if not RENKER_CORE_AVAILABLE:
        return "Access denied: capability enforcement enabled but renker_core is not installed"
    try:
        store = build_store(config.get("grants", []))
        actor = Actor("agent", config.get("session_id", "rencora"))
        result = evaluate(actor=actor, action=action, target=str(target), store=store)
    except Exception as error:
        return f"Access denied: capability check failed: {error}"
    _record_decision(config, path, actor, action, target, result)
    if result.decision.value == "ALLOW":
        return None
    return f"Access denied by capability policy: {result.reason}"


def _require() -> None:
    if not RENKER_CORE_AVAILABLE:
        raise RuntimeError(
            "renker_core is not installed; install renker-core to enable capability guarding"
        )
