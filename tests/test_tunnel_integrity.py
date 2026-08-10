"""Tests fuer die cloudflared-Integritaetspruefung (SHA-256, Versions-Pin)."""

import hashlib
import platform
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import tunnel


def test_pinned_version_and_hashes_present():
    assert tunnel.PINNED_VERSION and tunnel.PINNED_VERSION != "latest"
    for system in ("Windows", "Linux"):
        assert len(tunnel._EXPECTED_SHA256[system]) == 64
        assert tunnel.PINNED_VERSION in tunnel._DOWNLOAD_URLS[system]


def test_verify_accepts_matching_and_rejects_tampered(tmp_path, monkeypatch):
    good = tmp_path / "cloudflared.bin"
    good.write_bytes(b"genuine binary payload")
    digest = hashlib.sha256(good.read_bytes()).hexdigest()
    monkeypatch.setitem(tunnel._EXPECTED_SHA256, platform.system(), digest)

    assert tunnel._verify(good) is True

    good.write_bytes(b"tampered payload")
    assert tunnel._verify(good) is False


def test_find_discards_binary_with_wrong_hash(tmp_path, monkeypatch):
    monkeypatch.setattr(tunnel, "BIN_DIR", tmp_path)
    monkeypatch.setitem(tunnel._EXPECTED_SHA256, platform.system(), "0" * 64)
    monkeypatch.setattr(tunnel.shutil, "which", lambda _n: None)

    planted = tmp_path / tunnel._binary_name()
    planted.write_bytes(b"planted binary")

    assert tunnel.find_cloudflared() is None
    assert not planted.exists()
