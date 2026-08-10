"""Windows DPAPI (CryptProtectData/CryptUnprotectData) fuer Secrets im Ruhezustand.

Geschuetzte Daten sind an das Windows-Benutzerkonto gebunden: ein kopierter Blob
laesst sich auf einem anderen Rechner oder unter einem anderen Konto nicht
entschluesseln. Auf Nicht-Windows-Systemen ist DPAPI nicht verfuegbar.
"""

import ctypes
import sys
from ctypes import wintypes

_AVAILABLE = sys.platform == "win32"

if _AVAILABLE:
    class _BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    _crypt32 = ctypes.windll.crypt32
    _kernel32 = ctypes.windll.kernel32
    _CRYPTPROTECT_UI_FORBIDDEN = 0x01

    def _to_blob(data: bytes) -> _BLOB:
        buf = ctypes.create_string_buffer(data, len(data))
        return _BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))

    def _from_blob(blob: _BLOB) -> bytes:
        out = ctypes.string_at(blob.pbData, blob.cbData)
        _kernel32.LocalFree(blob.pbData)
        return out

    def _call(fn, data: bytes) -> bytes:
        src, dst = _to_blob(data), _BLOB()
        if not fn(ctypes.byref(src), None, None, None, None,
                  _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(dst)):
            raise OSError(f"DPAPI-Aufruf fehlgeschlagen: {ctypes.GetLastError()}")
        return _from_blob(dst)


def available() -> bool:
    return _AVAILABLE


def protect(data: bytes) -> bytes:
    if not _AVAILABLE:
        raise OSError("DPAPI ist nur unter Windows verfuegbar")
    return _call(_crypt32.CryptProtectData, data)


def unprotect(data: bytes) -> bytes:
    if not _AVAILABLE:
        raise OSError("DPAPI ist nur unter Windows verfuegbar")
    return _call(_crypt32.CryptUnprotectData, data)
