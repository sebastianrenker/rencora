# -*- mode: python ; coding: utf-8 -*-
import sys
from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

# ── Pakete, deren komplette Submodule/Daten mitgepackt werden müssen ───────
# HINWEIS: "google.generativeai" wurde entfernt - keine Datei importiert es.
# "mediapipe" ist seit der Gestensteuerung (actions/gesture_control.py)
# wieder ECHT in Benutzung und muss samt seiner Modell-Dateien mit rein.
# Die dicken optionalen Abhaengigkeiten (torch, tensorflow, ...) bleiben
# trotzdem draussen - siehe _excludes unten; mediapipe braucht sie fuer
# reines Hand-Tracking nicht.
_collect_packages = [
    "google.genai",
    "uvicorn",
    "cv2",
    "mediapipe",
    "renker_core_authz",
]

# ── Pakete, die NIE gebraucht werden und den Build unnötig aufblähen,
#    falls sie irgendwo transitiv als optionale Abhaengigkeit auftauchen ───
_excludes = [
    "torch", "torchvision", "torchaudio",
    "tensorflow",
    "sklearn", "scipy",
    "spacy", "thinc",
    "lightning",
    "matplotlib",
    "pandas",
    "jax", "jaxlib",
    "google.genai.tests",
    "mediapipe.tasks.python.test",
    "mediapipe.tasks.python.benchmark",
]

datas = []
binaries = []
hiddenimports = []

for pkg in _collect_packages:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

hiddenimports += collect_submodules("actions")
hiddenimports += collect_submodules("agents")
hiddenimports += collect_submodules("core")

# Windows-spezifische Pakete werden nur unter Windows gebraucht/gefunden.
if sys.platform == "win32":
    hiddenimports += [
        "comtypes",
        "comtypes.stream",
        "pycaw",
        "pycaw.pycaw",
        "win10toast",
        "pywinauto",
        "win32com",
        "win32com.client",
        "winrt",
    ]

# ── Laufzeitdaten, die main.py / dashboard / actions relativ zu BASE_DIR
#    bzw. sys.executable erwarten ──────────────────────────────────────────
datas += [
    ("face.png",                 "."),
    ("renker_logo.png",          "."),
    ("renker_logo_r.png",        "."),
    ("assets/earth_texture.jpg", "assets"),
    ("assets/fonts",             "assets/fonts"),
    ("assets/icons",             "assets/icons"),
    ("core/prompt.txt",          "core"),
    ("core/lore.txt",            "core"),
    ("config_example",           "config_example"),
    ("dashboard/static",         "dashboard/static"),
    ("database/schema.sql",      "database"),
]

# cloudflared.exe separat als Binary einbinden (kein Python-DLL, aber eine
# ausführbare Datei, die als externer Prozess gestartet wird)
binaries += [
    ("bin/cloudflared.exe", "bin"),
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=_excludes,
    noarchive=False,
    optimize=0,
    cipher=block_cipher,
)
pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='RENCORA',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='rencora.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='RENCORA',
)
