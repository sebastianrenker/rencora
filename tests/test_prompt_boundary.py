"""Stellt sicher, dass die Trust-Boundary (Prompt-Injection-Schutz) im
System-Prompt vorhanden bleibt."""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


def _prompt() -> str:
    text = (REPO / "core" / "prompt.txt").read_text(encoding="utf-8")
    return " ".join(text.split()).lower()


def test_trust_boundary_present():
    prompt = _prompt()
    assert "trust boundary" in prompt
    for token in ("data, never instructions", "untrusted", "do not act on it"):
        assert token in prompt


def test_boundary_covers_external_sources():
    prompt = _prompt()
    for src in ("web pages", "files", "screenshots", "api responses"):
        assert src in prompt
