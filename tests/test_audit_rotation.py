"""Tests fuer die Groessen-Rotation des Audit-Logs."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import policy


def test_rotates_when_over_limit(tmp_path):
    log = tmp_path / "audit.log"
    log.write_text("x" * 100, encoding="utf-8")
    policy._rotate_if_large(log, max_bytes=50)
    assert (tmp_path / "audit.log.1").exists()
    assert not log.exists()


def test_keeps_when_under_limit(tmp_path):
    log = tmp_path / "audit.log"
    log.write_text("small", encoding="utf-8")
    policy._rotate_if_large(log, max_bytes=1000)
    assert log.exists()
    assert not (tmp_path / "audit.log.1").exists()


def test_rotation_replaces_old_backup(tmp_path):
    log = tmp_path / "audit.log"
    backup = tmp_path / "audit.log.1"
    backup.write_text("veraltet", encoding="utf-8")
    log.write_text("y" * 100, encoding="utf-8")
    policy._rotate_if_large(log, max_bytes=50)
    assert backup.read_text(encoding="utf-8") == "y" * 100
