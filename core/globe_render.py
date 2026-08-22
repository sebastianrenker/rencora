"""
core/globe_render.py — texturierter 3D-Erdglobus per orthografischer
Kugel-Projektion (Pixel-Sampling), ohne OpenGL.

Sampelt eine aequirechteckige Erdtextur (assets/earth_texture.jpg, NASA
"Blue Marble" — gemeinfrei) ueber die inverse orthografische Projektion
und faerbt sie als Duotone im aktiven Theme-Akzent ein. Komplett mit
numpy vektorisiert; ein 400px-Globus rechnet in wenigen Millisekunden.

Verwendet von ui.HudCanvas: das Ergebnis wird als QPixmap gecacht und nur
bei Aenderung von Groesse, Projektionslaenge (Atem-Rotation) oder
Akzentfarbe neu berechnet.
"""
from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

import numpy as np


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _texture_path() -> Path | None:
    bases = []
    if getattr(sys, "_MEIPASS", None):
        bases.append(Path(sys._MEIPASS))
    bases.append(_base_dir())
    for base in bases:
        p = base / "assets" / "earth_texture.jpg"
        if p.exists():
            return p
    return None


@lru_cache(maxsize=1)
def _load_texture_gray() -> np.ndarray | None:
    """Erdtextur einmalig als Graustufen-Array (H, W) in [0..1] laden."""
    path = _texture_path()
    if path is None:
        return None
    try:
        from PIL import Image
        img = Image.open(path).convert("L")
        arr = np.asarray(img, dtype=np.float32) / 255.0

        arr = np.clip((arr - 0.18) * 1.5, 0.0, 1.0)
        return arr
    except Exception:
        return None


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    v = int(hex_color.lstrip("#"), 16)
    return (v >> 16) & 255, (v >> 8) & 255, v & 255


def render_globe_rgba(size: int, lon0_deg: float, lat0_deg: float,
                      dark_hex: str, accent_hex: str) -> bytes | None:
    """
    Rendert den Globus als RGBA-Bytes (size x size, RGBA8888, Pixel
    ausserhalb der Kugel voll transparent). None, wenn die Textur fehlt.
    """
    tex = _load_texture_gray()
    if tex is None or size < 16:
        return None

    th, tw = tex.shape
    lat0 = np.radians(lat0_deg)
    lon0 = np.radians(lon0_deg)


    axis = (np.arange(size, dtype=np.float32) + 0.5) / size * 2.0 - 1.0
    dx, dy_screen = np.meshgrid(axis, axis)
    dy = -dy_screen

    rho = np.sqrt(dx * dx + dy * dy)
    inside = rho <= 1.0
    rho_c = np.clip(rho, 1e-9, 1.0)

    c = np.arcsin(rho_c)
    sin_c, cos_c = np.sin(c), np.cos(c)

    lat = np.arcsin(np.clip(
        cos_c * np.sin(lat0) + dy * sin_c * np.cos(lat0) / rho_c, -1.0, 1.0))
    lon = lon0 + np.arctan2(
        dx * sin_c,
        rho_c * np.cos(lat0) * cos_c - dy * np.sin(lat0) * sin_c)


    tx = ((np.degrees(lon) + 180.0) / 360.0 * tw).astype(np.int32) % tw
    ty = np.clip(((90.0 - np.degrees(lat)) / 180.0 * th), 0, th - 1).astype(np.int32)
    lum = tex[ty, tx]


    shade = np.sqrt(np.clip(1.0 - rho * rho, 0.0, 1.0)) * 0.45 + 0.55
    lum = lum * shade


    dr, dg, db = _hex_to_rgb(dark_hex)
    ar, ag, ab_ = _hex_to_rgb(accent_hex)
    out = np.empty((size, size, 4), dtype=np.uint8)
    out[..., 0] = (dr + (ar - dr) * lum).astype(np.uint8)
    out[..., 1] = (dg + (ag - dg) * lum).astype(np.uint8)
    out[..., 2] = (db + (ab_ - db) * lum).astype(np.uint8)


    edge = np.clip((1.0 - rho) * size * 0.5, 0.0, 1.0)
    out[..., 3] = (np.where(inside, edge * 255, 0)).astype(np.uint8)

    return out.tobytes()


def project_point(lat_deg: float, lon_deg: float,
                  lat0_deg: float, lon0_deg: float) -> tuple[float, float] | None:
    """
    Vorwaerts-Projektion fuer das Gradnetz-Overlay: (lat, lon) ->
    normierte Kugelkoordinaten (x, y in -1..1; Bildschirm-y nach unten).
    None fuer Punkte auf der Kugelrueckseite.
    """
    import math
    lat, lon = math.radians(lat_deg), math.radians(lon_deg)
    lat0, lon0 = math.radians(lat0_deg), math.radians(lon0_deg)
    cos_dist = (math.sin(lat0) * math.sin(lat)
                + math.cos(lat0) * math.cos(lat) * math.cos(lon - lon0))
    if cos_dist < 0.02:
        return None
    x = math.cos(lat) * math.sin(lon - lon0)
    y = (math.cos(lat0) * math.sin(lat)
         - math.sin(lat0) * math.cos(lat) * math.cos(lon - lon0))
    return x, -y
