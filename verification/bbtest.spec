# -*- mode: python ; coding: utf-8 -*-
import os

from PyInstaller.utils.hooks import collect_all

RENCORA_ROOT = os.path.dirname(SPECPATH)
SCRIPT = os.path.join(SPECPATH, "bbtest_cli.py")

datas = []
binaries = []
hiddenimports = ["actions.file_controller", "core.renker_guard"]

d, b, h = collect_all("renker_core_authz")
datas += d
binaries += b
hiddenimports += h

_excludes = [
    "torch", "torchvision", "torchaudio", "tensorflow",
    "cv2", "mediapipe", "PyQt6", "PySide6",
    "google", "google.genai", "numpy", "pandas", "matplotlib",
    "uvicorn", "fastapi", "scipy", "sklearn",
]

a = Analysis(
    [SCRIPT],
    pathex=[RENCORA_ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=_excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="rencora_guard_bb",
    console=True,
    disable_windowed_traceback=False,
    upx=False,
)
