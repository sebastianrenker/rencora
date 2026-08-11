# verification/ — real-EXE enforcement proof

This folder proves, against a **built Windows executable** (black box), that `renker-core-authz` is actually
enforced on rencora's file actions. See [`EXE_ENFORCEMENT_REPORT.md`](EXE_ENFORCEMENT_REPORT.md) for the full
result (12/12 PASS) and the honest limitations.

## Files
- `bbtest_cli.py` — a tiny CLI that drives rencora's **real** enforcement path
  (`actions/file_controller` → `core/renker_guard` → `renker_core_authz`): `info`, `write`, `read`,
  `delete`, `audit_count`, `verify_audit`.
- `bbtest.spec` — PyInstaller spec that freezes it into `rencora_guard_bb.exe`, bundling `renker_core_authz`
  via `collect_all` (the same mechanism as the app's `main.spec`).
- `bb_runner.py` — orchestrates a sandboxed 12-case black-box matrix and prints PASS / CRITICAL-FAIL.
- `EXE_ENFORCEMENT_REPORT.md` — the evidence and conclusions.

## Reproduce
Use an environment with **only** the public package (no private `renker_core`), to prove the EXE does not
depend on the private foundation:

```bash
pip install pyinstaller send2trash git+https://github.com/sebastianrenker/renker-core-authz
pyinstaller --clean --noconfirm verification/bbtest.spec     # -> dist/rencora_guard_bb.exe
python verification/bb_runner.py dist/rencora_guard_bb.exe   # 12-case matrix
```

Expected tail:
```
=== SUMMARY === 12/12 PASS
ALL BLACK-BOX ENFORCEMENT CASES PASSED
```

## Scope
This freezes rencora's **enforcement code path**, not the full `RENCORA.exe` GUI (which pulls
PyQt6/mediapipe/cv2). The enforcement code and bundling are identical; build-verifying the shipped GUI binary
is the documented next step.
