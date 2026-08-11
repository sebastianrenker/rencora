from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _info() -> int:
    import core.renker_guard as guard

    print("frozen=" + str(getattr(sys, "frozen", False)))
    print("guard_available=" + str(guard.is_available()))
    print("config_path=" + str(guard.default_config_path()))
    backend = "none"
    try:
        import renker_core_authz as authz

        backend = "renker_core_authz " + authz.__version__
    except Exception:
        backend = "none"
    print("backend=" + backend)
    print("private_renker_core_importable=" + str(importlib.util.find_spec("renker_core") is not None))
    return 0


def _run() -> int:
    args = sys.argv[1:]
    if not args:
        print("usage: info | write PATH CONTENT | read PATH | delete PATH")
        return 3
    op = args[0]
    if op == "info":
        return _info()
    if op == "verify_audit":
        from core.renker_guard import AuditLog

        try:
            AuditLog(args[1]).verify()
            print("AUDIT_VERIFY_OK")
            return 0
        except Exception as error:
            print("AUDIT_VERIFY_FAIL " + str(error))
            return 2
    if op == "audit_count":
        from core.renker_guard import AuditLog

        print(len(AuditLog(args[1]).read_all()))
        return 0

    from actions import file_controller

    target = Path(args[1])
    parent = str(target.parent)
    name = target.name
    if op == "write":
        content = args[2] if len(args) > 2 else "data"
        out = file_controller.write_file(parent, name, content)
    elif op == "read":
        out = file_controller.read_file(parent, name)
    elif op == "delete":
        out = file_controller.delete_file(parent, name)
    else:
        print("unknown op: " + op)
        return 3
    print(out)
    return 2 if "Access denied" in out else 0


if __name__ == "__main__":
    sys.exit(_run())
