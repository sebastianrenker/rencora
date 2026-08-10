"""
core/theme_manager.py — Farbschema-Engine mit speicherbaren Profilen.

Profile liegen in config/themes.json:
    {
      "active": "Rencora Gruen",
      "profiles": {
        "Rencora Gruen": { "PRI": "#00ff41", "BG": "#000a00", ... },
        "Mein Blau":     { "PRI": "#00aaff", ... }
      }
    }

Die Keys entsprechen den Attributen der Farbklasse `C` in ui.py. Ein Profil
muss nicht alle Keys enthalten — fehlende behalten den eingebauten Standard.
Dieselbe Datei wird vom Dashboard-Server (/api/theme) gelesen, damit exe und
Browser-Dashboard immer dasselbe Schema zeigen.
"""
import json
import re
import sys
from pathlib import Path


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR   = _base_dir()
THEME_FILE = BASE_DIR / "config" / "themes.json"


DEFAULT_PROFILE_NAME = "Rencora Lila"
DEFAULT_COLORS = {
    "PRI":      "#8a2be2",
    "BG":       "#131019",
    "DARK":     "#161320",
    "PANEL":    "#1b1726",
    "PANEL2":   "#201b2e",
    "BORDER":   "#2b2440",
    "TEXT":     "#e8e4f2",
    "TEXT_DIM": "#8f87a3",
    "GREEN":    "#b980ff",
    "ACC":      "#ff6b00",
}

GREEN_PROFILE_NAME = "Rencora Gruen"
GREEN_COLORS = {
    "PRI":      "#00ff41",
    "BG":       "#000a00",
    "DARK":     "#000d00",
    "PANEL":    "#00100a",
    "PANEL2":   "#001208",
    "BORDER":   "#0a2e0a",
    "TEXT":     "#7fff7f",
    "TEXT_DIM": "#2a6e2a",
    "GREEN":    "#00ff88",
    "ACC":      "#ff6b00",
}


EDITABLE_KEYS = [
    ("PRI",      "Akzentfarbe"),
    ("BG",       "Hintergrund"),
    ("DARK",     "Sidebar / Leisten"),
    ("PANEL",    "Karten"),
    ("PANEL2",   "Karten (dunkel)"),
    ("BORDER",   "Rahmen"),
    ("TEXT",     "Text"),
    ("TEXT_DIM", "Text (gedimmt)"),
    ("GREEN",    "Diagramme"),
    ("ACC",      "Warnfarbe"),
]

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _mix(hex_a: str, hex_b: str, t: float) -> str:
    """Linear zwischen zwei Hex-Farben mischen (t=0 -> a, t=1 -> b)."""
    a = int(hex_a[1:], 16); b = int(hex_b[1:], 16)
    ar, ag, ab_ = (a >> 16) & 255, (a >> 8) & 255, a & 255
    br, bg, bb = (b >> 16) & 255, (b >> 8) & 255, b & 255
    return "#{:02x}{:02x}{:02x}".format(
        round(ar + (br - ar) * t), round(ag + (bg - ag) * t), round(ab_ + (bb - ab_) * t))


def _dark_palette(accent: str, secondary: str | None = None,
                  warn: str = "#ff6b00", oled: bool = False) -> dict:
    """Dunkles Farbset aus einer Akzentfarbe ableiten — moderne, ruhige
    Basis: getoentes Dunkelgrau statt Vollschwarz, neutraler Text; die
    Akzentfarbe toent Flaechen nur leicht (OLED-Preset bleibt bewusst
    echtes Schwarz fuer OLED-Displays)."""
    if oled:
        return {
            "PRI":      accent,
            "BG":       "#000000",
            "DARK":     "#000000",
            "PANEL":    _mix("#0a0a0e", accent, 0.05),
            "PANEL2":   _mix("#0e0e14", accent, 0.05),
            "BORDER":   _mix("#26262e", accent, 0.10),
            "TEXT":     _mix("#eceaf2", accent, 0.08),
            "TEXT_DIM": _mix("#8c8896", accent, 0.10),
            "GREEN":    secondary or accent,
            "ACC":      warn,
        }
    return {
        "PRI":      accent,
        "BG":       _mix("#131118", accent, 0.05),
        "DARK":     _mix("#161420", accent, 0.05),
        "PANEL":    _mix("#1b1826", accent, 0.06),
        "PANEL2":   _mix("#201c2d", accent, 0.06),
        "BORDER":   _mix("#2c2740", accent, 0.10),
        "TEXT":     _mix("#e9e6f2", accent, 0.10),
        "TEXT_DIM": _mix("#8f8aa0", accent, 0.12),
        "GREEN":    secondary or accent,
        "ACC":      warn,
    }


PRESETS: dict[str, dict] = {
    GREEN_PROFILE_NAME: dict(GREEN_COLORS),
    "Emerald":    _dark_palette("#00ff41", "#00ff88"),
    "Cyan":       _dark_palette("#00e5ff", "#18ffff"),
    "Blue":       _dark_palette("#2979ff", "#448aff"),
    "Purple":     _dark_palette("#a855f7", "#c084fc"),
    "Orange":     _dark_palette("#ff8c00", "#ffb74d", warn="#ff3355"),
    "Red":        _dark_palette("#ff3355", "#ff6e7f", warn="#ffcc00"),
    "White":      _dark_palette("#f5f7fa", "#cfd8dc"),
    "Gold":       _dark_palette("#ffd700", "#ffe97a", warn="#ff3355"),
    "Silver":     _dark_palette("#c0c8d0", "#e0e6ea"),
    "Carbon":     _dark_palette("#8a8f98", "#aab2bd"),
    "Matrix":     _dark_palette("#00ff41", "#00cc33", oled=True),
    "Cyber":      _dark_palette("#ff00c8", "#00e5ff"),
    "Dark":       _dark_palette("#7a8aff", "#9aa8ff"),
    "OLED Black": _dark_palette("#00ffaa", "#66ffd0", oled=True),
    "Light": {
        "PRI":      "#0066ff",
        "BG":       "#eef1f5",
        "DARK":     "#e3e7ee",
        "PANEL":    "#f8fafc",
        "PANEL2":   "#ffffff",
        "BORDER":   "#c4ccd8",
        "TEXT":     "#1a2330",
        "TEXT_DIM": "#5a6675",
        "GREEN":    "#00875a",
        "ACC":      "#ff6b00",
    },
}


ACCENT_SWATCHES = [
    "#a855f7", "#2979ff", "#00e5ff", "#00ff41", "#ffd700",
    "#ff8c00", "#ff3355", "#ff00c8", "#f5f7fa",
]


BAR_PRESETS: dict[str, str] = {
    "DEFAULT": DEFAULT_PROFILE_NAME,
    "DARK":    "Dark",
    "OLED":    "OLED Black",
    "LIGHT":   "Light",
    "CYBER":   "Cyber",
    "MINIMAL": "Carbon",
}


DEFAULT_SETTINGS = {
    "glow_effects": True,
    "animations": True,
    "transparency_pct": 100,
}
MIN_TRANSPARENCY = 20


def get_settings() -> dict:
    """Glow/Animations/Transparenz — immer vollstaendig mit Defaults."""
    data = _read_file()
    s = dict(DEFAULT_SETTINGS)
    stored = data.get("settings")
    if isinstance(stored, dict):
        if isinstance(stored.get("glow_effects"), bool):
            s["glow_effects"] = stored["glow_effects"]
        if isinstance(stored.get("animations"), bool):
            s["animations"] = stored["animations"]
        pct = stored.get("transparency_pct")
        if isinstance(pct, (int, float)):
            s["transparency_pct"] = max(MIN_TRANSPARENCY, min(100, int(pct)))
    return s


def save_settings(settings: dict) -> None:
    data = _read_file()
    merged = get_settings()
    merged.update({k: v for k, v in settings.items() if k in DEFAULT_SETTINGS})
    merged["transparency_pct"] = max(MIN_TRANSPARENCY,
                                     min(100, int(merged["transparency_pct"])))
    data["settings"] = merged
    _write_file(data)


def get_custom_swatches() -> list[str]:
    data = _read_file()
    out = []
    for v in data.get("custom_swatches", []):
        if isinstance(v, str) and _HEX_RE.match(v.strip()):
            out.append(v.strip().lower())
    return out[:12]


def add_custom_swatch(hex_color: str) -> None:
    hex_color = hex_color.strip().lower()
    if not _HEX_RE.match(hex_color):
        return
    data = _read_file()
    swatches = [v for v in data.get("custom_swatches", []) if v != hex_color]
    swatches.append(hex_color)
    data["custom_swatches"] = swatches[-12:]
    _write_file(data)


def _read_file() -> dict:
    try:
        data = json.loads(THEME_FILE.read_text(encoding="utf-8"))
        if not (isinstance(data, dict) and isinstance(data.get("profiles"), dict)):
            raise ValueError
    except Exception:
        data = {"active": DEFAULT_PROFILE_NAME,
                "profiles": {DEFAULT_PROFILE_NAME: dict(DEFAULT_COLORS)}}


    for name, colors in PRESETS.items():
        data["profiles"].setdefault(name, dict(colors))
    return data


def _write_file(data: dict) -> None:
    THEME_FILE.parent.mkdir(parents=True, exist_ok=True)
    THEME_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                          encoding="utf-8")


def _sanitize(colors: dict) -> dict:
    """Nur bekannte Keys mit gueltigen #rrggbb-Werten durchlassen."""
    out = {}
    for key, _label in EDITABLE_KEYS:
        v = colors.get(key)
        if isinstance(v, str) and _HEX_RE.match(v.strip()):
            out[key] = v.strip().lower()
    return out


def list_profiles() -> list[str]:
    return sorted(_read_file()["profiles"].keys())


def active_profile_name() -> str:
    data = _read_file()
    name = data.get("active", DEFAULT_PROFILE_NAME)
    return name if name in data["profiles"] else DEFAULT_PROFILE_NAME


def get_active_colors() -> dict:
    """Vollstaendiges Farbset des aktiven Profils (Defaults + Overrides)."""
    data = _read_file()
    profile = data["profiles"].get(active_profile_name(), {})
    colors = dict(DEFAULT_COLORS)
    colors.update(_sanitize(profile))
    return colors


def save_profile(name: str, colors: dict, make_active: bool = True) -> None:
    name = name.strip()
    if not name:
        raise ValueError("Profilname darf nicht leer sein")
    data = _read_file()
    data["profiles"][name] = _sanitize(colors)
    if make_active:
        data["active"] = name
    _write_file(data)


def set_active(name: str) -> None:
    data = _read_file()
    if name not in data["profiles"]:
        raise KeyError(name)
    data["active"] = name
    _write_file(data)


def delete_profile(name: str) -> None:
    data = _read_file()
    if name == DEFAULT_PROFILE_NAME:
        return
    data["profiles"].pop(name, None)
    if data.get("active") == name:
        data["active"] = DEFAULT_PROFILE_NAME
        data["profiles"].setdefault(DEFAULT_PROFILE_NAME, dict(DEFAULT_COLORS))
    _write_file(data)


def apply_to_palette(c_class) -> None:
    """Ueberschreibt die Attribute der ui.C-Farbklasse mit dem aktiven Profil.

    Muss VOR dem Bau der Widgets aufgerufen werden, da viele Stylesheets die
    Farben zur Konstruktionszeit einbetten (f-Strings).
    """
    for key, value in get_active_colors().items():
        setattr(c_class, key, value)
