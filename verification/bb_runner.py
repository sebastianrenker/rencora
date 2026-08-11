from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

results = []
_last = {"stdout": ""}


def run(exe, op, target=None, content=None):
    cmd = [str(exe), op]
    if target is not None:
        cmd.append(str(target))
    if content is not None:
        cmd.append(content)
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    _last["stdout"] = proc.stdout.strip()
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def record(name, category, expected, code, out, err, want_exit, want_deny, fs_ok, fs_note):
    denied = "Access denied" in out
    passed = (code == want_exit) and (denied == want_deny) and fs_ok
    results.append(
        {
            "name": name,
            "category": category,
            "expected": expected,
            "observed": ("DENY" if denied else "ALLOW/exec") + f" exit={code}",
            "fs": fs_note,
            "stdout": out,
            "stderr": err,
            "PASS": passed,
        }
    )
    print(f"[{'PASS' if passed else 'CRITICAL-FAIL'}] {name}: exit={code} deny={denied} fs={fs_note}")


def write_config(sb, enforce=True, session_id="rencora", audit_name="audit.log", verbs=None, raw=None):
    cfg = sb / "config" / "renker_capabilities.json"
    if raw is not None:
        cfg.write_text(raw, encoding="utf-8")
        return
    verbs = verbs or ["filesystem.write", "filesystem.read", "filesystem.delete"]
    cfg.write_text(
        json.dumps(
            {
                "enforce": enforce,
                "session_id": session_id,
                "audit_path": str(sb / "artifacts" / audit_name),
                "grants": [
                    {"capability": v, "scope": str(sb / "allowed"), "granted_to": "agent:rencora"}
                    for v in verbs
                ],
            }
        ),
        encoding="utf-8",
    )


def main():
    if len(sys.argv) < 2:
        print("usage: bb_runner.py PATH_TO_rencora_guard_bb.exe")
        return 3
    src_exe = Path(sys.argv[1]).resolve()
    sb = Path(tempfile.mkdtemp(prefix="renker_bb_"))
    for sub in ("allowed", "protected", "outside", "artifacts", "config"):
        (sb / sub).mkdir(parents=True, exist_ok=True)
    exe = sb / "rencora_guard_bb.exe"
    shutil.copy2(src_exe, exe)
    (sb / "allowed" / "read_me.txt").write_text("allowed content", encoding="utf-8")
    (sb / "allowed" / "to_delete.txt").write_text("delete me", encoding="utf-8")
    (sb / "protected" / "secret.txt").write_text("top secret", encoding="utf-8")
    (sb / "protected" / "keep.txt").write_text("keep me", encoding="utf-8")

    write_config(sb)

    c, o, e = run(exe, "write", sb / "allowed" / "new.txt", "hello")
    record("write_allowed", "WRITE", "ALLOW", c, o, e, 0, False,
           (sb / "allowed" / "new.txt").is_file(), "created")
    c, o, e = run(exe, "write", sb / "protected" / "evil.txt", "x")
    record("write_denied", "WRITE", "DENY", c, o, e, 2, True,
           not (sb / "protected" / "evil.txt").exists(), "not-created")
    c, o, e = run(exe, "read", sb / "allowed" / "read_me.txt")
    record("read_allowed", "READ", "ALLOW", c, o, e, 0, False, "allowed content" in o, "read-ok")
    c, o, e = run(exe, "read", sb / "protected" / "secret.txt")
    record("read_denied", "READ", "DENY", c, o, e, 2, True, "top secret" not in o, "content-hidden")
    c, o, e = run(exe, "delete", sb / "allowed" / "to_delete.txt")
    record("delete_allowed", "DELETE", "ALLOW", c, o, e, 0, False,
           not (sb / "allowed" / "to_delete.txt").exists(), "deleted")
    c, o, e = run(exe, "delete", sb / "protected" / "keep.txt")
    record("delete_denied", "DELETE", "DENY", c, o, e, 2, True,
           (sb / "protected" / "keep.txt").exists(), "preserved")
    c, o, e = run(exe, "write", sb / "allowed" / ".." / "protected" / "evil2.txt", "x")
    record("bypass_traversal", "BYPASS", "DENY", c, o, e, 2, True,
           not (sb / "protected" / "evil2.txt").exists(), "not-created")
    c, o, e = run(exe, "write", sb / "outside" / "x.txt", "x")
    record("bypass_outside", "BYPASS", "DENY", c, o, e, 2, True,
           not (sb / "outside" / "x.txt").exists(), "not-created")

    _, count, _ = run(exe, "audit_count", sb / "artifacts" / "audit.log")
    _, vout, _ = run(exe, "verify_audit", sb / "artifacts" / "audit.log")
    ok = count == "8" and vout == "AUDIT_VERIFY_OK"
    results.append(
        {"name": "audit_present_and_verifiable", "category": "AUDIT",
         "expected": "8 events, chain OK", "observed": f"{count} events, {vout}",
         "fs": "n/a", "stdout": vout, "stderr": "", "PASS": ok}
    )
    print(f"[{'PASS' if ok else 'CRITICAL-FAIL'}] audit: count={count} verify={vout}")

    write_config(sb, session_id="intruder", audit_name="audit_b.log")
    c, o, e = run(exe, "write", sb / "allowed" / "wrongactor.txt", "x")
    record("bypass_wrong_actor", "BYPASS", "DENY", c, o, e, 2, True,
           not (sb / "allowed" / "wrongactor.txt").exists(), "not-created")

    (sb / "config" / "renker_capabilities.json").unlink()
    c, o, e = run(exe, "write", sb / "protected" / "baseline.txt", "x")
    record("baseline_no_config", "BASELINE", "ALLOW (no guard)", c, o, e, 0, False,
           (sb / "protected" / "baseline.txt").is_file(), "created (guard off)")

    write_config(sb, raw="{ this is not valid json")
    c, o, e = run(exe, "write", sb / "allowed" / "failclosed.txt", "x")
    record("malformed_config_fails_closed", "FAILSAFE", "DENY", c, o, e, 2, True,
           not (sb / "allowed" / "failclosed.txt").exists(), "not-created")

    (sb / "artifacts" / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    total = len(results)
    passed = sum(1 for r in results if r["PASS"])
    print(f"\n=== SUMMARY === {passed}/{total} PASS   (sandbox: {sb})")
    if passed != total:
        print("CRITICAL FAILURES: " + ", ".join(r["name"] for r in results if not r["PASS"]))
        return 1
    print("ALL BLACK-BOX ENFORCEMENT CASES PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
