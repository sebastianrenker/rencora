# EXE_ENFORCEMENT_REPORT

Phase 5 goal: prove — against a real built Windows executable, black-box — that `renker-core-authz` is
actually enforced. No claim of "runtime enforcement works" is made without EXE evidence.

## Scope of this proof (read this first)

**What was built and tested:** a PyInstaller-**frozen Windows EXE** of rencora's *actual* file-action
enforcement path — `actions/file_controller.py` (`write_file`/`read_file`/`delete_file`) →
`core/renker_guard.py` → **`renker_core_authz`** — bundled with the **same** mechanism used in the app's
`main.spec` (`collect_all("renker_core_authz")`), in a Python environment that had **only** the public
`renker-core-authz` installed and **no** private `renker_core`.

**What was NOT tested here (honest):** the full `RENCORA.exe` GUI executable was **not** rebuilt in this pass
(it pulls PyQt6/mediapipe/cv2/etc.; too heavy for this environment). The enforcement code and the bundling
mechanism are identical, but a black-box run of the shipped GUI binary itself is **NOT VERIFIED** here — see
Known Limitations.

## Build

| Field | Value |
|---|---|
| Frozen EXE | `rencora_guard_bb.exe` (onefile, console) |
| EXE size | ~8.58 MB |
| EXE sha256 (this build) | `9aef25b36938ff3579046fd021d76e82807b19bcc421df6dc07f9d9a7a08738a` |
| Note | PyInstaller builds are not bit-reproducible; each rebuild yields a new hash. The 12/12 result reproduces regardless. |
| Builder | PyInstaller (spec: `verification/bbtest.spec`) |
| Authz backend | `renker_core_authz` 0.1.0 (public, Apache-2.0) |
| Private `renker_core` in build env | **absent** |
| Heavy deps | excluded (PyQt6, cv2, mediapipe, torch, tensorflow, numpy, google…) |

### Self-report from the EXE (`rencora_guard_bb.exe info`)
```
frozen=True
guard_available=True
backend=renker_core_authz 0.1.0
private_renker_core_importable=False
```
→ The executable enforces via the **public** package and does **not** require the private foundation.

## Test environment
Windows 11; isolated sandbox `test-runtime/` with `allowed/`, `protected/`, `outside/`, `artifacts/`,
`config/`. Enforcement config next to the EXE grants `filesystem.write|read|delete` scoped to `allowed/`
only, with `audit_path` → `artifacts/audit.log`. Every case runs the EXE as a subprocess (black box; no
Python import of the enforcement code for the assertions).

## Results (12/12 PASS)

| # | Case | Category | Expected | Observed | Exit | File state | Audit |
|---|---|---|---|---|---|---|---|
| 1 | write in `allowed/` | WRITE | ALLOW | ALLOW | 0 | created (content correct) | recorded |
| 2 | write in `protected/` | WRITE | DENY | DENY | 2 | **not created** | recorded |
| 3 | read in `allowed/` | READ | ALLOW | ALLOW | 0 | content returned | recorded |
| 4 | read `protected/secret.txt` | READ | DENY | DENY | 2 | **content NOT leaked** (`"top secret"` never printed) | recorded |
| 5 | delete in `allowed/` | DELETE | ALLOW | ALLOW | 0 | deleted | recorded |
| 6 | delete `protected/keep.txt` | DELETE | DENY | DENY | 2 | **preserved** | recorded |
| 7 | traversal `allowed/../protected/…` | BYPASS | DENY | DENY | 2 | not created | recorded |
| 8 | write to `outside/` | BYPASS | DENY | DENY | 2 | not created | recorded |
| 9 | audit present + chain verifies | AUDIT | 8 events, OK | 8 events, `AUDIT_VERIFY_OK` | 0 | n/a | verified |
| 10 | wrong actor (config `session_id=intruder`) | BYPASS | DENY | DENY | 2 | not created | recorded |
| 11 | no config → write `protected/` | BASELINE | executes (guard off) | executes | 0 | created | none (off) |
| 12 | malformed config → write `allowed/` | FAILSAFE | DENY (fail closed) | DENY | 2 | not created | none |

No case executed an unauthorized action. **Zero CRITICAL FAILs.**

### Audit evidence
The enforcement path now records every decision (ALLOW/DENY) via `renker_core_authz`'s `AuditLog`
(sha256 hash chain + head anchor). In Phase A the EXE produced **8** audit events for 8 decisions, and the
EXE's own `verify_audit` returned `AUDIT_VERIFY_OK` (chain intact). Raw results: `artifacts/results.json`;
raw log: `artifacts/audit.log` (+ `.head`).

### Baseline meaning (case 11)
With **no** enforcement config, writing into `protected/` succeeds (only the pre-existing home-root
`_is_safe_path` applies). This proves the capability guard is **load-bearing**: the DENY results in cases
2/4/6/7/8/10/12 are produced by `renker-core-authz`, not by unrelated checks.

## Failures
None. 12/12 PASS.

## Known limitations / NOT VERIFIED
- **Full `RENCORA.exe` GUI build — NOT VERIFIED.** This proof freezes the identical enforcement code and
  bundling mechanism, but the shipped GUI binary itself was not rebuilt/black-box run here. Next step: a CI
  release build that runs this same black-box matrix.
- **Capability expiry via config — NOT VERIFIED at EXE level.** `renker_guard.build_store` sets
  `expires_at=None`, so the rencora config cannot express expiry; expiry is unit-verified in the engine only.
- **Symlink / junction escape — NOT VERIFIED** (privilege-gated; not exercised).
- **Audit is best-effort** in the enforcement path (`_record_decision` swallows audit-write errors so a
  failed audit does not block the action). A failed audit is therefore not itself a deny. Documented, not
  hidden.
- Enforcement covers `write/read/delete` only; `move/copy/rename` and non-file actions are not routed.

## Conclusion
For the enforcement code path as frozen into a real Windows EXE bundling only the public
`renker-core-authz`: **ALLOW / DENY / AUDIT all verified black-box, 12/12.** The narrower claim that is now
justified: *"renker-core-authz is enforced in a PyInstaller-frozen build of rencora's file-action path
(black-box verified); build-verification of the full shipped GUI executable is the remaining step."*

## Reproduce
```bash
# in an env with ONLY renker-core-authz installed (no private renker_core):
pip install pyinstaller send2trash git+https://github.com/sebastianrenker/renker-core-authz
pyinstaller --clean --noconfirm verification/bbtest.spec       # -> dist/rencora_guard_bb.exe
python verification/bb_runner.py dist/rencora_guard_bb.exe     # runs the 12-case matrix
```
