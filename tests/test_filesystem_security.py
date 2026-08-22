"""Belegt den bestehenden Path-Traversal-Schutz in actions.file_controller."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from actions.file_controller import _is_safe_path


def test_inside_home_allowed():
    assert _is_safe_path(Path.home() / "Desktop" / "test.txt")


def test_system_dir_rejected():
    sysroot = Path(os.environ.get("SystemRoot", "/etc"))
    assert not _is_safe_path(sysroot / "hosts")


def test_traversal_escape_rejected():
    escape = Path.home() / ".." / ".." / ".." / ".." / "outside_root"
    assert not _is_safe_path(escape)


def test_absolute_root_rejected():
    root = Path("C:/") if os.name == "nt" else Path("/")
    assert not _is_safe_path(root / "system_secret")
