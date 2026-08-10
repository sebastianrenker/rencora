"""Sichert die Pfad-Traversal-Abwehr fuer hochgeladene Dateinamen ab."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dashboard.server import _safe_filename


def test_strips_directory_traversal():
    for raw in ("../../../../etc/passwd", "..\\..\\..\\win.ini",
                "/etc/shadow", "C:\\Windows\\System32\\cmd.exe"):
        safe = _safe_filename(raw)
        assert "/" not in safe and "\\" not in safe
        assert ".." not in safe


def test_removes_control_and_reserved_chars():
    safe = _safe_filename('bad<>:"|?*name\x00.txt')
    for ch in '<>:"|?*\x00':
        assert ch not in safe


def test_empty_or_dotonly_becomes_default():
    assert _safe_filename("") == "upload"
    assert _safe_filename("   ...   ") == "upload"
    assert _safe_filename("....") == "upload"


def test_normal_name_preserved():
    assert _safe_filename("Rechnung 2026.pdf") == "Rechnung 2026.pdf"
