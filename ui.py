from __future__ import annotations

import json
import math
import os
import platform
import random
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil


_WIN_NO_WINDOW: dict = (
    {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
)

from PyQt6.QtCore import (
    QEasingCurve, QMimeData, QObject, QPointF, QRectF, QSize, Qt,
    QTimer, QUrl, pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush, QColor, QDragEnterEvent, QDropEvent, QFont, QFontDatabase,
    QFontMetrics, QKeySequence, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
    QRadialGradient, QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QStackedWidget,
    QTextEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget, QProgressBar,
)

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent

BASE_DIR   = _base_dir()
CONFIG_DIR = BASE_DIR / "config"
API_FILE   = CONFIG_DIR / "api_keys.json"

_DEFAULT_W, _DEFAULT_H = 980, 700
_MIN_W,     _MIN_H     = 820, 580
_LEFT_W  = 148
_RIGHT_W = 340

_OS = platform.system()


class C:


    BG        = "#131019"
    PANEL     = "#1b1726"
    PANEL2    = "#201b2e"
    BORDER    = "#2b2440"
    BORDER_B  = "#3a3154"
    BORDER_A  = "#322a48"
    PRI       = "#8a2be2"
    PRI_DIM   = "#6b4f9e"
    PRI_GHO   = "#241d36"
    ACC       = "#ff6b00"
    ACC2      = "#ffcc00"
    GREEN     = "#b980ff"
    GREEN_D   = "#8f6fd0"
    RED       = "#ff3355"
    MUTED_C   = "#ff3366"
    TEXT      = "#e8e4f2"
    TEXT_DIM  = "#8f87a3"
    TEXT_MED  = "#b9b2cc"
    WHITE     = "#f5f3fa"
    DARK      = "#161320"
    BAR_BG    = "#1b1726"


try:
    from core import theme_manager as _theme_manager
    _theme_manager.apply_to_palette(C)
except Exception:
    _theme_manager = None


FONT_DISPLAY = "Rajdhani"
FONT_BODY    = "Rajdhani"

_fonts_loaded = False


_svg_icon_cache: dict = {}


def svg_icon(name: str, color: str, size: int) -> QPixmap | None:
    """Lucide-Outline-Icon (assets/icons/<name>.svg) in gewuenschter Farbe
    und Groesse rendern — gecacht. None, wenn Datei/QtSvg fehlt."""
    key = (name, color, size)
    if key in _svg_icon_cache:
        return _svg_icon_cache[key]
    pm = None
    try:
        from PyQt6.QtSvg import QSvgRenderer
        from PyQt6.QtCore import QByteArray
        bases = ([Path(sys._MEIPASS)] if getattr(sys, "_MEIPASS", None) else []) + [BASE_DIR]
        for base in bases:
            path = base / "assets" / "icons" / f"{name}.svg"
            if path.exists():
                txt = path.read_text(encoding="utf-8").replace("currentColor", color)
                renderer = QSvgRenderer(QByteArray(txt.encode("utf-8")))
                pm = QPixmap(size, size)
                pm.fill(Qt.GlobalColor.transparent)
                painter = QPainter(pm)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                renderer.render(painter)
                painter.end()
                break
    except Exception:
        pm = None
    _svg_icon_cache[key] = pm
    return pm


def ensure_fonts_loaded() -> None:
    global _fonts_loaded
    if _fonts_loaded:
        return
    _fonts_loaded = True
    bases = ([Path(sys._MEIPASS)] if getattr(sys, "_MEIPASS", None) else []) + [BASE_DIR]
    for base in bases:
        fdir = base / "assets" / "fonts"
        if not fdir.is_dir():
            continue
        for ttf in sorted(fdir.glob("*.ttf")):
            try:
                QFontDatabase.addApplicationFont(str(ttf))
            except Exception:
                pass
        break


def qcol(h: str, a: int = 255) -> QColor:
    c = QColor(h); c.setAlpha(a); return c


PANEL_ALPHA = 255


def set_panel_alpha(pct: int) -> None:
    global PANEL_ALPHA
    PANEL_ALPHA = max(51, min(255, int(255 * pct / 100)))


def rgba(hex_color: str, alpha: int | None = None) -> str:
    """Stylesheet-taugliches rgba() aus Hex + (Panel-)Alpha."""
    a = PANEL_ALPHA if alpha is None else alpha
    c = QColor(hex_color)
    return f"rgba({c.red()},{c.green()},{c.blue()},{a})"

class _SysMetrics:
    def __init__(self):
        self.cpu  = 0.0
        self.mem  = 0.0
        self.net  = 0.0
        self.gpu  = -1.0
        self.tmp  = -1.0
        self._lock = threading.Lock()
        self._last_net = psutil.net_io_counters()
        self._last_net_t = time.time()
        self._running = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def _loop(self):
        while self._running:
            try:
                self._update()
            except Exception:
                pass
            time.sleep(1.5)

    def _update(self):
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent

        nc  = psutil.net_io_counters()
        now = time.time()
        dt  = now - self._last_net_t
        if dt > 0:
            sent = (nc.bytes_sent - self._last_net.bytes_sent) / dt
            recv = (nc.bytes_recv - self._last_net.bytes_recv) / dt
            net  = (sent + recv) / (1024 * 1024)
        else:
            net = 0.0
        self._last_net   = nc
        self._last_net_t = now

        gpu = self._get_gpu()

        tmp = self._get_temp()

        with self._lock:
            self.cpu = cpu
            self.mem = mem
            self.net = net
            self.gpu = gpu
            self.tmp = tmp

    def _get_gpu(self) -> float:

        try:
            r = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=2, **_WIN_NO_WINDOW
            )
            if r.returncode == 0:
                vals = [float(v.strip()) for v in r.stdout.strip().split("\n") if v.strip()]
                if vals:
                    return sum(vals) / len(vals)
        except Exception:
            pass


        if _OS == "Linux":
            try:
                r = subprocess.run(
                    ["rocm-smi", "--showuse", "--csv"],
                    capture_output=True, text=True, timeout=2, **_WIN_NO_WINDOW
                )
                if r.returncode == 0:
                    for line in r.stdout.strip().split("\n"):
                        parts = line.split(",")
                        if len(parts) >= 2:
                            try:
                                return float(parts[1].strip().replace("%", ""))
                            except ValueError:
                                pass
            except Exception:
                pass


            try:
                r = subprocess.run(
                    ["intel_gpu_top", "-J", "-s", "500"],
                    capture_output=True, text=True, timeout=1, **_WIN_NO_WINDOW
                )
                if r.returncode == 0 and "Render/3D" in r.stdout:
                    import re
                    m = re.search(r'"busy":\s*([\d.]+)', r.stdout)
                    if m:
                        return float(m.group(1))
            except Exception:
                pass


        if _OS == "Darwin":
            try:
                r = subprocess.run(
                    ["sudo", "-n", "powermetrics", "-n", "1", "-i", "500",
                     "--samplers", "gpu_power"],
                    capture_output=True, text=True, timeout=2, **_WIN_NO_WINDOW
                )
                if r.returncode == 0 and "GPU" in r.stdout:
                    import re
                    m = re.search(r'GPU\s+Active:\s+([\d.]+)%', r.stdout)
                    if m:
                        return float(m.group(1))
            except Exception:
                pass

        return -1.0

    def _get_temp(self) -> float:
        try:
            temps = psutil.sensors_temperatures()
            candidates = ["coretemp", "k10temp", "cpu_thermal", "acpitz",
                          "cpu-thermal", "zenpower", "it8688"]
            for name in candidates:
                if name in temps:
                    entries = temps[name]
                    if entries:
                        return entries[0].current
            for entries in temps.values():
                if entries:
                    return entries[0].current
        except Exception:
            pass
        if _OS == "Darwin":
            try:
                r = subprocess.run(
                    ["osx-cpu-temp"], capture_output=True, text=True, timeout=2, **_WIN_NO_WINDOW
                )
                if r.returncode == 0:
                    import re
                    m = re.search(r"([\d.]+)", r.stdout)
                    if m:
                        return float(m.group(1))
            except Exception:
                pass

        if _OS == "Windows":
            try:
                r = subprocess.run(
                    ["powershell", "-Command",
                     "(Get-WmiObject MSAcpi_ThermalZoneTemperature -Namespace root/wmi).CurrentTemperature"],
                    capture_output=True, text=True, timeout=3, **_WIN_NO_WINDOW
                )
                if r.returncode == 0 and r.stdout.strip():
                    raw = float(r.stdout.strip().split("\n")[0])
                    return (raw / 10.0) - 273.15
            except Exception:
                pass

        return -1.0

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "cpu": self.cpu,
                "mem": self.mem,
                "net": self.net,
                "gpu": self.gpu,
                "tmp": self.tmp,
            }


_metrics = _SysMetrics()

class HudCanvas(QWidget):
    def __init__(self, face_path: str, parent=None, use_logo: bool = True):
        super().__init__(parent)
        self.setMinimumSize(300, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.muted    = False
        self.speaking = False
        self.state    = "INITIALISING"


        self.use_logo = use_logo

        self._tick       = 0
        self._scale      = 1.0
        self._tgt_scale  = 1.0
        self._halo       = 55.0
        self._tgt_halo   = 55.0
        self._last_t     = time.time()
        self._scan       = 0.0
        self._scan2      = 180.0
        self._rings      = [0.0, 120.0, 240.0]
        self._pulses: list[float] = [0.0, 50.0, 100.0]
        self._blink      = True
        self._blink_tick = 0
        self._particles: list[list[float]] = []
        self._face_px: QPixmap | None = None
        self._load_face(face_path)


        self.glow_enabled = True
        self.animations_enabled = True
        if _theme_manager is not None:
            try:
                s = _theme_manager.get_settings()
                self.glow_enabled = s["glow_effects"]
                self.animations_enabled = s["animations"]
            except Exception:
                pass

        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        if self.animations_enabled:
            self._tmr.start(16)

    def set_glow_enabled(self, on: bool) -> None:
        self.glow_enabled = on
        self.update()

    def set_animations_enabled(self, on: bool) -> None:
        """Aus = Timer stoppen; das Canvas friert im aktuellen Zustand ein
        (statisches Rendering), statt weiter 60x/s neu zu zeichnen."""
        self.animations_enabled = on
        if on and not self._tmr.isActive():
            self._tmr.start(16)
        elif not on and self._tmr.isActive():
            self._tmr.stop()
        self.update()

    def _load_face(self, path: str):
        self._face_load_error: str | None = None
        candidates = [path]

        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            candidates.append(os.path.join(script_dir, os.path.basename(path)))
        except Exception:
            pass

        src_path = next((c for c in candidates if c and os.path.isfile(c)), None)
        if src_path is None:
            self._face_load_error = f"face image not found (looked at: {', '.join(candidates)})"
            self._face_px = None
            return


        try:
            from PIL import Image, ImageDraw
            import io
            img = Image.open(src_path).convert("RGBA")
            sz  = min(img.size)
            img = img.resize((sz, sz), Image.LANCZOS)
            mk  = Image.new("L", (sz, sz), 0)
            ImageDraw.Draw(mk).ellipse((2, 2, sz - 2, sz - 2), fill=255)
            img.putalpha(mk)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            px = QPixmap(); px.loadFromData(buf.getvalue())
            if px.isNull():
                raise ValueError("decoded pixmap is null")
            self._face_px = px
            return
        except ImportError:
            pass
        except Exception as e:
            self._face_load_error = f"PIL face load failed: {e}"

        try:
            raw = QPixmap(src_path)
            if raw.isNull():
                raise ValueError("QPixmap failed to load file")
            sz = min(raw.width(), raw.height())
            raw = raw.copy(
                (raw.width() - sz) // 2, (raw.height() - sz) // 2, sz, sz
            )
            circular = QPixmap(sz, sz)
            circular.fill(Qt.GlobalColor.transparent)
            cp = QPainter(circular)
            cp.setRenderHint(QPainter.RenderHint.Antialiasing)
            clip = QPainterPath()
            clip.addEllipse(0, 0, sz, sz)
            cp.setClipPath(clip)
            cp.drawPixmap(0, 0, raw)
            cp.end()
            self._face_px = circular
            self._face_load_error = None
        except Exception as e:
            self._face_load_error = f"face image load failed: {e}"
            self._face_px = None

    def _step(self):
        self._tick += 1
        now = time.time()
        if now - self._last_t > (0.12 if self.speaking else 0.5):
            if self.speaking:
                self._tgt_scale = random.uniform(1.06, 1.14)
                self._tgt_halo  = random.uniform(145, 190)
            elif self.muted:
                self._tgt_scale = random.uniform(0.998, 1.002)
                self._tgt_halo  = random.uniform(15, 28)
            else:
                self._tgt_scale = random.uniform(1.001, 1.008)
                self._tgt_halo  = random.uniform(48, 68)
            self._last_t = now

        sp = 0.38 if self.speaking else 0.15
        self._scale += (self._tgt_scale - self._scale) * sp
        self._halo  += (self._tgt_halo  - self._halo)  * sp

        speeds = [1.3, -0.9, 2.0] if self.speaking else [0.55, -0.35, 0.9]
        for i, spd in enumerate(speeds):
            self._rings[i] = (self._rings[i] + spd) % 360

        self._scan  = (self._scan  + (3.0 if self.speaking else 1.3)) % 360
        self._scan2 = (self._scan2 + (-2.0 if self.speaking else -0.75)) % 360

        fw  = min(self.width(), self.height())
        lim = fw * 0.74
        spd = 4.2 if self.speaking else 2.0
        self._pulses = [r + spd for r in self._pulses if r + spd < lim]
        if len(self._pulses) < 3 and random.random() < (0.07 if self.speaking else 0.025):
            self._pulses.append(0.0)

        if self.speaking and random.random() < 0.28:
            cx, cy = self.width() / 2, self.height() / 2
            ang = random.uniform(0, 2 * math.pi)
            r_s = fw * 0.28
            self._particles.append([
                cx + math.cos(ang) * r_s, cy + math.sin(ang) * r_s,
                math.cos(ang) * random.uniform(0.9, 2.4),
                math.sin(ang) * random.uniform(0.9, 2.4) - 0.4, 1.0,
            ])
        self._particles = [
            [p[0]+p[2], p[1]+p[3], p[2]*0.97, p[3]*0.97, p[4]-0.028]
            for p in self._particles if p[4] > 0
        ]

        self._blink_tick += 1
        if self._blink_tick >= 38:
            self._blink = not self._blink
            self._blink_tick = 0


        self._globe_phase = getattr(self, "_globe_phase", 0.0) + 0.016
        now = time.time()
        if now - getattr(self, "_globe_last_calc", 0.0) >= 0.12:
            self._globe_last_calc = now
            self._globe_lon = 10.0 + 9.0 * math.sin(self._globe_phase * 0.35)

        self.update()

    def _atmosphere_layer(self, W: int, H: int) -> QPixmap:
        """Hintergrund-Atmosphaere wie im Referenzbild: weiches radiales
        Gluehen von der Mitte, sehr feines Gitter, verstreute Partikel-
        Lichtpunkte. Einmalig berechnet und gecacht (Groesse+Akzent)."""
        key = (W, H, C.PRI, PANEL_ALPHA)
        if getattr(self, "_atmo_key", None) == key:
            return self._atmo_px
        from PyQt6.QtGui import QRadialGradient
        pm = QPixmap(W, H)
        pm.fill(Qt.GlobalColor.transparent)
        ap = QPainter(pm)
        ap.setRenderHint(QPainter.RenderHint.Antialiasing)


        ap.fillRect(0, 0, W, H, qcol(C.BG, PANEL_ALPHA))


        grad = QRadialGradient(W / 2, H / 2, max(W, H) * 0.62)
        grad.setColorAt(0.0, qcol(C.PRI, 34))
        grad.setColorAt(0.45, qcol(C.PRI, 12))
        grad.setColorAt(1.0, qcol(C.PRI, 0))
        ap.setPen(Qt.PenStyle.NoPen)
        ap.setBrush(QBrush(grad))
        ap.drawRect(0, 0, W, H)


        ap.setPen(QPen(qcol(C.PRI, 10), 1))
        for gx in range(0, W, 44):
            ap.drawLine(gx, 0, gx, H)
        for gy in range(0, H, 44):
            ap.drawLine(0, gy, W, gy)


        rng = random.Random(W * 7919 + H)
        for _ in range(int(W * H / 9000)):
            px_, py_ = rng.uniform(0, W), rng.uniform(0, H)
            r = rng.uniform(0.6, 1.8)
            a = rng.randint(28, 90)
            ap.setPen(Qt.PenStyle.NoPen)
            ap.setBrush(QBrush(qcol(C.PRI if rng.random() < 0.75 else "#ffffff", a)))
            ap.drawEllipse(QPointF(px_, py_), r, r)
        ap.end()
        self._atmo_px = pm
        self._atmo_key = key
        return pm

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.drawPixmap(0, 0, self._atmosphere_layer(self.width(), self.height()))

        W, H  = self.width(), self.height()
        cx, cy = W / 2, H / 2
        fw    = min(W, H)
        pri   = qcol(C.MUTED_C if self.muted else C.PRI)
        ha    = max(0, min(255, int(self._halo)))


        for pr in self._pulses:
            a   = max(0, int(200 * (1.0 - pr / (fw * 0.74))))
            p.setPen(QPen(qcol(C.MUTED_C if self.muted else C.PRI, a), 1.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(cx - pr, cy - pr, pr * 2, pr * 2))


        for idx, (r_frac, w_r, arc_l, gap) in enumerate(
            [(0.46, 3.8, 100, 70), (0.38, 2.6, 65, 50)]
        ):
            ring_r = fw * r_frac
            base   = self._rings[idx]
            a_val  = max(70, min(255, int(ha * (1.05 - idx * 0.2)) + 50))
            p.setPen(QPen(qcol(C.MUTED_C if self.muted else C.PRI, a_val), w_r))
            p.setBrush(Qt.BrushStyle.NoBrush)
            angle = base
            rect  = QRectF(cx - ring_r, cy - ring_r, ring_r * 2, ring_r * 2)
            while angle < base + 360:
                p.drawArc(rect, int(angle * 16), int(arc_l * 16))
                angle += arc_l + gap


        sr    = fw * 0.48
        sa    = min(255, int(ha * 1.4))
        ex    = 80 if self.speaking else 48
        p.setPen(QPen(qcol(C.MUTED_C if self.muted else C.PRI, sa), 2.8))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(cx-sr, cy-sr, sr*2, sr*2), int(self._scan*16), int(ex*16))


        if self.use_logo:
            self._paint_globe(p, cx, cy, fw)


        if self.use_logo:
            self._paint_solid_double_ring(p, cx, cy, fw, ha)


        if self.use_logo:

            self._paint_center_logo(p, cx, cy, fw, ha)
        elif self._face_px is not None:

            port_d = fw * 0.62 * (self._scale * 0.18 + 0.91)
            port_x = cx - port_d / 2
            port_y = cy - port_d / 2 - fw * 0.02

            glow_col = C.MUTED_C if self.muted else C.PRI
            for gi in range(7):
                gr = 3 + gi * 4
                ga = max(0, int(ha * 0.07 * (1 - gi / 7)))
                p.setPen(QPen(qcol(glow_col, ga), gr))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(QRectF(port_x - gr, port_y - gr,
                                      port_d + gr * 2, port_d + gr * 2))

            path = QPainterPath()
            path.addEllipse(QRectF(port_x, port_y, port_d, port_d))
            p.save()
            p.setClipPath(path)
            p.drawPixmap(QRectF(port_x, port_y, port_d, port_d).toRect(),
                         self._face_px)
            if self.muted:
                p.fillRect(QRectF(port_x, port_y, port_d, port_d),
                           QColor(60, 0, 0, 70))
            p.restore()

            p.setPen(QPen(qcol(glow_col, min(255, ha + 90)), 2.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(port_x, port_y, port_d, port_d))
        else:

            head_w = fw * 0.38
            head_h = fw * 0.46

            head_top  = cy - fw * 0.30
            head_bot  = head_top + head_h
            neck_w    = fw * 0.13
            neck_h    = fw * 0.07
            shldr_w   = fw * 0.44
            shldr_h   = fw * 0.07

            col_line  = qcol(C.MUTED_C if self.muted else C.PRI, min(255, ha + 80))
            col_fill  = QColor(0, int(20 * (ha/255)), 0, 60)
            col_glow  = qcol(C.MUTED_C if self.muted else C.PRI, max(0, ha - 60))


            for gi in range(6):
                gr = 4 + gi * 5
                ga = max(0, int(ha * 0.06 * (1 - gi/6)))
                p.setPen(QPen(qcol(C.MUTED_C if self.muted else C.PRI, ga), gr))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(
                    QRectF(cx - head_w/2 - gr, head_top - gr,
                           head_w + gr*2, head_h + gr*2),
                    head_w * 0.38 + gr, head_w * 0.38 + gr
                )


            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(col_fill))
            p.drawRoundedRect(
                QRectF(cx - head_w/2, head_top, head_w, head_h),
                head_w * 0.38, head_w * 0.38
            )


            p.setPen(QPen(col_line, 2.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(
                QRectF(cx - head_w/2, head_top, head_w, head_h),
                head_w * 0.38, head_w * 0.38
            )


            vis_y  = head_top + head_h * 0.30
            vis_h  = head_h  * 0.18
            vis_x  = cx - head_w * 0.36
            vis_w  = head_w * 0.72
            visor_fill = QColor(0, int(40*(ha/255)), 0, 110)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(visor_fill))
            p.drawRoundedRect(QRectF(vis_x, vis_y, vis_w, vis_h), vis_h*0.45, vis_h*0.45)

            p.setPen(QPen(col_line, 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(vis_x, vis_y, vis_w, vis_h), vis_h*0.45, vis_h*0.45)


            scan_frac = (self._scan % 360) / 360.0
            sx = vis_x + scan_frac * vis_w
            sl_col = qcol(C.PRI, min(255, int(ha * 1.6)))
            p.setPen(QPen(sl_col, 1.5))
            p.drawLine(QPointF(sx, vis_y + 2), QPointF(sx, vis_y + vis_h - 2))


            chin_y = head_top + head_h * 0.78
            p.setPen(QPen(col_glow, 1))
            p.drawLine(QPointF(cx - head_w*0.25, chin_y),
                       QPointF(cx + head_w*0.25, chin_y))


            neck_x = cx - neck_w/2
            neck_y = head_bot - 2
            p.setPen(QPen(col_line, 1.8))
            p.setBrush(QBrush(col_fill))
            p.drawRect(QRectF(neck_x, neck_y, neck_w, neck_h))


            shldr_y = neck_y + neck_h
            shldr_x = cx - shldr_w/2

            shldr_path_fill = QColor(0, int(15*(ha/255)), 0, 55)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(shldr_path_fill))
            p.drawRoundedRect(QRectF(shldr_x, shldr_y, shldr_w, shldr_h), shldr_h*0.5, shldr_h*0.5)

            p.setPen(QPen(col_line, 2.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(shldr_x, shldr_y, shldr_w, shldr_h), shldr_h*0.5, shldr_h*0.5)


        t_out, t_in = fw * 0.485, fw * 0.465
        p.setPen(QPen(qcol(C.PRI, 110), 1))
        for deg in range(0, 360, 10):
            rad = math.radians(deg)
            inn = t_in if deg % 30 == 0 else t_in + 5
            p.drawLine(
                QPointF(cx + t_out*math.cos(rad), cy - t_out*math.sin(rad)),
                QPointF(cx + inn *math.cos(rad), cy - inn *math.sin(rad)),
            )


        for pt in self._particles:
            a = max(0, min(255, int(pt[4] * 255)))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(qcol(C.PRI, a)))
            p.drawEllipse(QPointF(pt[0], pt[1]), 2.2, 2.2)


        sy = cy + fw * 0.44
        if self.muted:
            stxt, scol = "⊘  MUTED",      qcol(C.MUTED_C)
        elif self.speaking:
            stxt, scol = "●  SPEAKING",   qcol(C.ACC)
        elif self.state == "THINKING":
            sym = "◈" if self._blink else "◇"
            stxt, scol = f"{sym}  THINKING",   qcol(C.ACC2)
        elif self.state == "PROCESSING":
            sym = "▷" if self._blink else "▶"
            stxt, scol = f"{sym}  PROCESSING", qcol(C.ACC2)
        elif self.state == "LISTENING":
            sym = "●" if self._blink else "○"
            stxt, scol = f"{sym}  LISTENING",  qcol(C.GREEN)
        else:
            sym = "●" if self._blink else "○"
            stxt, scol = f"{sym}  {self.state}", qcol(C.PRI)

        p.setPen(QPen(scol, 1))
        p.setFont(QFont(FONT_BODY, 11, QFont.Weight.Bold))
        p.drawText(QRectF(0, sy, W, 26), Qt.AlignmentFlag.AlignCenter, stxt)


        wy = sy + 30
        N, bw = 36, 8
        wx0 = (W - N * bw) / 2
        for i in range(N):
            if self.muted:
                hgt, cl = 2, qcol(C.MUTED_C)
            elif self.speaking:
                hgt = random.randint(3, 20)
                cl  = qcol(C.PRI) if hgt > 12 else qcol(C.PRI_DIM)
            else:
                hgt = int(3 + 2 * math.sin(self._tick * 0.09 + i * 0.6))
                cl  = qcol(C.BORDER_B)
            p.fillRect(QRectF(wx0 + i*bw, wy + 20 - hgt, bw - 1, hgt), cl)


        scan_col = QColor(0, 0, 0, 18)
        sy2 = 0.0
        while sy2 < H:
            p.fillRect(QRectF(0, sy2, W, 1), scan_col)
            sy2 += 3

    def _paint_globe(self, p, cx: float, cy: float, fw: float) -> None:
        """
        Texturierter Erd-Globus (orthografische Projektion, Europa-zentriert)
        als Duotone im aktiven Akzent — gerendert von core/globe_render.py,
        hier nur gecacht angezeigt plus Gradnetz- und Atmosphaeren-Overlay.
        Cache-Schluessel: Groesse, Projektionslaenge (Atem-Rotation), Farben.
        """
        try:
            from core.globe_render import render_globe_rgba, project_point
            from PyQt6.QtGui import QPolygonF
        except Exception:
            return

        radius = fw * 0.275
        size = max(32, int(radius * 2))
        lon0 = getattr(self, "_globe_lon", 10.0) if self.animations_enabled else 10.0
        lat0 = 50.0
        dark = C.BG
        accent = C.MUTED_C if self.muted else C.PRI

        key = (size, round(lon0, 1), dark, accent)
        if getattr(self, "_globe_key", None) != key:
            data = render_globe_rgba(size, lon0, lat0, dark, accent)
            if data is None:
                return
            from PyQt6.QtGui import QImage
            img = QImage(data, size, size, QImage.Format.Format_RGBA8888)
            self._globe_px = QPixmap.fromImage(img.copy())
            self._globe_key = key
        if getattr(self, "_globe_px", None) is None:
            return


        if self.glow_enabled:
            for gi in range(6, 0, -1):
                ga = int(26 * (1 - gi / 7))
                p.setPen(QPen(qcol(accent, ga), 3.0 + gi * 2.6))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(QPointF(cx, cy), radius + gi * 1.2, radius + gi * 1.2)

        p.drawPixmap(int(cx - radius), int(cy - radius), self._globe_px)


        p.setPen(QPen(qcol(accent, 46), 0.8))
        p.setBrush(Qt.BrushStyle.NoBrush)
        for lat_line in range(-60, 90, 30):
            pts = []
            for lon_line in range(-180, 185, 5):
                pt = project_point(lat_line, lon_line, lat0, lon0)
                if pt is None:
                    if len(pts) > 1:
                        p.drawPolyline(QPolygonF(pts))
                    pts = []
                else:
                    pts.append(QPointF(cx + pt[0] * radius, cy + pt[1] * radius))
            if len(pts) > 1:
                p.drawPolyline(QPolygonF(pts))
        for lon_line in range(-180, 180, 30):
            pts = []
            for lat_line in range(-85, 90, 5):
                pt = project_point(lat_line, lon_line, lat0, lon0)
                if pt is None:
                    if len(pts) > 1:
                        p.drawPolyline(QPolygonF(pts))
                    pts = []
                else:
                    pts.append(QPointF(cx + pt[0] * radius, cy + pt[1] * radius))
            if len(pts) > 1:
                p.drawPolyline(QPolygonF(pts))

    def _paint_solid_double_ring(self, p, cx: float, cy: float, fw: float, ha: int) -> None:
        """
        Zeichnet zwei durchgezogene, leuchtende Ringe (Cyan außen, Grün
        innen) um das zentrale Logo, plus 'SYSTEM ONLINE' oben am Ring
        und 'CORE 01' / 'SYS A1' Tags seitlich — siehe Referenz-Dashboard.
        Pulsiert leicht mit dem bestehenden Halo-Wert `ha`, bleibt aber
        auch im Idle-Zustand klar sichtbar (Mindest-Alpha).
        """
        outer_r = fw * 0.335
        inner_r = fw * 0.295
        pulse_alpha = max(90, min(255, ha + 80))
        ring_col = C.MUTED_C if self.muted else C.PRI


        if self.glow_enabled:
            for gi in range(5, 0, -1):
                glow_w = 2.4 + gi * 3.2
                glow_a = max(0, int(pulse_alpha * 0.10 * (1 - gi / 6)))
                p.setPen(QPen(qcol(ring_col, glow_a), glow_w))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(QPointF(cx, cy), outer_r, outer_r)

        p.setPen(QPen(qcol(ring_col, pulse_alpha), 3.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), outer_r, outer_r)
        p.setPen(QPen(qcol(ring_col, int(pulse_alpha * 0.55)), 1.6))
        p.drawEllipse(QPointF(cx, cy), inner_r, inner_r)


        p.setPen(QPen(qcol(ring_col, 40), 1))
        for deg in range(0, 360, 6):
            a = math.radians(deg)
            r1 = outer_r * 1.03
            r2 = outer_r * (1.10 if deg % 30 == 0 else 1.06)
            p.drawLine(QPointF(cx + math.cos(a) * r1, cy + math.sin(a) * r1),
                       QPointF(cx + math.cos(a) * r2, cy + math.sin(a) * r2))


        tri = QPainterPath()
        tri_w = fw * 0.020
        tri_y = cy - outer_r - fw * 0.030
        tri.moveTo(cx - tri_w, tri_y)
        tri.lineTo(cx + tri_w, tri_y)
        tri.lineTo(cx, tri_y + tri_w * 1.5)
        tri.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(qcol(ring_col, 220)))
        p.drawPath(tri)
        from PyQt6.QtGui import QFontMetricsF


        tag_font = QFont(FONT_BODY, max(7, int(fw * 0.014)), QFont.Weight.Bold)
        p.setFont(tag_font)
        tfm = QFontMetricsF(tag_font)
        for tag_text, side in (("CORE\n01", -1), ("SYS\nA1", 1)):
            tag_w = max(tfm.horizontalAdvance(line) for line in tag_text.split("\n")) + 18
            tag_h = tfm.height() * 2 + 10
            tag_x = cx + side * (outer_r + tag_w / 2 + 6)
            tag_rect = QRectF(tag_x - tag_w / 2, cy - tag_h / 2, tag_w, tag_h)
            p.setPen(QPen(qcol(ring_col, 180), 1))
            p.setBrush(QBrush(qcol(C.PANEL2, 220)))
            p.drawRoundedRect(tag_rect, 3, 3)
            p.setPen(QPen(qcol(ring_col, 255), 1))
            p.drawText(tag_rect, Qt.AlignmentFlag.AlignCenter, tag_text)


        info_font = QFont(FONT_BODY, max(6, int(fw * 0.013)))
        p.setFont(info_font)
        ifm = QFontMetricsF(info_font)
        info_x = cx - fw * 0.46
        info_y = cy - fw * 0.40
        for label, value, col in (
            ("LINK:", "ONLINE", ring_col),
            ("ENCRYPTION:", "AES-256", C.TEXT_MED),
            ("DATA FLOW:", "STABLE", C.TEXT_MED),
        ):
            p.setPen(QPen(qcol(C.TEXT_DIM, 220), 1))
            p.drawText(QPointF(info_x, info_y), label)
            p.setPen(QPen(qcol(col, 240), 1))
            p.drawText(QPointF(info_x + ifm.horizontalAdvance(label) + 6, info_y), value)
            info_y += ifm.height() * 1.25


        st_label_font = QFont(FONT_BODY, max(6, int(fw * 0.012)))
        p.setFont(st_label_font)
        p.setPen(QPen(qcol(C.TEXT_DIM, 220), 1))
        st_y = cy + outer_r + fw * 0.045
        p.drawText(QRectF(cx - fw * 0.3, st_y, fw * 0.6, ifm.height()),
                   int(Qt.AlignmentFlag.AlignHCenter), "STATUS")
        st_value_font = QFont(FONT_BODY, max(7, int(fw * 0.016)), QFont.Weight.Bold)
        p.setFont(st_value_font)
        p.setPen(QPen(qcol(ring_col, 255), 1))
        p.drawText(QRectF(cx - fw * 0.3, st_y + ifm.height() * 1.1, fw * 0.6, ifm.height() * 1.6),
                   int(Qt.AlignmentFlag.AlignHCenter),
                   "SYSTEM MUTED" if self.muted else "SYSTEM ONLINE")

    def _paint_center_logo(self, p, cx: float, cy: float, fw: float, ha: int) -> None:
        """
        Zeichnet das echte Renker-Industries-Logo (renker_logo.png, mit
        Alpha-Kanal) zentriert ueber den HUD-Ringen. Faellt auf einen
        schlichten 'RENCORA'-Schriftzug zurueck, wenn die Datei fehlt.
        """
        glow_col = C.MUTED_C if self.muted else C.PRI


        glow_r = fw * 0.30
        for gi in range(6):
            gr = 3 + gi * 5
            ga = max(0, int(ha * 0.05 * (1 - gi / 6)))
            p.setPen(QPen(qcol(glow_col, ga), gr))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(cx, cy), glow_r + gr, glow_r + gr)


        if not hasattr(self, "_center_logo_px"):
            self._center_logo_px = None
            self._center_logo_has_wordmark = False
            bases = ([Path(sys._MEIPASS)] if getattr(sys, "_MEIPASS", None) else []) + [BASE_DIR]
            candidates = [(b / "renker_logo_r.png", False) for b in bases] + \
                         [(b / "renker_logo.png", True) for b in bases]
            for logo_file, has_wordmark in candidates:
                if logo_file.exists():
                    px = QPixmap(str(logo_file))
                    if not px.isNull():
                        self._center_logo_px = px
                        self._center_logo_has_wordmark = has_wordmark
                        break

        if self._center_logo_px is not None:
            px = self._center_logo_px


            from PyQt6.QtGui import QRadialGradient
            lg = QRadialGradient(cx, cy - fw * 0.10, fw * 0.30)
            lg.setColorAt(0.0, qcol(glow_col, 70))
            lg.setColorAt(1.0, qcol(glow_col, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(lg))
            p.drawEllipse(QPointF(cx, cy - fw * 0.10), fw * 0.30, fw * 0.30)

            if self.muted:
                p.setOpacity(0.55)

            if self._center_logo_has_wordmark:

                target_w = fw * 0.52
                target_h = target_w * px.height() / px.width()
                p.drawPixmap(QRectF(cx - target_w / 2, cy - target_h / 2,
                                    target_w, target_h).toRect(), px)
            else:


                logo_w = fw * 0.30
                logo_h = logo_w * px.height() / px.width()
                logo_top = cy - logo_h * 0.80
                p.drawPixmap(QRectF(cx - logo_w / 2, logo_top,
                                    logo_w, logo_h).toRect(), px)

                title_size = max(16, int(fw * 0.060))
                p.setFont(QFont(FONT_DISPLAY, title_size, QFont.Weight.Bold))
                title_y = logo_top + logo_h - title_size * 0.6


                backing = QRectF(cx - fw * 0.30, logo_top - fw * 0.02,
                                 fw * 0.60, (title_y - logo_top) + title_size * 3.6)
                for bi in range(3, 0, -1):
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QBrush(qcol(C.BG, int(60 * bi / 3))))
                    grow = (3 - bi) * 6.0
                    p.drawRoundedRect(backing.adjusted(-grow, -grow, grow, grow), 18, 18)


                halo_rect = QRectF(cx - fw * 0.45, title_y, fw * 0.9, title_size * 2.0)
                p.setPen(QPen(qcol(glow_col, 34), 1))
                for ox, oy in ((-2, 0), (2, 0), (0, -2), (0, 2),
                               (-1, -1), (1, -1), (-1, 1), (1, 1)):
                    p.drawText(halo_rect.translated(ox, oy),
                               int(Qt.AlignmentFlag.AlignHCenter), "RENCORA AI")
                p.setPen(QPen(qcol(C.WHITE, 245), 1))
                p.drawText(halo_rect,
                           int(Qt.AlignmentFlag.AlignHCenter), "RENCORA AI")

                sub_size = max(7, int(fw * 0.018))
                p.setFont(QFont(FONT_BODY, sub_size, QFont.Weight.Bold))
                p.setPen(QPen(qcol(C.TEXT_MED, 220), 1))
                p.drawText(QRectF(cx - fw * 0.45, title_y + title_size * 2.1,
                                  fw * 0.9, sub_size * 2.5),
                           int(Qt.AlignmentFlag.AlignHCenter),
                           "R E N K E R   I N D U S T R I E S")

            p.setOpacity(1.0)
            return


        title_size = max(20, int(fw * 0.085))
        p.setFont(QFont(FONT_BODY, title_size, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.WHITE, 235), 1))
        p.drawText(QRectF(cx - fw * 0.4, cy - title_size, fw * 0.8, title_size * 2),
                   int(Qt.AlignmentFlag.AlignCenter), "RENCORA AI")

def chamfer_path(rect: QRectF, c: float) -> QPainterPath:
    """Octagon-style rect with chamfered (cut) corners, like the reference HUD panels."""
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    c = min(c, w / 2, h / 2)
    path = QPainterPath()
    path.moveTo(x + c, y)
    path.lineTo(x + w - c, y)
    path.lineTo(x + w, y + c)
    path.lineTo(x + w, y + h - c)
    path.lineTo(x + w - c, y + h)
    path.lineTo(x + c, y + h)
    path.lineTo(x, y + h - c)
    path.lineTo(x, y + c)
    path.closeSubpath()
    return path


class SectionHeader(QWidget):
    """Section title with a glowing green bullet, matching the reference HUD style.
    Optional right-aligned badge (e.g. 'LIVE') for sections like ACTIVITY LOG."""

    def __init__(self, text: str, badge: str = "", parent=None):
        super().__init__(parent)
        self._text = text
        self._badge = badge
        self.setFixedHeight(22)

    def set_badge(self, badge: str) -> None:
        self._badge = badge
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        H = self.height()
        cy = H / 2

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(qcol(C.GREEN, 70)))
        p.drawEllipse(QPointF(6, cy), 5, 5)
        p.setBrush(QBrush(qcol(C.GREEN)))
        p.drawEllipse(QPointF(6, cy), 2.6, 2.6)

        p.setFont(QFont(FONT_BODY, 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.TEXT), 1))
        p.drawText(QRectF(16, 0, self.width() - 16, H),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   self._text.upper())

        if self._badge:

            p.setBrush(QBrush(qcol(C.GREEN)))
            p.setPen(Qt.PenStyle.NoPen)
            badge_dot_x = self.width() - 8 - QFontMetrics(p.font()).horizontalAdvance(self._badge) - 10
            p.drawEllipse(QPointF(badge_dot_x, cy), 2.6, 2.6)
            p.setPen(QPen(qcol(C.GREEN), 1))
            p.drawText(
                QRectF(badge_dot_x + 6, 0, self.width() - badge_dot_x, H),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self._badge,
            )


class ChamferFrame(QWidget):
    """A panel with chamfered (cut) corners and a border — wraps a child layout."""

    def __init__(self, border_color: str = C.BORDER, bg: str = C.PANEL,
                 chamfer: float = 8, parent=None):
        super().__init__(parent)
        self._border = border_color
        self._bg     = bg
        self._chamfer = chamfer

        try:
            from PyQt6.QtWidgets import QGraphicsDropShadowEffect
            eff = QGraphicsDropShadowEffect(self)
            eff.setBlurRadius(26)
            eff.setOffset(0, 6)
            eff.setColor(QColor(0, 0, 0, 110))
            self.setGraphicsEffect(eff)
        except Exception:
            pass
        self._inner = QVBoxLayout(self)
        self._inner.setContentsMargins(10, 8, 10, 8)
        self._inner.setSpacing(4)

    def layout_box(self) -> QVBoxLayout:
        return self._inner

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        radius = max(8.0, float(self._chamfer) + 3.0)


        from PyQt6.QtGui import QLinearGradient
        grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        top = QColor(self._bg); top.setAlpha(PANEL_ALPHA)
        bot = QColor(self._bg).darker(126); bot.setAlpha(PANEL_ALPHA)
        grad.setColorAt(0.0, top)
        grad.setColorAt(1.0, bot)
        p.setBrush(QBrush(grad))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect, radius, radius)


        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(qcol(C.PRI, 16), 4.5))
        p.drawRoundedRect(rect, radius, radius)
        p.setPen(QPen(qcol(C.PRI, 34), 2.2))
        p.drawRoundedRect(rect, radius, radius)
        p.setPen(QPen(qcol(C.BORDER_B, 210), 1.0))
        p.drawRoundedRect(rect, radius, radius)


class ChamferButton(QPushButton):
    """Push button with chamfered corners, an icon glyph, and a glow border."""

    def __init__(self, icon: str, text: str, color: str = C.PRI, parent=None):
        super().__init__(parent)
        self._icon  = icon
        self._text  = text
        self._color = color
        self._active = True
        self._hover_t = 0.0
        self._hover_anim = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(34)

    def _animate_hover(self, target: float) -> None:
        """Sanftes Ein-/Ausblenden des Hover-Zustands (140 ms) statt
        hartem Umschalten — ruhige Mikro-Animation."""
        from PyQt6.QtCore import QVariantAnimation, QEasingCurve
        if self._hover_anim is not None:
            self._hover_anim.stop()
        anim = QVariantAnimation(self)
        anim.setStartValue(self._hover_t)
        anim.setEndValue(target)
        anim.setDuration(140)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        def _tick(v):
            self._hover_t = float(v)
            self.update()
        anim.valueChanged.connect(_tick)
        anim.start()
        self._hover_anim = anim

    def enterEvent(self, e):
        self._animate_hover(1.0)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._animate_hover(0.0)
        super().leaveEvent(e)

    def set_active(self, active: bool, color: str | None = None):
        self._active = active
        if color:
            self._color = color
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        rect = QRectF(0.5, 0.5, W - 1, H - 1)

        from PyQt6.QtGui import QLinearGradient
        grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        if self._active:
            hi = qcol(self._color, 30 + int(18 * self._hover_t))
            lo = qcol(self._color, 10 + int(10 * self._hover_t))
        else:
            hi = qcol(C.PANEL, 235)
            lo = QColor(C.PANEL); lo = lo.darker(130); lo.setAlpha(235)
        grad.setColorAt(0.0, hi)
        grad.setColorAt(1.0, lo)
        p.setBrush(QBrush(grad))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect, 9, 9)

        edge = self._color if self._active else C.BORDER_B
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(qcol(edge, 20 + int(20 * self._hover_t)), 4.0))
        p.drawRoundedRect(rect, 9, 9)
        p.setPen(QPen(qcol(edge, 150 + int(60 * self._hover_t)), 1.0))
        p.drawRoundedRect(rect, 9, 9)

        icon_pm = svg_icon(self._icon, self._color if self._active else C.TEXT_DIM, 15) if self._icon else None
        if icon_pm is not None:
            p.drawPixmap(12, int(H / 2 - 7), icon_pm)

        txt_col = qcol(self._color) if self._active else qcol(C.TEXT_DIM)
        p.setFont(QFont(FONT_BODY, 9, QFont.Weight.DemiBold))
        p.setPen(QPen(txt_col, 1))
        label = self._text if icon_pm is not None else (f"{self._icon}  {self._text}" if self._icon else self._text)


        p.drawText(
            self.rect(),
            int(Qt.AlignmentFlag.AlignCenter) | int(Qt.TextFlag.TextWordWrap),
            label,
        )


class StatusStripItem(QWidget):
    """
    Kompaktes, horizontales Statusfeld mit Icon, Label, Wert und Mini-
    Sparkline — für die untere Statusleiste (siehe Referenz-Dashboard:
    NET STATUS / CONNECTION / DATA FLOW / MEMORY / CPU LOAD). Nutzt
    dasselbe Sparkline-Verfahren wie MetricBar, nur platzsparender und
    horizontal statt vertikal angeordnet.
    """

    def __init__(self, icon: str, label: str, color: str = C.PRI, parent=None):
        super().__init__(parent)
        self._icon = icon
        self._label = label
        self._color = color
        self._value_text = "--"
        self._hist: list[float] = []
        self._hist_max = 24
        self.setFixedHeight(40)
        self.setMinimumWidth(150)

    def set_value(self, pct: float, text: str) -> None:
        self._value_text = text
        self._hist.append(max(0.0, min(100.0, pct)))
        if len(self._hist) > self._hist_max:
            self._hist.pop(0)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        pm = svg_icon(self._icon, self._color, 15)
        if pm is not None:
            p.drawPixmap(2, int(H / 2 - 7), pm)
        else:
            p.setFont(QFont(FONT_BODY, 11))
            p.setPen(QPen(qcol(self._color, 230), 1))
            p.drawText(QRectF(0, 0, 22, H), Qt.AlignmentFlag.AlignCenter, self._icon)

        text_x = 26
        p.setFont(QFont(FONT_BODY, 7))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(text_x, 4, 90, 12), Qt.AlignmentFlag.AlignLeft, self._label)

        p.setFont(QFont(FONT_BODY, 9, QFont.Weight.Bold))
        p.setPen(QPen(qcol(self._color, 240), 1))
        p.drawText(QRectF(text_x, 16, 90, 16), Qt.AlignmentFlag.AlignLeft, self._value_text)


        sp_x, sp_y = 120, 8
        sp_w, sp_h = max(0, W - sp_x - 6), H - 16
        if len(self._hist) >= 2 and sp_w > 4:
            n = len(self._hist)
            step = sp_w / max(1, self._hist_max - 1)
            start_x = sp_x + (self._hist_max - n) * step
            pts = [
                QPointF(start_x + i * step, sp_y + sp_h - (v / 100.0) * sp_h)
                for i, v in enumerate(self._hist)
            ]
            p.setPen(QPen(qcol(self._color, 210), 1.3))
            for i in range(len(pts) - 1):
                p.drawLine(pts[i], pts[i + 1])


class GlobalNodeMapWidget(QWidget):
    """
    Kompakte, stilisierte Weltkarte mit pulsierenden Verbindungsknoten —
    passend zur Statusleiste (siehe Referenz-Dashboard: GLOBAL NODE MAP).
    Rein dekorativ als Live-Status-Kachel; für die echte interaktive
    Weltkarte mit Nachrichten pro Land siehe das Remote-Dashboard (/globe),
    erreichbar über den REMOTE CONTROL-Knopf.
    """


    _DOTS = [
        (0.12, 0.28), (0.15, 0.24), (0.18, 0.30), (0.14, 0.34), (0.20, 0.22), (0.22, 0.35),
        (0.22, 0.55), (0.24, 0.62), (0.21, 0.68), (0.25, 0.50),
        (0.46, 0.22), (0.48, 0.18), (0.50, 0.25),
        (0.47, 0.42), (0.49, 0.55), (0.45, 0.62), (0.51, 0.48),
        (0.62, 0.22), (0.68, 0.28), (0.72, 0.24), (0.65, 0.35), (0.70, 0.40), (0.60, 0.30),
        (0.78, 0.62), (0.81, 0.65),
    ]
    _NODES = [(0.16, 0.28), (0.48, 0.22), (0.66, 0.30), (0.49, 0.50), (0.79, 0.63)]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(40)
        self.setMinimumWidth(150)
        self._phase = 0.0
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._tick)
        self._tmr.start(60)

    def _tick(self):
        self._phase += 0.05
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        p.setFont(QFont(FONT_BODY, 7))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(0, 2, 140, 12), Qt.AlignmentFlag.AlignLeft, "GLOBAL NODE MAP")

        map_y, map_h = 14, H - 16
        p.setPen(QPen(qcol(C.PRI, 70), 1))
        for fx, fy in self._DOTS:
            p.drawPoint(QPointF(fx * W, map_y + fy * map_h))

        p.setPen(QPen(qcol(C.PRI, 55), 1))
        for i in range(len(self._NODES) - 1):
            x1, y1 = self._NODES[i]
            x2, y2 = self._NODES[i + 1]
            p.drawLine(
                QPointF(x1 * W, map_y + y1 * map_h),
                QPointF(x2 * W, map_y + y2 * map_h),
            )

        for i, (fx, fy) in enumerate(self._NODES):
            x, y = fx * W, map_y + fy * map_h
            pulse = (math.sin(self._phase + i * 1.3) + 1) / 2
            r = 1.6 + pulse * 1.6
            p.setPen(QPen(qcol(C.GREEN, int(180 + pulse * 60)), 1.2))
            p.setBrush(QBrush(qcol(C.GREEN, int(140 + pulse * 90))))
            p.drawEllipse(QPointF(x, y), r, r)


class TempGaugeItem(QWidget):
    """AI CORE TEMP als rundes Halbkreis-Gauge mit Skala 0-100 °C und
    Zeiger (Referenz-Dashboard, unterste Kachelreihe) — gleiche set_value-
    Schnittstelle wie StatusStripItem."""

    def __init__(self, label: str = "AI CORE TEMP", color: str = C.ACC2, parent=None):
        super().__init__(parent)
        self._label = label
        self._color = color
        self._value_text = "--"
        self._pct = 0.0
        self.setFixedHeight(40)
        self.setMinimumWidth(150)

    def set_value(self, pct: float, text: str) -> None:
        self._pct = max(0.0, min(100.0, pct))
        self._value_text = text
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        p.setFont(QFont(FONT_BODY, 7))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(0, 2, 110, 12), Qt.AlignmentFlag.AlignLeft, self._label)
        p.setFont(QFont(FONT_BODY, 10, QFont.Weight.Bold))
        p.setPen(QPen(qcol(self._color, 240), 1))
        p.drawText(QRectF(0, 16, 110, 18), Qt.AlignmentFlag.AlignLeft, self._value_text)


        gauge_d = 34
        gx = W - gauge_d - 8
        gy = H - 4 - gauge_d / 2
        rect = QRectF(gx, gy - gauge_d / 2, gauge_d, gauge_d)
        p.setPen(QPen(qcol(C.BORDER_B), 3))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(rect, 0, 180 * 16)
        span = int(-(self._pct / 100.0) * 180 * 16)
        p.setPen(QPen(qcol(self._color, 230), 3, cap=Qt.PenCapStyle.RoundCap))
        p.drawArc(rect, 180 * 16, span)


        ang = math.radians(180 - (self._pct / 100.0) * 180)
        ncx, ncy = gx + gauge_d / 2, gy
        r = gauge_d / 2 - 3
        p.setPen(QPen(qcol("#ffffff", 220), 1.4))
        p.drawLine(QPointF(ncx, ncy),
                   QPointF(ncx + math.cos(ang) * r, ncy - math.sin(ang) * r))


        p.setFont(QFont(FONT_BODY, 5))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QPointF(gx - 10, ncy + 3), "0°C")
        p.drawText(QPointF(gx + gauge_d + 2, ncy + 3), "100°C")


class MetricBar(QWidget):

    def __init__(self, label: str, color: str = C.PRI, filled: bool = True,
                 show_graph: bool = True, parent=None):
        super().__init__(parent)
        self._label      = label
        self._color      = color
        self._filled     = filled
        self._show_graph = show_graph
        self._value  = 0.0
        self._text   = "--"
        self._hist: list[float] = []
        self._hist_max = 48
        self.setFixedHeight(54 if show_graph else 36)
        self.setMinimumWidth(80)

    def set_value(self, pct: float, text: str):
        self._value = max(0.0, min(100.0, pct))
        self._text  = text
        if self._show_graph:
            self._hist.append(self._value)
            if len(self._hist) > self._hist_max:
                self._hist.pop(0)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        rect = QRectF(0.5, 0.5, W - 1, H - 1)
        p.setBrush(QBrush(qcol(C.PANEL2, PANEL_ALPHA)))
        p.setPen(QPen(qcol(C.BORDER_A), 1.0))
        p.drawRoundedRect(rect, 8, 8)


        p.setFont(QFont(FONT_BODY, 8))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(10, 6, W - 16, 14),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._label)

        if self._value > 85:
            val_col = qcol(C.RED)
        elif self._value > 65:
            val_col = qcol(C.ACC)
        else:
            val_col = qcol(self._color)

        p.setFont(QFont(FONT_BODY, 12, QFont.Weight.Bold))
        p.setPen(QPen(val_col if self._text != "--" else qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(0, 4, W - 12, 18),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self._text)

        if not self._show_graph:
            return


        sp_x, sp_y = 8, 26
        sp_w, sp_h = W - 16, H - 32
        if len(self._hist) >= 2:
            n = len(self._hist)
            step = sp_w / max(1, self._hist_max - 1)
            start_x = sp_x + (self._hist_max - n) * step
            pts = []
            for i, v in enumerate(self._hist):
                px = start_x + i * step
                py = sp_y + sp_h - (v / 100.0) * sp_h
                pts.append(QPointF(px, py))

            if self._filled:
                fill_path = QPainterPath()
                fill_path.moveTo(pts[0].x(), sp_y + sp_h)
                for pt in pts:
                    fill_path.lineTo(pt)
                fill_path.lineTo(pts[-1].x(), sp_y + sp_h)
                fill_path.closeSubpath()
                fill_col = qcol(self._color, 55)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(fill_col))
                p.drawPath(fill_path)

            line_path = QPainterPath()
            line_path.moveTo(pts[0])
            for pt in pts[1:]:
                line_path.lineTo(pt)
            p.setPen(QPen(qcol(self._color, 220), 1.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(line_path)
        else:
            p.setPen(QPen(qcol(C.BORDER_A), 1))
            p.drawLine(QPointF(sp_x, sp_y + sp_h), QPointF(sp_x + sp_w, sp_y + sp_h))

class CircularGauge(QWidget):
    """
    Runder Fortschritts-Ring mit Prozentwert in der Mitte und Label darunter —
    das native Pendant zu den Gauge-Ringen im Web-Dashboard (app.html),
    fuer CPU/MEM/GPU im linken Panel.
    """

    def __init__(self, label: str, color: str = C.PRI, parent=None):
        super().__init__(parent)
        self._label = label
        self._color = color
        self._value = 0.0
        self._text  = "--"
        self.setFixedSize(42, 58)

    def set_value(self, pct: float, text: str) -> None:
        self._value = max(0.0, min(100.0, pct))
        self._text  = text
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        d = 40
        rect = QRectF((self.width() - d) / 2, 1, d, d)

        p.setPen(QPen(qcol(C.BORDER_A), 4))
        p.drawArc(rect, 0, 360 * 16)

        if self._value > 85:
            ring_col = qcol(C.RED)
        elif self._value > 65:
            ring_col = qcol(C.ACC)
        else:
            ring_col = qcol(self._color)
        span = int(-(self._value / 100.0) * 360 * 16)
        p.setPen(QPen(ring_col, 4, cap=Qt.PenCapStyle.RoundCap))
        p.drawArc(rect, 90 * 16, span)

        p.setFont(QFont(FONT_BODY, 8, QFont.Weight.Bold))
        p.setPen(QPen(ring_col if self._text != "--" else qcol(C.TEXT_DIM), 1))
        p.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), self._text)

        p.setFont(QFont(FONT_BODY, 6))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(0, d + 2, self.width(), 12),
                   int(Qt.AlignmentFlag.AlignCenter), self._label)


class LogWidget(QTextEdit):
    _sig = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(QFont(FONT_BODY, 9))
        self.setStyleSheet(f"""
            QTextEdit {{
                background: transparent;
                color: {C.TEXT};
                border: none;
                border-left: 2px solid {C.PRI_DIM};
                padding: 4px 8px;
                selection-background-color: {C.PRI_GHO};
            }}
            QScrollBar:vertical {{
                background: {C.BG};
                width: 8px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_B};
                border-radius: 4px;
                min-height: 20px;
            }}
        """)
        self._sig.connect(self._enqueue)

    def append_log(self, text: str):
        self._sig.emit(text)

    def _enqueue(self, text: str):
        """Zeile sofort komplett anfuegen — der fruehere Zeichen-fuer-
        Zeichen-Typewriter-Effekt war Retro-Aesthetik und kostete einen
        6ms-Timer; ruhiges, sofortiges Erscheinen wirkt moderner."""
        tl = text.lower()
        if   tl.startswith("you:"):     tag = "you"
        elif tl.startswith("rencora:"): tag = "ai"
        elif tl.startswith("file:"):    tag = "file"
        elif "error" in tl or "fehl" in tl: tag = "err"
        else:                            tag = "sys"
        col = qcol(C.RED) if tag == "err" else qcol(C.GREEN)
        cur = self.textCursor()
        cur.movePosition(cur.MoveOperation.End)
        fmt = cur.charFormat()
        fmt.setForeground(QBrush(col))
        cur.insertText(text + chr(10), fmt)
        self.setTextCursor(cur)
        self.ensureCursorVisible()


_FILE_ICONS = {
    "image":   ("", "#00ff41"), "video":   ("", "#ff6b00"),
    "audio":   ("", "#cc44ff"), "pdf":     ("", "#ff4444"),
    "word":    ("", "#4488ff"), "excel":   ("", "#44bb44"),
    "code":    ("", "#ffcc00"), "archive": ("", "#ff8844"),
    "pptx":    ("", "#ff6622"), "text":    ("", "#aaaaaa"),
    "data":    ("", "#88ddff"), "unknown": ("", "#888888"),
}
_EXT_TO_CAT = {
    **dict.fromkeys(["jpg","jpeg","png","gif","webp","bmp","tiff","svg","ico"], "image"),
    **dict.fromkeys(["mp4","avi","mov","mkv","wmv","flv","webm","m4v"],         "video"),
    **dict.fromkeys(["mp3","wav","ogg","m4a","aac","flac","wma","opus"],        "audio"),
    **dict.fromkeys(["pdf"],                                                     "pdf"),
    **dict.fromkeys(["doc","docx"],                                              "word"),
    **dict.fromkeys(["xls","xlsx","ods"],                                        "excel"),
    **dict.fromkeys(["ppt","pptx"],                                              "pptx"),
    **dict.fromkeys(["py","js","ts","jsx","tsx","html","css","java","c","cpp",
                     "cs","go","rs","rb","php","swift","kt","sh","sql","lua"],   "code"),
    **dict.fromkeys(["zip","rar","tar","gz","7z","bz2","xz"],                   "archive"),
    **dict.fromkeys(["txt","md","rst","log"],                                    "text"),
    **dict.fromkeys(["csv","tsv","json","xml"],                                  "data"),
}

def _file_category(path: Path) -> str:
    return _EXT_TO_CAT.get(path.suffix.lower().lstrip("."), "unknown")

def _fmt_size(size: int) -> str:
    if   size < 1024:    return f"{size} B"
    elif size < 1024**2: return f"{size/1024:.1f} KB"
    elif size < 1024**3: return f"{size/1024**2:.1f} MB"
    else:                return f"{size/1024**3:.1f} GB"


class FileDropZone(QWidget):
    file_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(100)
        self._current_file: str | None = None
        self._hovering  = False
        self._drag_over = False
        self._dash_offset = 0.0
        self._anim_tmr = QTimer(self)
        self._anim_tmr.timeout.connect(self._animate)
        self._anim_tmr.start(40)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._canvas = _DropCanvas(self)
        layout.addWidget(self._canvas)

    def _animate(self):
        self._dash_offset = (self._dash_offset + 0.8) % 20
        self._canvas.update()

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._drag_over = True; self._canvas.update()

    def dragLeaveEvent(self, e):
        self._drag_over = False; self._canvas.update()

    def dropEvent(self, e: QDropEvent):
        self._drag_over = False
        urls = e.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if Path(path).is_file():
                self._set_file(path)
        self._canvas.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._browse()

    def enterEvent(self, e):
        self._hovering = True; self._canvas.update()

    def leaveEvent(self, e):
        self._hovering = False; self._canvas.update()

    def current_file(self) -> str | None:
        return self._current_file

    def clear_file(self):
        self._current_file = None; self._canvas.update()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select a file for RENCORA", str(Path.home()),
            "All Files (*.*);;"
            "Images (*.jpg *.jpeg *.png *.gif *.webp *.bmp *.svg);;"
            "Documents (*.pdf *.docx *.txt *.md *.pptx);;"
            "Data (*.csv *.xlsx *.json *.xml);;"
            "Code (*.py *.js *.ts *.html *.css *.java *.cpp *.go);;"
            "Audio (*.mp3 *.wav *.ogg *.m4a *.aac *.flac);;"
            "Video (*.mp4 *.avi *.mov *.mkv *.wmv *.webm);;"
            "Archives (*.zip *.rar *.tar *.gz *.7z)",
        )
        if path:
            self._set_file(path)

    def _set_file(self, path: str):
        self._current_file = path
        self._canvas.update()
        self.file_selected.emit(path)


class _DropCanvas(QWidget):
    def __init__(self, zone: FileDropZone):
        super().__init__(zone)
        self._z = zone

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        z    = self._z
        W, H = self.width(), self.height()
        pad  = 6
        rect = QRectF(pad, pad, W - pad * 2, H - pad * 2)

        bg_col = qcol("#001a24" if z._drag_over else ("#001218" if z._hovering else C.PANEL))
        p.setBrush(QBrush(bg_col)); p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect, 6, 6)

        if z._current_file:   border_col = qcol(C.GREEN, 200)
        elif z._drag_over:    border_col = qcol(C.PRI, 230)
        elif z._hovering:     border_col = qcol(C.BORDER_B, 200)
        else:                 border_col = qcol(C.BORDER, 160)

        pen = QPen(border_col, 1.5, Qt.PenStyle.DashLine)
        pen.setDashOffset(z._dash_offset)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 6, 6)

        if z._current_file:   self._paint_file(p, W, H)
        elif z._drag_over:    self._paint_drag_over(p, W, H)
        else:                 self._paint_idle(p, W, H, z._hovering)

    def _paint_idle(self, p, W, H, hover):
        cx, cy = W / 2, H / 2
        col = qcol(C.PRI_DIM if not hover else C.PRI)
        p.setPen(QPen(col, 2)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(cx, cy - 14), QPointF(cx, cy + 4))
        p.drawLine(QPointF(cx - 8, cy - 6), QPointF(cx, cy - 14))
        p.drawLine(QPointF(cx + 8, cy - 6), QPointF(cx, cy - 14))
        p.drawLine(QPointF(cx - 14, cy + 4), QPointF(cx + 14, cy + 4))
        p.setFont(QFont(FONT_BODY, 8))
        p.setPen(QPen(qcol(C.PRI_DIM if not hover else C.TEXT), 1))
        p.drawText(QRectF(0, cy + 8, W, 16), Qt.AlignmentFlag.AlignCenter,
                   "Drop file here  or  Click to Browse")
        p.setFont(QFont(FONT_BODY, 7))
        p.setPen(QPen(qcol("#1a4a5a"), 1))
        p.drawText(QRectF(0, cy + 24, W, 14), Qt.AlignmentFlag.AlignCenter,
                   "Images · Video · Audio · PDF · Docs · Code · Data")

    def _paint_drag_over(self, p, W, H):
        cx, cy = W / 2, H / 2
        p.setFont(QFont(FONT_BODY, 20))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy - 24, W, 32), Qt.AlignmentFlag.AlignCenter, "")
        p.setFont(QFont(FONT_BODY, 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy + 12, W, 16), Qt.AlignmentFlag.AlignCenter, "Release to load")

    def _paint_file(self, p, W, H):
        path = Path(self._z._current_file)
        cat  = _file_category(path)
        icon, icon_col = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size_str = _fmt_size(path.stat().st_size)
        ext_str  = path.suffix.upper().lstrip(".") or "FILE"

        block_x, block_w = 10, 60
        p.setFont(QFont("Segoe UI Emoji", 22) if _OS == "Windows" else QFont("Arial", 22))
        p.setPen(QPen(qcol(icon_col), 1))
        p.drawText(QRectF(block_x, 0, block_w, H), Qt.AlignmentFlag.AlignCenter, icon)

        tx = block_x + block_w + 6
        tw = W - tx - 38

        p.setFont(QFont(FONT_BODY, 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.WHITE), 1))
        name = path.name if len(path.name) <= 34 else path.name[:31] + "..."
        p.drawText(QRectF(tx, H * 0.18, tw, 16),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)

        p.setFont(QFont(FONT_BODY, 7))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(tx, H * 0.18 + 18, tw, 14),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f"{ext_str}  ·  {size_str}")

        p.setFont(QFont(FONT_BODY, 6))
        p.setPen(QPen(qcol("#1e5c6a"), 1))
        par = str(path.parent)
        if len(par) > 42: par = "…" + par[-41:]
        p.drawText(QRectF(tx, H * 0.18 + 34, tw, 12),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, par)

        p.setFont(QFont(FONT_BODY, 9, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.RED, 180), 1))
        p.drawText(QRectF(W - 34, 0, 28, H), Qt.AlignmentFlag.AlignCenter, "")

    def mousePressEvent(self, e):
        z = self._z
        if z._current_file and e.pos().x() > self.width() - 34:
            z.clear_file()
        else:
            z.mousePressEvent(e)


class SetupOverlay(QWidget):
    done = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            SetupOverlay {{
                background: rgba(0, 6, 10, 245);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)

        detected = {"darwin": "mac", "windows": "windows"}.get(
            _OS.lower(), "linux"
        )
        self._sel_os = detected

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 22, 30, 22)
        layout.setSpacing(8)

        def _lbl(txt, font_size=9, bold=False, color=C.PRI,
                 align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt)
            w.setAlignment(align)
            w.setFont(QFont(FONT_BODY, font_size,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            return w

        layout.addWidget(_lbl("◈  INITIALISATION REQUIRED", 13, True))
        layout.addWidget(_lbl("Configure RENCORA before first boot.", 9, color=C.PRI_DIM))
        layout.addSpacing(6)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER};"); layout.addWidget(sep)
        layout.addSpacing(4)

        layout.addWidget(_lbl("GEMINI API KEY", 8, color=C.TEXT_DIM,
                               align=Qt.AlignmentFlag.AlignLeft))
        key_link = QLabel(
            f'<a href="https://aistudio.google.com/app/apikey" '
            f'style="color:{C.ACC2}; text-decoration:none;">'
            f'&#8594;  Schluessel kostenlos erstellen (Google AI Studio)</a>'
        )
        key_link.setAlignment(Qt.AlignmentFlag.AlignLeft)
        key_link.setFont(QFont(FONT_BODY, 8))
        key_link.setStyleSheet("background: transparent;")
        key_link.setOpenExternalLinks(True)
        key_link.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(key_link)
        layout.addSpacing(2)
        self._key_input = QLineEdit()
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_input.setPlaceholderText("AIza…")
        self._key_input.setFont(QFont(FONT_BODY, 10))
        self._key_input.setFixedHeight(32)
        self._key_input.setStyleSheet(f"""
            QLineEdit {{
                background: #000d12; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 3px; padding: 4px 8px;
            }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
        """)
        layout.addWidget(self._key_input)
        layout.addSpacing(12)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color: {C.BORDER};"); layout.addWidget(sep2)
        layout.addSpacing(4)

        layout.addWidget(_lbl("OPERATING SYSTEM", 8, color=C.TEXT_DIM,
                               align=Qt.AlignmentFlag.AlignLeft))
        det_name = {"windows": "Windows", "mac": "macOS", "linux": "Linux"}[detected]
        layout.addWidget(_lbl(f"Auto-detected: {det_name}", 8, color=C.ACC2,
                               align=Qt.AlignmentFlag.AlignLeft))

        os_row = QHBoxLayout(); os_row.setSpacing(6)
        self._os_btns: dict[str, QPushButton] = {}
        for key, label in [("windows","⊞  Windows"),("mac","  macOS"),("linux","  Linux")]:
            btn = QPushButton(label)
            btn.setFont(QFont(FONT_BODY, 9, QFont.Weight.Bold))
            btn.setFixedHeight(32)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, k=key: self._sel(k))
            os_row.addWidget(btn)
            self._os_btns[key] = btn
        layout.addLayout(os_row)
        self._sel(detected)
        layout.addSpacing(12)

        init_btn = QPushButton("▸  INITIALISE SYSTEMS")
        init_btn.setFont(QFont(FONT_BODY, 10, QFont.Weight.Bold))
        init_btn.setFixedHeight(36)
        init_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        init_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 3px;
            }}
            QPushButton:hover {{
                background: {C.PRI_GHO}; border: 1px solid {C.PRI};
            }}
        """)
        init_btn.clicked.connect(self._submit)
        layout.addWidget(init_btn)

    def _sel(self, key: str):
        self._sel_os = key
        pal = {"windows":(C.PRI,"#001a22"),"mac":(C.ACC2,"#1a1400"),"linux":(C.GREEN,"#001a0d")}
        for k, btn in self._os_btns.items():
            if k == key:
                fg, bg = pal[k]
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {fg}; color: {bg};
                        border: none; border-radius: 3px; font-weight: bold;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: #000d12; color: {C.TEXT_DIM};
                        border: 1px solid {C.BORDER}; border-radius: 3px;
                    }}
                    QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}
                """)

    def _submit(self):
        key = self._key_input.text().strip()
        if not key:
            self._key_input.setStyleSheet(
                self._key_input.styleSheet() +
                f" QLineEdit {{ border: 1px solid {C.RED}; }}"
            )
            return
        self.done.emit(key, self._sel_os)


class RemoteKeyOverlay(QWidget):
    """Floating overlay — QR code for instant phone pairing + manual key fallback.
    Unterstuetzt zwei Modi: LAN (lokales Netz) und INTERNET (Cloudflare-Tunnel,
    funktioniert auch wenn das Handy NICHT im selben WLAN ist)."""

    closed = pyqtSignal()

    _OW, _OH = 400, 505

    def __init__(self, url: str, key: str, auto_login_url: str = "",
                 manual_url: str = "", expiry_secs: int = 600, parent=None,
                 tunnel_url: str = None, tunnel_auto_login_url: str = "",
                 get_tunnel_status_fn=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            RemoteKeyOverlay {{
                background: rgba(0, 4, 12, 0.95);
                border: 1px solid {C.BORDER_B};
                border-radius: 14px;
            }}
        """)
        self._expiry          = time.time() + expiry_secs
        self._on_new_key      = None
        self._auto_login_url  = auto_login_url
        self._manual_url      = manual_url or url


        self._mode                  = "lan"
        self._tunnel_url            = tunnel_url
        self._tunnel_auto           = tunnel_auto_login_url
        self._tunnel_status         = "running" if tunnel_url else "starting"
        self._get_tunnel_status_fn  = get_tunnel_status_fn

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 16, 24, 16)
        lay.setSpacing(5)

        def _lbl(txt, fs=9, bold=False, color=C.PRI,
                 align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt)
            w.setAlignment(align)
            w.setFont(QFont(FONT_BODY, fs,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            w.setWordWrap(True)
            return w

        lay.addWidget(_lbl("◈  REMOTE ACCESS", 12, True))
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 1px 0;")
        lay.addWidget(sep)


        mode_row = QHBoxLayout(); mode_row.setSpacing(6)

        def _mode_btn(txt):
            b = QPushButton(txt)
            b.setFixedHeight(26)
            b.setFont(QFont(FONT_BODY, 8, QFont.Weight.Bold))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            return b

        self._lan_btn = _mode_btn(" LAN")
        self._lan_btn.clicked.connect(lambda: self._set_mode("lan"))
        self._net_btn = _mode_btn(" INTERNET")
        self._net_btn.clicked.connect(lambda: self._set_mode("net"))
        mode_row.addWidget(self._lan_btn)
        mode_row.addWidget(self._net_btn)
        lay.addLayout(mode_row)

        self._mode_hint = _lbl("", 8, color=C.TEXT_DIM)
        lay.addWidget(self._mode_hint)


        self._qr_label = QLabel()
        self._qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._qr_label.setFixedSize(176, 176)
        self._qr_label.setStyleSheet(
            "background: white; border-radius: 10px; padding: 4px;"
        )
        qr_row = QHBoxLayout()
        qr_row.addStretch()
        qr_row.addWidget(self._qr_label)
        qr_row.addStretch()
        lay.addLayout(qr_row)

        self._update_qr(auto_login_url)

        lay.addWidget(_lbl("Scan with phone camera to connect instantly", 8, color=C.TEXT_DIM))

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color: {C.BORDER}; margin: 1px 0;")
        lay.addWidget(sep2)

        lay.addWidget(_lbl("Or enter manually:", 7, color=C.TEXT_DIM,
                           align=Qt.AlignmentFlag.AlignLeft))

        self._url_lbl = QLabel(self._manual_url)
        self._url_lbl.setFont(QFont(FONT_BODY, 8))
        self._url_lbl.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent;")
        self._url_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._url_lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self._url_lbl)

        self._key_lbl = QLabel(key)
        self._key_lbl.setFont(QFont(FONT_BODY, 28, QFont.Weight.Bold))
        self._key_lbl.setStyleSheet(f"""
            color: {C.ACC};
            background: {C.PANEL2};
            border: 1px solid {C.BORDER_B};
            border-radius: 8px;
            padding: 6px 4px;
            letter-spacing: 10px;
        """)
        self._key_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._key_lbl)

        self._timer_lbl = QLabel()
        self._timer_lbl.setFont(QFont(FONT_BODY, 8))
        self._timer_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        self._timer_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._timer_lbl)

        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        new_btn = QPushButton("NEW KEY")
        new_btn.setFixedHeight(32)
        new_btn.setFont(QFont(FONT_BODY, 8, QFont.Weight.Bold))
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL}; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 5px;
            }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border: 1px solid {C.PRI}; }}
        """)
        new_btn.clicked.connect(self._refresh_key)
        btn_row.addWidget(new_btn)

        close_btn = QPushButton("DISMISS")
        close_btn.setFixedHeight(32)
        close_btn.setFont(QFont(FONT_BODY, 8, QFont.Weight.Bold))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 5px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}
        """)
        close_btn.clicked.connect(self._do_close)
        btn_row.addWidget(close_btn)
        lay.addLayout(btn_row)

        self._ctimer = QTimer(self)
        self._ctimer.timeout.connect(self._tick)
        self._ctimer.start(1000)
        self._set_mode("lan")
        self._tick()

    def set_new_key_callback(self, fn) -> None:
        self._on_new_key = fn

    def _style_mode_buttons(self) -> None:
        active = f"""
            QPushButton {{
                background: {C.PRI_GHO}; color: {C.PRI};
                border: 1px solid {C.PRI}; border-radius: 5px;
            }}
        """
        inactive = f"""
            QPushButton {{
                background: {C.PANEL}; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 5px;
            }}
            QPushButton:hover {{ border: 1px solid {C.PRI_DIM}; color: {C.TEXT}; }}
        """
        self._lan_btn.setStyleSheet(active if self._mode == "lan" else inactive)
        self._net_btn.setStyleSheet(active if self._mode == "net" else inactive)
        label = " INTERNET"
        if self._tunnel_status == "starting":
            label = " STARTET…"
        elif self._tunnel_status in ("disabled", "failed") and not self._tunnel_url:
            label = " N/V"
        self._net_btn.setText(label)

    def _set_mode(self, mode: str) -> None:
        if mode == "net" and not self._tunnel_url and self._tunnel_status not in ("starting",):

            pass
        self._mode = mode
        self._style_mode_buttons()
        if mode == "lan":
            self._update_qr(self._auto_login_url)
            self._url_lbl.setText(self._manual_url)
            self._mode_hint.setText("Nur im selben WLAN wie dieser PC nutzbar.")
        else:
            if self._tunnel_url:
                self._update_qr(self._tunnel_auto or self._tunnel_url)
                self._url_lbl.setText(self._tunnel_url.replace("https://", ""))
                self._mode_hint.setText("Funktioniert ueberall — auch per Mobilfunknetz, ohne WLAN.")
            else:
                self._qr_label.setPixmap(QPixmap())
                self._qr_label.setText(
                    "Tunnel wird\ngestartet…" if self._tunnel_status == "starting"
                    else "Nicht verfuegbar\n(cloudflared fehlt)"
                )
                self._qr_label.setFont(QFont(FONT_BODY, 9))
                self._qr_label.setStyleSheet(
                    f"color: {C.TEXT_MED}; background: white; border-radius: 10px; padding: 4px;"
                )
                self._url_lbl.setText("—")
                self._mode_hint.setText(
                    "Kurz warten, der Internet-Link braucht ein paar Sekunden…"
                    if self._tunnel_status == "starting" else
                    "cloudflared nicht gefunden — siehe CHANGELOG fuer manuelle Installation."
                )


    def _update_qr(self, url: str) -> None:
        if not url:
            self._qr_label.setText("—")
            return
        try:
            import qrcode as _qrmod
            from io import BytesIO
            qr = _qrmod.QRCode(
                box_size=5, border=2,
                error_correction=_qrmod.constants.ERROR_CORRECT_M,
            )
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buf = BytesIO()
            img.save(buf, format="PNG")
            px = QPixmap()
            px.loadFromData(buf.getvalue())
            self._qr_label.setPixmap(
                px.scaled(170, 170,
                          Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
            )
        except ImportError:
            self._qr_label.setText("pip install\nqrcode[pil]")
            self._qr_label.setFont(QFont(FONT_BODY, 8))
            self._qr_label.setStyleSheet(
                "color: #888; background: white; border-radius: 10px; padding: 4px;"
            )
        except Exception:
            self._qr_label.setText(url[:28])
            self._qr_label.setFont(QFont(FONT_BODY, 7))
            self._qr_label.setStyleSheet(
                f"color: {C.PRI}; background: white; border-radius: 10px; padding: 4px;"
            )

    def _tick(self):
        remaining = max(0, int(self._expiry - time.time()))
        m, s = divmod(remaining, 60)
        self._timer_lbl.setText(f"Key expires in  {m:02d}:{s:02d}")
        if remaining == 0:
            self._do_close()


        if self._get_tunnel_status_fn:
            try:
                status, url, auto = self._get_tunnel_status_fn()
            except Exception:
                status, url, auto = "failed", None, ""
            changed = (status != self._tunnel_status) or (url != self._tunnel_url)
            self._tunnel_status = status
            self._tunnel_url    = url
            self._tunnel_auto   = auto
            if changed:
                self._style_mode_buttons()
                if self._mode == "net":
                    self._set_mode("net")

    def mark_connected(self) -> None:
        """Call from any thread when a phone successfully connects."""
        self._ctimer.stop()
        self._key_lbl.setText("CONNECTED")
        self._key_lbl.setStyleSheet(f"""
            color: {C.GREEN};
            background: rgba(34,197,94,0.08);
            border: 2px solid rgba(34,197,94,0.4);
            border-radius: 8px;
            padding: 6px 4px;
            letter-spacing: 4px;
        """)
        self._qr_label.setText("")
        self._qr_label.setFont(QFont(FONT_BODY, 54, QFont.Weight.Bold))
        self._qr_label.setStyleSheet(
            "color: #00ff88; background: #001a0d; border-radius: 10px;"
        )
        self._timer_lbl.setText("Phone connected — RENCORA ready")
        self._timer_lbl.setStyleSheet(f"color: {C.GREEN}; background: transparent;")

    def _refresh_key(self):
        if self._on_new_key:
            result = self._on_new_key()
            if result:
                url    = result[0]
                key    = result[1]
                auto   = result[2] if len(result) >= 3 else ""
                manual = result[3] if len(result) >= 4 else url
                self._manual_url     = manual or url
                self._key_lbl.setText(key)
                self._auto_login_url = auto
                self._tunnel_url  = result[4] if len(result) >= 5 else self._tunnel_url
                self._tunnel_auto = result[5] if len(result) >= 6 else self._tunnel_auto
                self._expiry = time.time() + 600
                self._key_lbl.setStyleSheet(f"""
                    color: {C.ACC};
                    background: {C.PANEL2};
                    border: 1px solid {C.BORDER_B};
                    border-radius: 8px;
                    padding: 6px 4px;
                    letter-spacing: 10px;
                """)
                self._timer_lbl.setStyleSheet(
                    f"color: {C.TEXT_MED}; background: transparent;"
                )
                self._ctimer.start(1000)
                self._set_mode(self._mode)
                self._tick()

    def _do_close(self):
        self._ctimer.stop()
        self.hide()
        self.closed.emit()


class NavButton(QWidget):
    """
    Klickbarer Sidebar-Navigationspunkt (Icon + Label), siehe Referenz-
    Dashboard: DASHBOARD/MONITOR/SYSTEMS/NETWORK/PROCESSES/UPLOAD/
    TERMINAL/SETTINGS. Aktiver Eintrag wird grün hervorgehoben, alle
    anderen bleiben gedimmt — `set_active()` steuert das.

    Hinweis: Aktuell rein visuell mit Hervorhebung beim Klick; löst noch
    keine echte Ansichtsumschaltung aus (das Dashboard bleibt das, was
    HudCanvas/SYS-MONITOR/ACTIVITY-LOG zeigen, unabhängig vom gewählten
    Eintrag). Eine echte Mehrfach-Ansicht wäre eine separate Erweiterung.
    """

    clicked = pyqtSignal(str)

    def __init__(self, icon: str, label: str, key: str, parent=None):
        super().__init__(parent)
        self._key = key
        self._active = False
        self.setFixedHeight(38)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 4, 0)
        lay.setSpacing(8)
        self._icon_name = icon
        self._icon_lbl = QLabel()
        pm = svg_icon(icon, C.TEXT_DIM, 15)
        if pm is not None:
            self._icon_lbl.setPixmap(pm)
        else:
            self._icon_lbl.setText(icon)
            self._icon_lbl.setFont(QFont(FONT_BODY, 10))
        self._icon_lbl.setFixedWidth(16)
        lay.addWidget(self._icon_lbl)
        self._text_lbl = QLabel(label)
        self._text_lbl.setFont(QFont(FONT_BODY, 7, QFont.Weight.Bold))
        lay.addWidget(self._text_lbl)
        lay.addStretch()
        self._apply_style()

    def set_active(self, active: bool) -> None:
        self._active = active
        self._apply_style()

    def _apply_style(self) -> None:
        if self._active:
            self.setStyleSheet(
                f"background: {C.PRI_GHO}; border: 1px solid {C.BORDER_B}; border-radius: 4px;"
            )
            pm = svg_icon(self._icon_name, C.PRI, 15)
            if pm is not None:
                self._icon_lbl.setPixmap(pm)
            self._icon_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
            self._text_lbl.setStyleSheet(f"color: {C.WHITE}; background: transparent;")
        else:
            self.setStyleSheet("background: transparent; border: 1px solid transparent; border-radius: 4px;")
            pm = svg_icon(self._icon_name, C.TEXT_DIM, 15)
            if pm is not None:
                self._icon_lbl.setPixmap(pm)
            self._icon_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
            self._text_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")

    def mousePressEvent(self, event):
        self.clicked.emit(self._key)
        super().mousePressEvent(event)


class HexagonBadge(QWidget):
    """Kleines, grün umrandetes Hexagon-Icon mit zentriertem Buchstaben — siehe Referenz-Dashboard, oben links."""

    def __init__(self, letter: str, parent=None):
        super().__init__(parent)
        self._letter = letter

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        r = min(w, h) / 2 - 2

        path = QPainterPath()
        for i in range(6):
            angle = math.pi / 6 + i * math.pi / 3
            x, y = cx + r * math.cos(angle), cy + r * math.sin(angle)
            path.moveTo(x, y) if i == 0 else path.lineTo(x, y)
        path.closeSubpath()

        p.setPen(QPen(qcol(C.PRI, 220), 1.6))
        p.setBrush(QBrush(qcol(C.PRI, 18)))
        p.drawPath(path)

        p.setPen(QPen(qcol(C.PRI, 255), 1))
        p.setFont(QFont(FONT_BODY, int(r * 0.7), QFont.Weight.Bold))
        p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, self._letter)


class StatusDot(QWidget):
    """Kleiner, gefüllter Status-Punkt (z. B. neben 'AI CORE ACTIVE')."""

    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self._color = color

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(qcol(self._color, 255)))
        r = min(self.width(), self.height()) / 2
        p.drawEllipse(QPointF(self.width() / 2, self.height() / 2), r, r)


class HeaderIconButton(QLabel):
    """
    Kleines, klickbares Icon mit optionalem Benachrichtigungs-Badge
    (z. B. die rote '2' auf dem Glocken-Symbol im Referenz-Dashboard).
    Rein optisch — verbindet sich noch mit keiner Aktion, kann aber per
    .clicked-Signal-Ersatz (mousePressEvent) später leicht erweitert werden.
    """

    def __init__(self, glyph: str, badge_count: int = 0, parent=None):
        super().__init__(parent)
        self._glyph = glyph
        self._badge_count = badge_count
        self.setFixedSize(30, 30)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFont(QFont(FONT_BODY, 12))
        self.setStyleSheet(f"color: {C.TEXT}; background: transparent;")
        self.setText(glyph)

    def set_badge_count(self, count: int) -> None:
        self._badge_count = count
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._badge_count <= 0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(qcol(C.RED, 230)))
        bx, by, br = self.width() - 9, 3, 7
        p.drawEllipse(QPointF(bx, by), br, br)
        p.setPen(QPen(qcol(C.WHITE, 255), 1))
        p.setFont(QFont(FONT_BODY, 6, QFont.Weight.Bold))
        p.drawText(
            QRectF(bx - br, by - br, br * 2, br * 2),
            Qt.AlignmentFlag.AlignCenter,
            str(min(self._badge_count, 9)),
        )


class HeaderBgWidget(QWidget):
    """Header-Band mit feinen Schaltkreis-Spuren samt Knotenpunkten und
    Verzweigungen beidseitig des Titels — wie im Referenzbild."""

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        cy = H / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(qcol(C.DARK, PANEL_ALPHA)))
        p.drawRect(self.rect())


        cx = W / 2
        clear_w = min(W * 0.16, 190)
        for side in (-1, 1):
            x0 = cx + side * clear_w
            x_end = cx + side * (clear_w + W * 0.22)
            for k, dy in enumerate((-10, 0, 10)):
                yy = cy + dy
                jog = x0 + side * (30 + k * 46)
                p.setPen(QPen(qcol(C.PRI, 60 - k * 12), 1))
                p.drawLine(QPointF(x0, yy), QPointF(jog, yy))
                p.drawLine(QPointF(jog, yy), QPointF(jog, yy - 6 * (1 if k % 2 else -1)))
                p.drawLine(QPointF(jog, yy - 6 * (1 if k % 2 else -1)),
                           QPointF(x_end, yy - 6 * (1 if k % 2 else -1)))

                p.setBrush(QBrush(qcol(C.PRI, 140 - k * 25)))
                p.setPen(Qt.PenStyle.NoPen)
                for nx, ny in ((x0, yy), (jog, yy - 6 * (1 if k % 2 else -1)),
                               (x_end, yy - 6 * (1 if k % 2 else -1))):
                    p.drawEllipse(QPointF(nx, ny), 1.7, 1.7)

        p.setPen(QPen(qcol(C.BORDER_B, 170), 1))
        p.drawLine(QPointF(0, H - 0.5), QPointF(W, H - 0.5))


class ToggleSwitch(QWidget):
    """Kleiner iOS-artiger Schalter (Track + Knopf) fuer die Theme-Leiste."""

    toggled = pyqtSignal(bool)

    def __init__(self, checked: bool = True, parent=None):
        super().__init__(parent)
        self._checked = checked
        self.setFixedSize(34, 18)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def is_checked(self) -> bool:
        return self._checked

    def set_checked(self, v: bool) -> None:
        if v != self._checked:
            self._checked = v
            self.update()

    def mousePressEvent(self, _):
        self._checked = not self._checked
        self.update()
        self.toggled.emit(self._checked)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = qcol(C.PRI, 160) if self._checked else qcol(C.BORDER)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(track))
        p.drawRoundedRect(QRectF(0, 2, 34, 14), 7, 7)
        knob_x = 20 if self._checked else 2
        p.setBrush(QBrush(qcol("#ffffff", 235) if self._checked else qcol(C.TEXT_DIM)))
        p.drawEllipse(QRectF(knob_x, 1, 16, 16))


class ColorWheel(QWidget):
    """
    Selbst gezeichnetes Hue-Rad (Konus-Gradient-Ring) mit innerem
    Saettigungs/Helligkeits-Quadrat und Cursor-Kreisen — siehe
    Referenz-Popup "CUSTOM COLOR". Maus setzt Hue (Ring) bzw. S/V (Quadrat).
    """

    colorChanged = pyqtSignal(QColor)

    def __init__(self, initial: QColor, parent=None):
        super().__init__(parent)
        self.setFixedSize(150, 150)
        h, s, v, _ = initial.getHsvF()
        self._h = max(0.0, h)
        self._s = s
        self._v = v
        self._drag = None

    def color(self) -> QColor:
        return QColor.fromHsvF(self._h, self._s, self._v)

    def set_value(self, v: float) -> None:
        """Helligkeit (V) von aussen setzen (BRIGHTNESS-Slider)."""
        self._v = max(0.0, min(1.0, v))
        self.update()
        self.colorChanged.emit(self.color())

    def _geom(self):
        cx, cy = self.width() / 2, self.height() / 2
        outer = min(cx, cy) - 2
        inner = outer * 0.74
        side = inner * 1.30
        return cx, cy, outer, inner, side

    def paintEvent(self, _):
        from PyQt6.QtGui import QConicalGradient, QLinearGradient
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy, outer, inner, side = self._geom()

        grad = QConicalGradient(QPointF(cx, cy), 90)
        for i in range(13):
            grad.setColorAt(i / 12, QColor.fromHsvF((i / 12) % 1.0, 1, 1))
        ring = QPainterPath()
        ring.addEllipse(QPointF(cx, cy), outer, outer)
        ring.addEllipse(QPointF(cx, cy), inner, inner)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        p.drawPath(ring)


        sq = QRectF(cx - side / 2, cy - side / 2, side, side)
        base = QColor.fromHsvF(self._h, 1, 1)
        gx = QLinearGradient(sq.topLeft(), sq.topRight())
        gx.setColorAt(0, QColor("#ffffff")); gx.setColorAt(1, base)
        p.setBrush(QBrush(gx)); p.drawRoundedRect(sq, 4, 4)
        gy = QLinearGradient(sq.topLeft(), sq.bottomLeft())
        gy.setColorAt(0, QColor(0, 0, 0, 0)); gy.setColorAt(1, QColor("#000000"))
        p.setBrush(QBrush(gy)); p.drawRoundedRect(sq, 4, 4)


        ang = (90 - self._h * 360) * math.pi / 180
        rr = (outer + inner) / 2
        hx, hy = cx + math.cos(ang) * rr, cy - math.sin(ang) * rr
        p.setPen(QPen(QColor("#ffffff"), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(hx, hy), (outer - inner) / 2 - 1, (outer - inner) / 2 - 1)

        sx = sq.left() + self._s * side
        sy = sq.top() + (1 - self._v) * side
        p.drawEllipse(QPointF(sx, sy), 5, 5)

    def _handle(self, pos):
        cx, cy, outer, inner, side = self._geom()
        dx, dy = pos.x() - cx, pos.y() - cy
        dist = (dx * dx + dy * dy) ** 0.5
        sq_half = side / 2
        if self._drag == "ring" or (self._drag is None and inner <= dist <= outer):
            self._drag = "ring"
            ang = math.degrees(math.atan2(-dy, dx))
            self._h = ((90 - ang) % 360) / 360
        elif self._drag == "square" or (abs(dx) <= sq_half and abs(dy) <= sq_half):
            self._drag = "square"
            self._s = max(0.0, min(1.0, (dx + sq_half) / side))
            self._v = max(0.0, min(1.0, 1 - (dy + sq_half) / side))
        else:
            return
        self.update()
        self.colorChanged.emit(self.color())

    def mousePressEvent(self, e):
        self._drag = None
        self._handle(e.position())

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.MouseButton.LeftButton:
            self._handle(e.position())

    def mouseReleaseEvent(self, _):
        self._drag = None


class CustomColorPopup(QWidget):
    """
    'CUSTOM COLOR'-Popup wie im Referenz-Dashboard: Farbrad + Vorschau +
    Hex-Wert + BRIGHTNESS-Slider + Swatch-Reihe mit '+'-Button. Uebernimmt
    NICHT selbst — die Auswahl wird per colorChosen-Signal an die Theme-
    Leiste gemeldet (Vorschau) und erst dort mit APPLY THEME persistiert.
    """

    colorChosen = pyqtSignal(str)

    def __init__(self, initial_hex: str, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(370, 230)
        self.setStyleSheet(
            f"QWidget {{ background: {C.PANEL2}; border: 1px solid {C.BORDER_B}; }}")

        initial = QColor(initial_hex) if QColor(initial_hex).isValid() else QColor("#8a2be2")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 10, 14, 12)
        outer.setSpacing(8)

        head = QHBoxLayout()
        title = QLabel("CUSTOM COLOR")
        title.setFont(QFont(FONT_BODY, 9, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.TEXT}; background: transparent; border: none; letter-spacing: 2px;")
        head.addWidget(title)
        head.addStretch()
        close_btn = QPushButton("")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setFixedSize(20, 20)
        close_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {C.TEXT_DIM}; border: none; }}"
            f"QPushButton:hover {{ color: #ffffff; }}")
        close_btn.clicked.connect(self.close)
        head.addWidget(close_btn)
        outer.addLayout(head)

        body = QHBoxLayout(); body.setSpacing(14)
        self._wheel = ColorWheel(initial)
        self._wheel.colorChanged.connect(self._on_wheel)
        body.addWidget(self._wheel)

        right = QVBoxLayout(); right.setSpacing(5)
        lbl_prev = QLabel("COLOR PREVIEW")
        lbl_prev.setFont(QFont(FONT_BODY, 7))
        lbl_prev.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none; letter-spacing: 1.5px;")
        right.addWidget(lbl_prev)

        prev_row = QHBoxLayout(); prev_row.setSpacing(8)
        self._preview = QLabel()
        self._preview.setFixedSize(46, 28)
        prev_row.addWidget(self._preview)
        self._hex_lbl = QLabel(initial.name())
        self._hex_lbl.setFont(QFont(FONT_BODY, 9, QFont.Weight.Bold))
        self._hex_lbl.setStyleSheet(f"color: {C.TEXT}; background: transparent; border: none;")
        prev_row.addWidget(self._hex_lbl)
        prev_row.addStretch()
        right.addLayout(prev_row)

        bright_head = QHBoxLayout()
        lbl_b = QLabel("BRIGHTNESS")
        lbl_b.setFont(QFont(FONT_BODY, 7))
        lbl_b.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none; letter-spacing: 1.5px;")
        bright_head.addWidget(lbl_b)
        bright_head.addStretch()
        self._bright_val = QLabel()
        self._bright_val.setFont(QFont(FONT_BODY, 7, QFont.Weight.Bold))
        self._bright_val.setStyleSheet(f"color: {C.TEXT}; background: transparent; border: none;")
        bright_head.addWidget(self._bright_val)
        right.addLayout(bright_head)

        from PyQt6.QtWidgets import QSlider
        self._bright = QSlider(Qt.Orientation.Horizontal)
        self._bright.setRange(0, 100)
        self._bright.setStyleSheet(
            f"QSlider::groove:horizontal {{ height: 4px; background: {C.BORDER}; border-radius: 2px; }}"
            f"QSlider::sub-page:horizontal {{ background: {C.PRI}; border-radius: 2px; }}"
            f"QSlider::handle:horizontal {{ width: 12px; height: 12px; margin: -4px 0; "
            f"border-radius: 6px; background: #ffffff; }}")
        self._bright.valueChanged.connect(self._on_brightness)
        right.addWidget(self._bright)

        swatch_row = QHBoxLayout(); swatch_row.setSpacing(5)
        self._swatch_row = swatch_row
        self._rebuild_swatches()
        right.addLayout(swatch_row)
        right.addStretch()
        body.addLayout(right, stretch=1)
        outer.addLayout(body)

        self._sync(initial)


    def _rebuild_swatches(self) -> None:
        while self._swatch_row.count():
            item = self._swatch_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        defaults = ["#8a2be2", "#7a1f3d", "#ffb300", "#00c853", "#2979ff", "#c026d3"]
        saved = _theme_manager.get_custom_swatches() if _theme_manager else []
        for hexcol in (defaults + saved)[:10]:
            dot = QPushButton()
            dot.setCursor(Qt.CursorShape.PointingHandCursor)
            dot.setFixedSize(18, 18)
            dot.setToolTip(hexcol)
            dot.setStyleSheet(
                f"QPushButton {{ background: {hexcol}; border: 1px solid {C.BORDER_B}; border-radius: 9px; }}"
                f"QPushButton:hover {{ border: 2px solid #ffffff; }}")
            dot.clicked.connect(lambda _=False, h=hexcol: self._select_hex(h))
            self._swatch_row.addWidget(dot)
        plus = QPushButton("+")
        plus.setCursor(Qt.CursorShape.PointingHandCursor)
        plus.setFixedSize(18, 18)
        plus.setToolTip("Aktuelle Farbe als Preset speichern")
        plus.setStyleSheet(
            f"QPushButton {{ background: {C.PANEL}; color: {C.TEXT_DIM}; "
            f"border: 1px solid {C.BORDER_B}; border-radius: 9px; font-weight: bold; }}"
            f"QPushButton:hover {{ color: #ffffff; border-color: #ffffff; }}")
        plus.clicked.connect(self._save_swatch)
        self._swatch_row.addWidget(plus)
        self._swatch_row.addStretch()

    def _save_swatch(self) -> None:
        if _theme_manager is not None:
            _theme_manager.add_custom_swatch(self._wheel.color().name())
            self._rebuild_swatches()

    def _select_hex(self, hexcol: str) -> None:
        col = QColor(hexcol)
        h, s, v, _ = col.getHsvF()
        self._wheel._h, self._wheel._s, self._wheel._v = max(0.0, h), s, v
        self._wheel.update()
        self._sync(col)
        self.colorChosen.emit(col.name())

    def _on_wheel(self, col: QColor) -> None:
        self._sync(col)
        self.colorChosen.emit(col.name())

    def _on_brightness(self, val: int) -> None:
        self._wheel.set_value(val / 100.0)

    def _sync(self, col: QColor) -> None:
        self._preview.setStyleSheet(
            f"background: {col.name()}; border: 1px solid {C.BORDER_B}; border-radius: 4px;")
        self._hex_lbl.setText(col.name().upper())
        self._bright.blockSignals(True)
        self._bright.setValue(int(self._wheel._v * 100))
        self._bright.blockSignals(False)
        self._bright_val.setText(f"{int(self._wheel._v * 100)}%")


class MainWindow(QMainWindow):
    _log_sig     = pyqtSignal(str)
    _state_sig   = pyqtSignal(str)
    _news_sig    = pyqtSignal(str, list)
    _confirm_sig = pyqtSignal(object)

    def __init__(self, face_path: str):
        super().__init__()
        ensure_fonts_loaded()
        self.setWindowTitle("RENCORA v7 — RENKER INDUSTRIES")
        self.setMinimumSize(_MIN_W, _MIN_H)
        self.resize(_DEFAULT_W, _DEFAULT_H)

        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            (screen.width()  - _DEFAULT_W) // 2,
            (screen.height() - _DEFAULT_H) // 2,
        )

        self.on_text_command  = None
        self.on_remote_clicked = None
        self.on_get_tunnel_status = None
        self._muted           = False
        self._current_file: str | None = None
        self._remote_overlay: RemoteKeyOverlay | None = None


        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._central = QWidget()
        central = self._central
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self._nav_panel = self._build_nav_panel()
        body.addWidget(self._nav_panel, stretch=0)

        self._left_panel = self._build_left_panel()
        body.addWidget(self._left_panel, stretch=0)

        center_col = QVBoxLayout()
        center_col.setSpacing(6)

        self.hud = HudCanvas(face_path)
        self.hud.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)


        self._view_stack = QStackedWidget()
        self._view_stack.addWidget(self.hud)
        self._view_indices: dict[str, int] = {"dashboard": 0}

        for key, builder in (
            ("monitor", self._build_monitor_view),
            ("systems", self._build_systems_view),
            ("network", self._build_network_view),
            ("processes", self._build_processes_view),
            ("news", self._build_news_view),
            ("terminal", self._build_terminal_view),
            ("settings", self._build_settings_view),
        ):
            view = builder()
            idx = self._view_stack.addWidget(view)
            self._view_indices[key] = idx

        self._view_stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        center_col.addWidget(self._view_stack, stretch=1)


        body.addLayout(center_col, stretch=5)

        self._right_panel = self._build_right_panel()
        body.addWidget(self._right_panel, stretch=0)

        root.addLayout(body, stretch=1)
        self._status_strip = self._build_status_strip()
        root.addWidget(self._status_strip)
        self._theme_bar = self._build_theme_bar()
        root.addWidget(self._theme_bar)
        self._footer = self._build_footer()
        root.addWidget(self._footer)
        self._restyle_chrome()

        self._clock_tmr = QTimer(self)
        self._clock_tmr.timeout.connect(self._tick_clock)
        self._clock_tmr.start(1000)
        self._tick_clock()


        self._metric_tmr = QTimer(self)
        self._metric_tmr.timeout.connect(self._update_metrics)
        self._metric_tmr.start(2000)
        self._update_metrics()

        self._log_sig.connect(self._log.append_log)
        self._state_sig.connect(self._apply_state)
        self._confirm_sig.connect(self._on_confirm_request)

        if getattr(self.hud, "_face_load_error", None):
            self._log.append_log(f"SYS: {self.hud._face_load_error} — using fallback avatar.")

        self._overlay: SetupOverlay | None = None
        self._ready = self._check_config()
        if not self._ready:
            self._show_setup()

        sc_mute = QShortcut(QKeySequence("F4"), self)
        sc_mute.activated.connect(self._toggle_mute)
        sc_full = QShortcut(QKeySequence("F11"), self)
        sc_full.activated.connect(self._toggle_fullscreen)


        self._apply_transparency()

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cw = self.centralWidget()
        if self._overlay and self._overlay.isVisible():
            ow, oh = 460, 390
            self._overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )
        if self._remote_overlay and self._remote_overlay.isVisible():
            ow, oh = RemoteKeyOverlay._OW, RemoteKeyOverlay._OH
            self._remote_overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )

    def _update_metrics(self):
        snap = _metrics.snapshot()


        cpu = snap["cpu"]
        self._gauge_cpu.set_value(cpu, f"{cpu:.0f}%")


        mem = snap["mem"]
        self._gauge_mem.set_value(mem, f"{mem:.0f}%")


        net = snap["net"]
        if net < 1.0:
            net_str = f"{net*1024:.0f}KB/s"
        else:
            net_str = f"{net:.1f}MB/s"
        net_pct = min(100, net * 10)
        self._bar_net.set_value(net_pct, net_str)


        self._status_net.set_value(net_pct, "ONLINE")
        self._status_flow.set_value(net_pct, net_str)
        self._status_mem.set_value(mem, f"{mem:.0f}%")
        self._status_cpu.set_value(cpu, f"{cpu:.0f}%")


        gpu = snap["gpu"]
        if gpu >= 0:
            self._gauge_gpu.set_value(gpu, f"{gpu:.0f}%")
        else:
            self._gauge_gpu.set_value(0, "N/A")


        tmp = snap["tmp"]
        if tmp >= 0:
            tmp_pct = min(100, (tmp / 100) * 100)
            self._bar_tmp.set_value(tmp_pct, f"{tmp:.0f}°C")
            self._status_temp.set_value(tmp_pct, f"{tmp:.0f}°C")
        else:
            self._bar_tmp.set_value(0, "N/A")
            self._status_temp.set_value(0, "N/A")

        try:
            boot_t  = psutil.boot_time()
            elapsed = time.time() - boot_t
            h = int(elapsed // 3600)
            m = int((elapsed % 3600) // 60)
            s = int(elapsed % 60)
            self._uptime_lbl.setText(f"{h:02d}:{m:02d}:{s:02d}")
        except Exception:
            self._uptime_lbl.setText("--:--:--")

        try:
            proc_count = len(psutil.pids())
            self._proc_lbl.setText(str(proc_count))
        except Exception:
            self._proc_lbl.setText("--")


    def _build_header(self) -> QWidget:
        w = HeaderBgWidget()
        w.setFixedHeight(64)
        lay = QHBoxLayout(w)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(14)


        left_box = QHBoxLayout(); left_box.setSpacing(10)
        hexagon = HexagonBadge("R")
        hexagon.setFixedSize(40, 40)
        left_box.addWidget(hexagon)

        left_text = QVBoxLayout(); left_text.setSpacing(1)
        name_lbl = QLabel("RENCORA v7")
        name_lbl.setFont(QFont(FONT_DISPLAY, 11, QFont.Weight.Bold))
        name_lbl.setStyleSheet(f"color: {C.WHITE}; background: transparent;")
        left_text.addWidget(name_lbl)

        brand_lbl = QLabel("RENKER ARTIFICIAL INTELLIGENCE")
        brand_lbl.setFont(QFont(FONT_BODY, 6))
        brand_lbl.setStyleSheet(
            f"color: {C.TEXT_DIM}; background: transparent; letter-spacing: 1px;")
        left_text.addWidget(brand_lbl)

        status_row = QHBoxLayout(); status_row.setSpacing(5)
        status_lbl = QLabel("AI CORE ACTIVE")
        status_lbl.setFont(QFont(FONT_BODY, 7, QFont.Weight.Bold))
        status_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; letter-spacing: 1px;")
        status_row.addWidget(status_lbl)
        self._header_status_dot = StatusDot(C.PRI)
        self._header_status_dot.setFixedSize(7, 7)
        status_row.addWidget(self._header_status_dot)
        status_row.addStretch()
        left_text.addLayout(status_row)

        left_box.addLayout(left_text)
        lay.addLayout(left_box)
        lay.addStretch()

        mid = QVBoxLayout(); mid.setSpacing(2)


        self._sys_online_lbl = QLabel("SYSTEM ONLINE")
        self._sys_online_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sys_online_lbl.setFont(QFont(FONT_DISPLAY, 15, QFont.Weight.Bold))
        try:
            from PyQt6.QtWidgets import QGraphicsDropShadowEffect
            neon = QGraphicsDropShadowEffect(self._sys_online_lbl)
            neon.setBlurRadius(22)
            neon.setOffset(0, 0)
            neon.setColor(qcol(C.PRI, 190))
            self._sys_online_lbl.setGraphicsEffect(neon)
        except Exception:
            pass
        self._sys_online_lbl.setStyleSheet(
            f"color: {C.PRI}; background: transparent; letter-spacing: 6px;")
        mid.addWidget(self._sys_online_lbl)
        self._sys_online_sub = QLabel("ALL  SYSTEMS  OPERATIONAL")
        self._sys_online_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sys_online_sub.setFont(QFont(FONT_BODY, 7))
        self._sys_online_sub.setStyleSheet(
            f"color: {C.PRI_DIM}; background: transparent; letter-spacing: 4px;")
        mid.addWidget(self._sys_online_sub)
        lay.addLayout(mid)
        lay.addStretch()


        icon_row = QHBoxLayout(); icon_row.setSpacing(10)
        bell1 = HeaderIconButton("")
        _pm = svg_icon("bell", C.TEXT_DIM, 16)
        if _pm is not None: bell1.setPixmap(_pm)
        icon_row.addWidget(bell1)
        self._notif_icon = HeaderIconButton("", badge_count=0)
        if _pm is not None: self._notif_icon.setPixmap(_pm)
        icon_row.addWidget(self._notif_icon)
        grid_ic = HeaderIconButton("")
        _pm2 = svg_icon("layout-grid", C.TEXT_DIM, 16)
        if _pm2 is not None: grid_ic.setPixmap(_pm2)
        icon_row.addWidget(grid_ic)
        lay.addLayout(icon_row)

        right_col = QVBoxLayout(); right_col.setSpacing(2)
        self._clock_lbl = QLabel("00:00:00")
        self._clock_lbl.setFont(QFont(FONT_DISPLAY, 13, QFont.Weight.Bold))
        self._clock_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        self._clock_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_col.addWidget(self._clock_lbl)
        self._date_lbl = QLabel("")
        self._date_lbl.setFont(QFont(FONT_BODY, 7))
        self._date_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        self._date_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_col.addWidget(self._date_lbl)
        lay.addLayout(right_col)


        sec_row = QHBoxLayout(); sec_row.setSpacing(6)
        sec_icon = QLabel()
        _pm3 = svg_icon("shield-check", "#22c55e", 18)
        if _pm3 is not None:
            sec_icon.setPixmap(_pm3)
        else:
            sec_icon.setText("")
        sec_icon.setStyleSheet("background: transparent;")
        sec_row.addWidget(sec_icon)
        sec_text_col = QVBoxLayout(); sec_text_col.setSpacing(0)
        sec_label = QLabel("SECURITY STATUS")
        sec_label.setFont(QFont(FONT_BODY, 6))
        sec_label.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        sec_text_col.addWidget(sec_label)
        self._security_value_lbl = QLabel("CLEARED")
        self._security_value_lbl.setFont(QFont(FONT_BODY, 9, QFont.Weight.Bold))
        self._security_value_lbl.setStyleSheet("color: #22c55e; background: transparent;")
        sec_text_col.addWidget(self._security_value_lbl)
        sec_row.addLayout(sec_text_col)
        lay.addLayout(sec_row)


        win_col = QHBoxLayout(); win_col.setSpacing(4)
        for glyph, tip, cb in (
            ("—", "Minimieren", self.showMinimized),
            ("", "Beenden", self.close),
        ):
            b = QPushButton(glyph)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setToolTip(tip)
            b.setFixedSize(24, 24)
            hover_col = "#ff5566" if glyph == "" else "#ffffff"
            b.setStyleSheet(
                f"QPushButton {{ background: transparent; color: {C.TEXT_DIM}; "
                f"border: none; font-size: 11pt; }}"
                f"QPushButton:hover {{ color: {hover_col}; }}")
            b.clicked.connect(cb)
            win_col.addWidget(b)
        lay.addLayout(win_col)

        return w

    def _tick_clock(self):
        self._clock_lbl.setText(time.strftime("%H:%M:%S"))
        self._date_lbl.setText(time.strftime("%a %d %b %Y"))

    def _build_nav_panel(self) -> QWidget:
        """
        Schmale Navigationsleiste links (Dashboard/Monitor/Systems/
        Network/Processes/Upload/Terminal/Settings) — siehe Referenz-
        Dashboard. Steht als eigene Spalte VOR dem bestehenden
        SYS-MONITOR-Panel, nicht darin.
        """
        w = QWidget()
        w.setFixedWidth(132)
        w.setStyleSheet(f"background: {C.DARK}; border-right: 1px solid {C.BORDER};")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(6, 12, 6, 12)
        lay.setSpacing(3)

        entries = [
            ("house", "DASHBOARD", "dashboard"),
            ("activity", "MONITOR", "monitor"),
            ("boxes", "SYSTEMS", "systems"),
            ("globe", "NETWORK", "network"),
            ("cpu", "PROCESSES", "processes"),
            ("newspaper", "NEWS", "news"),
            ("upload", "UPLOAD", "upload"),
            ("square-terminal", "TERMINAL", "terminal"),
            ("settings", "SETTINGS", "settings"),
        ]
        self._nav_buttons: dict[str, NavButton] = {}
        for icon, label, key in entries:
            btn = NavButton(icon, label, key)
            btn.clicked.connect(self._on_nav_clicked)
            lay.addWidget(btn)
            self._nav_buttons[key] = btn

        self._nav_buttons["dashboard"].set_active(True)
        lay.addStretch()
        return w

    def _browse_file(self) -> None:
        """Öffnet denselben Datei-Dialog wie die FILE UPLOAD-Drop-Zone, ausgelöst über die UPLOAD-Sidebar-Navigation."""
        self._drop_zone._browse()

    def _on_nav_clicked(self, key: str) -> None:
        """
        Hebt den geklickten Navigationspunkt hervor und schaltet die
        zentrale Ansicht entsprechend um (siehe self._view_stack,
        self._view_indices). "upload" ist ein Sonderfall: öffnet direkt
        den bestehenden Datei-Dialog statt die Ansicht zu wechseln, da
        es bereits eine eigene Drop-Zone im rechten Panel gibt.
        """
        if key == "upload":
            self._browse_file()


            return

        for btn_key, btn in self._nav_buttons.items():
            btn.set_active(btn_key == key)

        idx = self._view_indices.get(key)
        if idx is not None:
            self._view_stack.setCurrentIndex(idx)
            if key in ("monitor", "processes"):
                self._refresh_monitor_view(key)
            elif key == "news":
                self._load_news(self._news_country)

    def _build_news_view(self) -> QWidget:
        """
        WELT-NETZ Nachrichten-Terminal: dieselbe Engine wie Web-Dashboard und
        Mobile-App (core/news_engine.py) — mehrere Quellen pro Land quer
        durchs politische Spektrum, feste Bias-Einstufung, deutsche
        Uebersetzung. Klick auf eine Schlagzeile oeffnet den Artikel im
        Browser.
        """
        self._news_country = "de"
        self._news_sig.connect(self._on_news_loaded)

        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        lay.addWidget(SectionHeader("WELT-NETZ  //  NACHRICHTEN", badge="LIVE"))

        country_row = QHBoxLayout(); country_row.setSpacing(6)
        self._news_country_btns: dict[str, QPushButton] = {}
        for code, name in (("de", "DEUTSCHLAND"), ("us", "USA"),
                           ("ru", "RUSSLAND"), ("cn", "CHINA")):
            b = QPushButton(name)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, c=code: self._load_news(c))
            self._news_country_btns[code] = b
            country_row.addWidget(b)
        country_row.addStretch()
        lay.addLayout(country_row)
        self._style_news_country_btns()

        self._news_status = QLabel("")
        self._news_status.setFont(QFont(FONT_BODY, 8))
        self._news_status.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        lay.addWidget(self._news_status)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            f"QScrollArea {{ background: transparent; border: none; }}"
            f"QScrollBar:vertical {{ background: {C.BG}; width: 8px; border: none; }}"
            f"QScrollBar::handle:vertical {{ background: {C.BORDER_B}; border-radius: 4px; min-height: 20px; }}"
        )
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        self._news_list_lay = QVBoxLayout(container)
        self._news_list_lay.setContentsMargins(0, 0, 6, 0)
        self._news_list_lay.setSpacing(6)
        self._news_list_lay.addStretch()
        scroll.setWidget(container)
        lay.addWidget(scroll, stretch=1)

        return w

    def _style_news_country_btns(self) -> None:
        for code, b in self._news_country_btns.items():
            active = code == self._news_country
            col = C.PRI if active else C.TEXT_DIM
            bg = C.PRI_GHO if active else C.PANEL
            b.setStyleSheet(
                f"QPushButton {{ background: {bg}; color: {col}; "
                f"border: 1px solid {col}; padding: 5px 12px; "
                f"font-family: 'Rajdhani'; font-size: 8pt; "
                f"font-weight: bold; letter-spacing: 1px; }}"
            )

    def _load_news(self, country: str) -> None:
        self._news_country = country
        self._style_news_country_btns()
        self._news_status.setText("Lade Meldungen ...")

        def _worker():
            try:
                from core.news_engine import fetch_news
                items = fetch_news(country)
            except Exception:
                items = []
            self._news_sig.emit(country, items)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_news_loaded(self, country: str, items: list) -> None:
        if country != self._news_country:
            return

        while self._news_list_lay.count() > 1:
            child = self._news_list_lay.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if not items:
            self._news_status.setText("Keine Meldungen gefunden (offline?).")
            return
        self._news_status.setText(f"{len(items)} Meldungen — Quellen quer durchs politische Spektrum, Klick oeffnet Artikel.")

        for n in items:
            frame = ChamferFrame(border_color=C.BORDER, bg=C.PANEL2, chamfer=6)
            fl = frame.layout_box()
            fl.setContentsMargins(10, 7, 10, 7)
            fl.setSpacing(3)

            bias_color = n.get("bias_color", C.TEXT_MED)
            head = QLabel(
                f'<span style="color:{C.TEXT_DIM}; letter-spacing:1px;">{n.get("source","")}</span>'
                f'&nbsp;&nbsp;<span style="color:{bias_color}; font-weight:bold;">'
                f'[{n.get("bias","").upper()}]</span>'
            )
            head.setFont(QFont(FONT_BODY, 7))
            head.setStyleSheet("background: transparent;")
            fl.addWidget(head)

            title = QLabel(
                f'<a href="{n.get("link","")}" style="color:{C.TEXT}; text-decoration:none;">'
                f'{n.get("title","")}</a>'
            )
            title.setFont(QFont(FONT_BODY, 9))
            title.setWordWrap(True)
            title.setOpenExternalLinks(True)
            title.setStyleSheet("background: transparent;")
            fl.addWidget(title)

            if n.get("original_title"):
                orig = QLabel(f'Original: {n["original_title"]}')
                orig.setFont(QFont(FONT_BODY, 7))
                orig.setWordWrap(True)
                orig.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; font-style: italic;")
                fl.addWidget(orig)

            self._news_list_lay.insertWidget(self._news_list_lay.count() - 1, frame)

    def _build_terminal_view(self) -> QWidget:
        """
        Echtes Terminal: führt eingegebene Befehle tatsächlich über
        subprocess aus und zeigt die reale Ausgabe an. Läuft mit den
        Rechten des RENCORA-Prozesses selbst — siehe Sicherheitshinweis
        in _run_terminal_command().
        """
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        frame = ChamferFrame(border_color=C.BORDER, bg=C.PANEL, chamfer=8)
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        flay = frame.layout_box()
        flay.setContentsMargins(8, 8, 8, 8)

        self._terminal_output = QPlainTextEdit()
        self._terminal_output.setReadOnly(True)


        self._terminal_output.setFont(QFont("Consolas", 9))
        self._terminal_output.setStyleSheet(
            f"background: {C.BG}; color: {C.PRI}; border: none;"
        )
        self._terminal_output.setPlainText(
            f"RENCORA TERMINAL — {_OS}\n"
            f"Befehle laufen mit den Rechten dieses Prozesses. Mit Vorsicht verwenden.\n"
        )
        flay.addWidget(self._terminal_output, stretch=1)

        input_row = QHBoxLayout(); input_row.setSpacing(6)
        prompt_lbl = QLabel(">")
        prompt_lbl.setFont(QFont(FONT_BODY, 10, QFont.Weight.Bold))
        prompt_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        input_row.addWidget(prompt_lbl)

        self._terminal_input = QLineEdit()
        self._terminal_input.setFont(QFont(FONT_BODY, 10))
        self._terminal_input.setStyleSheet(
            f"background: {C.PANEL2}; color: {C.TEXT}; border: 1px solid {C.BORDER}; padding: 4px;"
        )
        self._terminal_input.setPlaceholderText("Befehl eingeben und Enter drücken…")
        self._terminal_input.returnPressed.connect(self._run_terminal_command)
        input_row.addWidget(self._terminal_input, stretch=1)
        flay.addLayout(input_row)

        lay.addWidget(frame, stretch=1)
        return w

    def _run_terminal_command(self) -> None:
        cmd = self._terminal_input.text().strip()
        if not cmd:
            return
        self._terminal_input.clear()
        self._terminal_output.appendPlainText(f"\n> {cmd}")
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=15, **_WIN_NO_WINDOW
            )
            output = result.stdout or ""
            if result.stderr:
                output += result.stderr
            self._terminal_output.appendPlainText(output.rstrip() or "(keine Ausgabe)")
        except subprocess.TimeoutExpired:
            self._terminal_output.appendPlainText("FEHLER: Befehl nach 15s abgebrochen (Timeout).")
        except Exception as e:
            self._terminal_output.appendPlainText(f"FEHLER: {e}")

    def _build_monitor_view(self) -> QWidget:
        """Detailansicht für laufende Prozesse, sortiert nach CPU-Auslastung — echte psutil-Daten."""
        view, tree = self._build_process_tree_widget()
        self._monitor_tree = tree
        return view

    def _build_processes_view(self) -> QWidget:
        """
        Eigene Baumansicht für PROCESSES (siehe _build_monitor_view).
        WICHTIG: Nutzt eine eigene Tree-Referenz (self._processes_tree),
        NICHT dieselbe wie self._monitor_tree — sonst überschreibt der
        zweite Aufruf von _build_process_tree_widget() die Referenz auf
        den ersten (bereits im Stack sichtbaren) Baum, und 'MONITOR'
        bliebe dauerhaft leer, da _refresh_monitor_view() dann den
        falschen, unsichtbaren Baum befüllt (echter Bug, beim Testen
        gefunden: die Tabelle zeigte nur Spaltenköpfe, nie Zeilen).
        """
        view, tree = self._build_process_tree_widget()
        self._processes_tree = tree
        return view

    def _build_process_tree_widget(self) -> tuple[QWidget, "QTreeWidget"]:
        """Gemeinsamer Aufbau für Monitor- und Processes-Ansicht; gibt (Widget, TreeWidget) zurück."""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)

        frame = ChamferFrame(border_color=C.BORDER, bg=C.PANEL, chamfer=8)
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        flay = frame.layout_box()
        flay.setContentsMargins(8, 8, 8, 8)

        tree = QTreeWidget()
        tree.setHeaderLabels(["PID", "PROCESS", "CPU %", "MEM %"])
        tree.setRootIsDecorated(False)
        tree.setStyleSheet(
            f"QTreeWidget {{ background: {C.BG}; color: {C.TEXT}; border: none; }}"
            f"QHeaderView::section {{ background: {C.PANEL2}; color: {C.PRI}; border: none; padding: 4px; }}"
        )
        tree.setFont(QFont(FONT_BODY, 8))
        flay.addWidget(tree)

        lay.addWidget(frame, stretch=1)
        return w, tree

    def _refresh_monitor_view(self, key: str = "monitor") -> None:
        """Füllt die aktuell sichtbare Monitor- oder Processes-Baumansicht mit echten, aktuellen psutil-Prozessdaten."""
        tree = getattr(self, "_monitor_tree" if key == "monitor" else "_processes_tree", None)
        if tree is None:
            return
        tree.clear()
        try:
            procs = sorted(
                psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]),
                key=lambda p: p.info.get("cpu_percent") or 0,
                reverse=True,
            )
        except Exception:
            return
        for proc in procs[:60]:
            info = proc.info
            item = QTreeWidgetItem([
                str(info.get("pid", "")),
                str(info.get("name", "") or "?"),
                f"{info.get('cpu_percent') or 0:.1f}",
                f"{info.get('memory_percent') or 0:.1f}",
            ])
            tree.addTopLevelItem(item)

    def _build_systems_view(self) -> QWidget:
        """Übersicht über Datenträger (Speicherplatz pro Laufwerk) — echte psutil-Daten."""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        header = SectionHeader("STORAGE")
        lay.addWidget(header)

        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
            except (PermissionError, OSError):
                continue
            box = ChamferFrame(border_color=C.BORDER, bg=C.PANEL2, chamfer=6)
            blay = box.layout_box()
            blay.setContentsMargins(10, 8, 10, 8)
            title = QLabel(f"{part.device}  ({part.mountpoint})")
            title.setFont(QFont(FONT_BODY, 9, QFont.Weight.Bold))
            title.setStyleSheet(f"color: {C.TEXT}; background: transparent;")
            blay.addWidget(title)
            bar = QProgressBar()
            bar.setMaximum(100)
            bar.setValue(int(usage.percent))
            bar.setFormat(f"{usage.used // (1024**3)}GB / {usage.total // (1024**3)}GB  (%p%)")
            bar.setStyleSheet(
                f"QProgressBar {{ background: {C.BAR_BG}; color: {C.TEXT}; border: 1px solid {C.BORDER}; }}"
                f"QProgressBar::chunk {{ background: {C.PRI}; }}"
            )
            blay.addWidget(bar)
            lay.addWidget(box)

        lay.addStretch()
        return w

    def _build_network_view(self) -> QWidget:
        """Übersicht über Netzwerkschnittstellen mit IO-Zählern — echte psutil-Daten."""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        lay.addWidget(SectionHeader("Network Interfaces"))

        frame = ChamferFrame(border_color=C.BORDER, bg=C.PANEL, chamfer=8)
        flay = frame.layout_box()
        flay.setContentsMargins(8, 8, 8, 8)

        tree = QTreeWidget()
        tree.setHeaderLabels(["INTERFACE", "SENT", "RECEIVED"])
        tree.setRootIsDecorated(False)
        tree.setStyleSheet(
            f"QTreeWidget {{ background: {C.BG}; color: {C.TEXT}; border: none; }}"
            f"QHeaderView::section {{ background: {C.PANEL2}; color: {C.PRI}; border: none; padding: 4px; }}"
        )
        tree.setFont(QFont(FONT_BODY, 8))
        try:
            for name, counters in psutil.net_io_counters(pernic=True).items():
                tree.addTopLevelItem(QTreeWidgetItem([
                    name,
                    f"{counters.bytes_sent / (1024**2):.1f} MB",
                    f"{counters.bytes_recv / (1024**2):.1f} MB",
                ]))
        except Exception:
            pass
        flay.addWidget(tree)
        lay.addWidget(frame, stretch=1)
        return w

    def _build_settings_view(self) -> QWidget:
        """Einstellungen: System-Info + Farbschema-Engine mit speicherbaren Profilen."""
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        outer.addWidget(SectionHeader("Settings"))

        try:
            from core.version import VERSION as _app_version
        except Exception:
            _app_version = "?"

        box = ChamferFrame(border_color=C.BORDER, bg=C.PANEL2, chamfer=6)
        blay = box.layout_box()
        blay.setContentsMargins(12, 10, 12, 10)
        for label, value in (
            ("VERSION", f"RENCORA v7  ·  build {_app_version}"),
            ("OS", _OS),
            ("PYTHON", platform.python_version()),
            ("CONFIG FILE", "core/config/api_keys.json"),
        ):
            row = QHBoxLayout()
            l = QLabel(label)
            l.setFont(QFont(FONT_BODY, 8))
            l.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
            row.addWidget(l)
            row.addStretch()
            v = QLabel(str(value))
            v.setFont(QFont(FONT_BODY, 8, QFont.Weight.Bold))
            v.setStyleSheet(f"color: {C.TEXT}; background: transparent;")
            row.addWidget(v)
            blay.addLayout(row)

        upd_btn = QPushButton("NACH UPDATES SUCHEN")
        upd_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        upd_btn.setStyleSheet(
            f"QPushButton {{ background: {C.PANEL}; color: {C.TEXT_MED}; "
            f"border: 1px solid {C.BORDER}; padding: 5px 10px; "
            f"font-family: 'Rajdhani'; font-size: 8pt; letter-spacing: 1px; }}"
            f"QPushButton:hover {{ color: {C.PRI}; border-color: {C.PRI}; }}"
        )
        upd_btn.clicked.connect(self._on_check_update)
        blay.addWidget(upd_btn)
        outer.addWidget(box)


        outer.addWidget(SectionHeader("KI-Modell (Text / Agent)"))
        model_box = ChamferFrame(border_color=C.BORDER, bg=C.PANEL2, chamfer=6)
        mlay = model_box.layout_box()
        mlay.setContentsMargins(12, 10, 12, 10)
        mlay.setSpacing(6)

        self._model_combo = QComboBox()
        self._model_combo.addItem("Lokales Ollama (Standard)", "ollama")
        self._model_combo.addItem("RencoraLM v3 - eigenes Modell (GPU-Server)", "rencoralm-v3")
        self._model_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._model_combo.setStyleSheet(
            f"QComboBox {{ background: {C.PANEL}; color: {C.TEXT}; "
            f"border: 1px solid {C.BORDER}; padding: 5px 10px; "
            f"font-family: 'Rajdhani'; font-size: 9pt; letter-spacing: 1px; }}"
            f"QComboBox:hover {{ border-color: {C.PRI}; }}"
            f"QComboBox::drop-down {{ border: none; width: 22px; }}"
            f"QComboBox QAbstractItemView {{ background: {C.PANEL2}; color: {C.TEXT}; "
            f"selection-background-color: {C.PRI}; border: 1px solid {C.BORDER}; "
            f"outline: none; }}"
        )
        self._model_combo.setCurrentIndex(self._aktuelles_modell_index())
        self._model_combo.activated.connect(self._on_modell_gewaehlt)
        mlay.addWidget(self._model_combo)

        mhint = QLabel(
            "Modell fuer Text- und Agentenantworten. Die Stimme/Hauptantwort\n"
            "laeuft weiter ueber Gemini (davon unabhaengig). RencoraLM v3 ist das\n"
            "eigene, lokale Modell - der Server startet beim Umschalten selbst; es\n"
            "ist ein Textfortsetzer und folgt keinen Werkzeug-Befehlen.")
        mhint.setFont(QFont(FONT_BODY, 8))
        mhint.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        mhint.setWordWrap(True)
        mlay.addWidget(mhint)
        outer.addWidget(model_box)


        outer.addWidget(SectionHeader("Farbschema"))
        theme_box = ChamferFrame(border_color=C.BORDER, bg=C.PANEL2, chamfer=6)
        tlay = theme_box.layout_box()
        tlay.setContentsMargins(12, 10, 12, 10)
        hint = QLabel(
            "Theme-Presets, Akzentfarben, eigener Farbwaehler (CUSTOM COLOR),\n"
            "Glow/Animations-Schalter und Transparenz findest du in der\n"
            "APPEARANCE & THEME-Leiste am unteren Fensterrand.")
        hint.setFont(QFont(FONT_BODY, 8))
        hint.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        hint.setWordWrap(True)
        tlay.addWidget(hint)
        outer.addWidget(theme_box)
        outer.addStretch()
        return w

    def _aktuelles_modell_index(self) -> int:
        """Liest die aktuelle Provider-Wahl aus api_keys.json (0=Ollama, 1=v3)."""
        try:
            d = json.loads(API_FILE.read_text(encoding="utf-8"))
        except Exception:
            return 0
        prov = str(d.get("llm_provider", "ollama")).strip().lower()
        model = str(d.get("llm_model", "")).strip().lower()
        if prov in ("openai", "lmstudio", "localai", "jan", "llamacpp") and model == "rencoralm-v3":
            return 1
        return 0

    def _on_modell_gewaehlt(self, index: int) -> None:
        """Schreibt die Modellwahl nach api_keys.json (laden->aendern->speichern,
        damit gemini_api_key & Co. erhalten bleiben). Greift ab der naechsten
        Text-/Agentenanfrage — die App liest die Config bei jedem Aufruf frisch."""
        preset = self._model_combo.itemData(index)
        try:
            d = json.loads(API_FILE.read_text(encoding="utf-8")) if API_FILE.exists() else {}
        except Exception:
            d = {}
        if preset == "rencoralm-v3":
            d["llm_provider"] = "openai"
            d["llm_url"] = "http://127.0.0.1:5151"
            d["llm_model"] = "rencoralm-v3"
        else:
            for k in ("llm_provider", "llm_url", "llm_model"):
                d.pop(k, None)
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            API_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            self._log.append_log(f"SYS: Modellwechsel fehlgeschlagen: {e}")
            return
        if preset == "rencoralm-v3":
            self._log.append_log("SYS: Modell -> RencoraLM v3. Pruefe GPU-Server ...")
            self._pruefe_v3_server()
        else:
            self._log.append_log("SYS: Modell -> lokales Ollama (Standard). Greift ab naechster Nachricht.")

    def _pruefe_v3_server(self) -> None:
        """Health-Check auf den v3-Server; startet ihn bei Bedarf selbst."""
        def _health() -> bool:
            import urllib.request
            try:
                with urllib.request.urlopen("http://127.0.0.1:5151/health", timeout=2) as r:
                    return getattr(r, "status", 200) == 200
            except Exception:
                return False

        def _worker():
            if _health():
                self._log_sig.emit("SYS: v3-Server erreichbar. Neue Nachrichten nutzen RencoraLM v3.")
                return
            if not self._starte_v3_server():
                self._log_sig.emit(
                    "WRN: v3-Server nicht erreichbar und Python nicht gefunden — "
                    "Start_RencoraLM_v3_Server.bat manuell ausfuehren.")
                return
            self._log_sig.emit("SYS: Starte v3-Server ...")
            for _ in range(30):
                time.sleep(1.0)
                if _health():
                    self._log_sig.emit("SYS: v3-Server bereit. Neue Nachrichten nutzen RencoraLM v3.")
                    return
            self._log_sig.emit("WRN: v3-Server antwortete nicht rechtzeitig.")
        threading.Thread(target=_worker, daemon=True).start()

    def _starte_v3_server(self) -> bool:
        """Startet tools/rencora_lm_server.py im Hintergrund. Nutzt den laufenden
        Interpreter (Entwicklung) oder Python von PATH (installierte .exe)."""
        import shutil
        script = BASE_DIR / "tools" / "rencora_lm_server.py"
        if not script.exists():
            return False
        py = sys.executable if not getattr(sys, "frozen", False) else None
        py = py or shutil.which("python") or shutil.which("py")
        if not py:
            return False
        try:
            subprocess.Popen([py, str(script), "--port", "5151"], cwd=str(BASE_DIR))
            return True
        except Exception:
            return False

    def _on_check_update(self) -> None:
        """Update-Pruefung im Hintergrund-Thread — Netz darf die UI nicht blockieren."""
        self._log.append_log("SYS: Suche nach Updates ...")

        def _worker():
            try:
                from core.version import check_for_update
                result = check_for_update()
            except Exception as e:
                result = {"status": "error", "detail": str(e)}
            status = result.get("status")
            if status == "no_source":
                msg = ("SYS: Keine Update-Quelle konfiguriert "
                       "(config/api_keys.json -> 'update_url').")
            elif status == "up_to_date":
                msg = f"SYS: Rencora ist aktuell (v{result['version']})."
            elif status == "update":
                msg = (f"SYS: Update verfuegbar: v{result['version']} — "
                       f"Download wird im Browser geoeffnet.")
                if result.get("download_url"):
                    import webbrowser
                    webbrowser.open(result["download_url"])
            else:
                msg = f"SYS: Update-Pruefung fehlgeschlagen: {result.get('detail', '?')}"
            self._log_sig.emit(msg)

        threading.Thread(target=_worker, daemon=True).start()

    def _build_left_panel(self) -> QWidget:
        w = QWidget()
        w.setFixedWidth(_LEFT_W)
        w.setStyleSheet(f"background: {C.DARK}; border-right: 1px solid {C.BORDER};")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 10, 8, 10)
        lay.setSpacing(6)

        lay.addWidget(SectionHeader("System Monitor"))
        lay.addSpacing(2)

        self._gauge_cpu = CircularGauge("CPU", C.PRI)
        self._gauge_mem = CircularGauge("MEM", C.GREEN_D)
        self._gauge_gpu = CircularGauge("GPU", "#39ff14")
        gauge_row = QHBoxLayout()
        gauge_row.setSpacing(2)
        for g in (self._gauge_cpu, self._gauge_mem, self._gauge_gpu):
            gauge_row.addWidget(g)
        lay.addLayout(gauge_row)

        self._bar_net = MetricBar("NET", C.GREEN,    filled=False)
        self._bar_tmp = MetricBar("TMP", "#88ff44",  show_graph=False)

        for bar in [self._bar_net, self._bar_tmp]:
            lay.addWidget(bar)

        lay.addSpacing(4)

        lay.addSpacing(4)
        lay.addWidget(SectionHeader("System Overview"))
        lay.addSpacing(2)

        info_panel = ChamferFrame(border_color=C.BORDER, bg=C.PANEL2, chamfer=6)
        ip_lay = info_panel.layout_box()
        ip_lay.setContentsMargins(8, 6, 8, 6)
        ip_lay.setSpacing(5)

        def _overview_row(label: str, value: str, value_color: str = C.TEXT_MED) -> tuple[QLabel, QHBoxLayout]:
            row = QHBoxLayout(); row.setSpacing(6)
            dot = StatusDot(C.PRI)
            dot.setFixedSize(5, 5)
            row.addWidget(dot)
            l = QLabel(label)
            l.setFont(QFont(FONT_BODY, 7))
            l.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
            row.addWidget(l)
            row.addStretch()
            v = QLabel(value)
            v.setFont(QFont(FONT_BODY, 8, QFont.Weight.Bold))
            v.setStyleSheet(f"color: {value_color}; background: transparent; border: none;")
            row.addWidget(v)
            return v, row

        self._uptime_lbl, row_uptime = _overview_row("UPTIME", "00:00:00", C.GREEN)
        ip_lay.addLayout(row_uptime)

        self._proc_lbl, row_proc = _overview_row("PROCESSES", "--", C.TEXT_MED)
        ip_lay.addLayout(row_proc)

        os_name = {"Windows": "WIN 11 PRO", "Darwin": "macOS", "Linux": "LINUX"}.get(_OS, _OS.upper())
        _, row_os = _overview_row("OS", os_name, C.ACC2)
        ip_lay.addLayout(row_os)

        _, row_user = _overview_row("USER", "Rencora_AI", C.TEXT)
        ip_lay.addLayout(row_user)

        _, row_proto = _overview_row("AI PROTOCOL", "V1.0.0", C.PRI)
        ip_lay.addLayout(row_proto)

        lay.addWidget(info_panel)
        lay.addStretch()

        for txt, col, bg in [
            ("AI CORE\nACTIVE",     C.GREEN,    C.PANEL2),
            ("SECURITY\nCLEARED",   C.PRI,      C.PANEL2),
            ("PROTOCOL\nRENKER V1", C.TEXT_DIM, C.PANEL2),
        ]:
            box = ChamferFrame(border_color=col, bg=bg, chamfer=6)
            bl = box.layout_box()
            bl.setContentsMargins(4, 8, 4, 8)
            lbl = QLabel(txt)
            lbl.setFont(QFont(FONT_BODY, 7, QFont.Weight.Bold))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"color: {col}; background: transparent; border: none;")
            bl.addWidget(lbl)
            lay.addWidget(box)

        return w
    def _build_right_panel(self) -> QWidget:
        w = QWidget()
        w.setFixedWidth(_RIGHT_W)
        w.setStyleSheet(f"background: {C.DARK}; border-left: 1px solid {C.BORDER};")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        lay.addWidget(SectionHeader("Activity Log", badge="LIVE"))
        log_frame = ChamferFrame(border_color=C.BORDER, bg=C.PANEL, chamfer=8)
        lf_lay = log_frame.layout_box()
        lf_lay.setContentsMargins(4, 4, 4, 4)
        self._log = LogWidget()
        lf_lay.addWidget(self._log)
        lay.addWidget(log_frame, stretch=1)

        view_full_log = QLabel("VIEW FULL LOG  ›")
        view_full_log.setFont(QFont(FONT_BODY, 7, QFont.Weight.Bold))
        view_full_log.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent; padding: 2px 4px;")
        view_full_log.setCursor(Qt.CursorShape.PointingHandCursor)
        view_full_log.setAlignment(Qt.AlignmentFlag.AlignRight)
        lay.addWidget(view_full_log)

        lay.addWidget(SectionHeader("File Upload"))
        self._drop_zone = FileDropZone()
        self._drop_zone.file_selected.connect(self._on_file_selected)
        lay.addWidget(self._drop_zone)

        self._file_hint = QLabel("No file loaded — drop or click above to upload")
        self._file_hint.setFont(QFont(FONT_BODY, 7))
        self._file_hint.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        self._file_hint.setWordWrap(True)
        lay.addWidget(self._file_hint)

        lay.addWidget(SectionHeader("Command Input"))
        lay.addLayout(self._build_input_row())

        self._mute_btn = ChamferButton("mic", "MIC\nMUTED", C.GREEN)
        self._mute_btn.clicked.connect(self._toggle_mute)
        self._style_mute_btn()

        remote_btn = ChamferButton("cast", "REMOTE\nCONTROL", C.PRI)
        remote_btn.clicked.connect(self._open_remote)

        self._hologram_btn = ChamferButton("box", "HOLOGRAM\nMODE", C.TEXT_MED)
        self._hologram_btn.clicked.connect(self._toggle_hologram)
        self._hologram_btn.set_active(False)

        fs_btn = ChamferButton("maximize", "FULLSCREEN\nHUD", C.TEXT_MED)
        fs_btn.clicked.connect(self._toggle_fullscreen)


        btn_grid = QGridLayout()
        btn_grid.setSpacing(6)
        for btn in (self._mute_btn, remote_btn, self._hologram_btn, fs_btn):
            btn.setFixedHeight(48)
        btn_grid.addWidget(self._mute_btn, 0, 0)
        btn_grid.addWidget(remote_btn, 0, 1)
        btn_grid.addWidget(self._hologram_btn, 1, 0)
        btn_grid.addWidget(fs_btn, 1, 1)
        lay.addLayout(btn_grid)

        return w

    def _toggle_hologram(self) -> None:
        """HOLOGRAM MODE — verbindet/trennt die bestehende Bruecke zum
        Neural Hologram OS (core/hologram_bridge.py). Ohne laufendes
        Hologramm-Programm meldet der Log sauber den Fehlschlag."""
        self._hologram_mode = not getattr(self, "_hologram_mode", False)
        try:
            from core.hologram_bridge import hologram_bridge
            if self._hologram_mode:
                hologram_bridge.start()
                self._hologram_btn.set_active(True, C.PRI)
                self._log.append_log("SYS: Hologram mode enabled — connecting to Neural Hologram OS.")
            else:
                hologram_bridge.stop()
                self._hologram_btn.set_active(False)
                self._log.append_log("SYS: Hologram mode disabled.")
        except Exception as e:
            self._hologram_mode = False
            self._hologram_btn.set_active(False)
            self._log.append_log(f"SYS: Hologram mode unavailable ({e}).")

    def _restyle_chrome(self) -> None:
        """Setzt die Stylesheet-Hintergruende der Rahmen-Widgets mit dem
        aktuellen Panel-Alpha neu — so scheint bei niedriger Transparenz der
        Desktop durch die Flaechen, waehrend Text/Rahmen deckend bleiben."""
        self._central.setStyleSheet(f"background: {rgba(C.BG)};")
        side = f"background: {rgba(C.DARK)}; border-right: 1px solid {C.BORDER};"
        self._nav_panel.setStyleSheet(side)
        self._left_panel.setStyleSheet(side)
        band = f"background: {rgba(C.DARK)}; border-top: 1px solid {C.BORDER};"
        self._status_strip.setStyleSheet(band)
        self._theme_bar.setStyleSheet(band)
        self._footer.setStyleSheet(band)

    def _set_transparency_preview(self, pct: int) -> None:
        """Live-Vorschau der Panel-Transparenz (Text bleibt deckend)."""
        set_panel_alpha(pct)
        self._restyle_chrome()
        for widget in self.findChildren(QWidget):
            widget.update()

    def _apply_transparency(self) -> None:
        """
        Persistierte Basis-Transparenz anwenden: Panel-Alpha aus den
        gespeicherten Einstellungen (>= 20% geklemmt); der Transparent-/
        Away-Modus multipliziert zusaetzlich die Gesamt-Fensteropazitaet
        mit 0.8 (bestehendes Verhalten, wirkt relativ zur Basis).
        """
        pct = 100
        if _theme_manager is not None:
            try:
                pct = _theme_manager.get_settings()["transparency_pct"]
            except Exception:
                pass
        self._set_transparency_preview(pct)
        self.setWindowOpacity(0.8 if getattr(self, "_transparent_mode", False) else 1.0)


    def mousePressEvent(self, e):
        if (e.button() == Qt.MouseButton.LeftButton
                and e.position().y() <= 66 and not self.isFullScreen()):
            self._drag_offset = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
        else:
            self._drag_offset = None
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if (getattr(self, "_drag_offset", None) is not None
                and e.buttons() & Qt.MouseButton.LeftButton):
            self.move(e.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._drag_offset = None
        super().mouseReleaseEvent(e)

    def _toggle_transparent(self) -> None:
        """Transparent-Modus (frueher eigener Button, heute nur noch intern/
        per Shortcut nutzbar) — multipliziert sich mit der Basis-Transparenz
        aus der Theme-Leiste, siehe _apply_transparency()."""
        self._transparent_mode = not getattr(self, "_transparent_mode", False)
        self._apply_transparency()
        self._log.append_log(
            "SYS: Transparent mode enabled." if self._transparent_mode
            else "SYS: Transparent mode disabled.")

    def _on_security_clear(self) -> None:
        """Bestätigt den Sicherheitsstatus erneut (siehe Top-Bar 'SECURITY STATUS')."""
        self._log.append_log("SYS: Security status cleared.")
        if hasattr(self, "_security_value_lbl"):
            self._security_value_lbl.setText("CLEARED")

    def _build_input_row(self) -> QHBoxLayout:
        row = QHBoxLayout(); row.setSpacing(5)
        self._input = QLineEdit()
        self._input.setPlaceholderText("Type a command or question…")
        self._input.setFont(QFont(FONT_BODY, 9))
        self._input.setFixedHeight(30)
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: #000d14; color: {C.WHITE};
                border: 1px solid {C.BORDER}; border-radius: 3px; padding: 3px 7px;
            }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
        """)
        self._input.returnPressed.connect(self._send)
        row.addWidget(self._input)

        send = QPushButton("▸")
        send.setFixedSize(30, 30)
        send.setFont(QFont(FONT_BODY, 11, QFont.Weight.Bold))
        send.setCursor(Qt.CursorShape.PointingHandCursor)
        send.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL}; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 3px;
            }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border: 1px solid {C.PRI}; }}
        """)
        send.clicked.connect(self._send)
        row.addWidget(send)
        return row

    def _build_status_strip(self) -> QWidget:
        """
        Untere Statusleiste mit Mini-Graphen — siehe Referenz-Dashboard:
        NET STATUS / CONNECTION / DATA FLOW / MEMORY / CPU LOAD, jeweils
        mit eigenem Sparkline-Verlauf. Wird in _update_metrics() mit den
        bereits vorhandenen CPU/MEM/NET-Werten gefüttert.
        """
        w = QWidget()
        w.setFixedHeight(48)
        w.setStyleSheet(f"background: {C.DARK}; border-top: 1px solid {C.BORDER};")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(14, 4, 14, 4)
        lay.setSpacing(18)

        self._status_net = StatusStripItem("globe", "NETWORK STATUS", C.GREEN)
        self._status_map = GlobalNodeMapWidget()
        self._status_flow = StatusStripItem("activity", "DATA FLOW", "#00d9ff")
        self._status_mem = StatusStripItem("memory-stick", "MEMORY", C.GREEN_D)
        self._status_cpu = StatusStripItem("gauge", "CPU LOAD", C.PRI)
        self._status_temp = TempGaugeItem("AI CORE TEMP", C.ACC2)

        lay.addWidget(self._status_net, stretch=1)
        lay.addWidget(self._status_map, stretch=2)
        for item in (self._status_flow, self._status_mem,
                     self._status_cpu, self._status_temp):
            lay.addWidget(item, stretch=1)

        return w


    def _build_theme_bar(self) -> QWidget:
        """
        Referenz-Dashboard, unterste Leiste: THEME PRESETS (6 Buttons),
        COLOR ACCENT (Farbpunkte + '+'), CUSTOMIZATION (Glow/Animations-
        Toggles + Transparency-Slider), APPLY THEME. Alle Interaktionen
        wirken sofort als LIVE-VORSCHAU; persistiert wird erst mit APPLY.
        """
        s = _theme_manager.get_settings() if _theme_manager else dict(
            glow_effects=True, animations=True, transparency_pct=100)
        self._pending_theme = {
            "profile": _theme_manager.active_profile_name() if _theme_manager else None,
            "colors": dict(_theme_manager.get_active_colors()) if _theme_manager else {},
            "glow": s["glow_effects"],
            "anim": s["animations"],
            "transp": s["transparency_pct"],
        }

        w = QWidget()
        w.setFixedHeight(64)
        w.setStyleSheet(f"background: {C.DARK}; border-top: 1px solid {C.BORDER};")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(14, 6, 14, 6)
        lay.setSpacing(18)

        def _sec_label(text):
            l = QLabel(text)
            l.setFont(QFont(FONT_BODY, 6))
            l.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none; letter-spacing: 1.5px;")
            return l


        title_col = QVBoxLayout(); title_col.setSpacing(1)
        t1 = QLabel("APPEARANCE & THEME")
        t1.setFont(QFont(FONT_BODY, 8, QFont.Weight.Bold))
        t1.setStyleSheet(f"color: {C.TEXT}; background: transparent; border: none; letter-spacing: 1px;")
        t2 = QLabel("Customize the look and feel")
        t2.setFont(QFont(FONT_BODY, 6))
        t2.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
        title_col.addWidget(t1); title_col.addWidget(t2)
        lay.addLayout(title_col)


        presets_col = QVBoxLayout(); presets_col.setSpacing(3)
        presets_col.addWidget(_sec_label("THEME PRESETS"))
        preset_row = QHBoxLayout(); preset_row.setSpacing(4)
        self._bar_preset_btns: dict[str, QPushButton] = {}
        bar_presets = _theme_manager.BAR_PRESETS if _theme_manager else {}
        for label in bar_presets:
            b = QPushButton(label)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedHeight(20)
            b.clicked.connect(lambda _=False, n=label: self._bar_select_preset(n))
            self._bar_preset_btns[label] = b
            preset_row.addWidget(b)
        presets_col.addLayout(preset_row)
        lay.addLayout(presets_col)
        self._bar_style_presets()


        accent_col = QVBoxLayout(); accent_col.setSpacing(3)
        accent_col.addWidget(_sec_label("COLOR ACCENT"))
        accent_row = QHBoxLayout(); accent_row.setSpacing(5)
        for hexcol in (_theme_manager.ACCENT_SWATCHES if _theme_manager else []):
            dot = QPushButton()
            dot.setCursor(Qt.CursorShape.PointingHandCursor)
            dot.setFixedSize(18, 18)
            dot.setToolTip(hexcol)
            dot.setStyleSheet(
                f"QPushButton {{ background: {hexcol}; border: 1px solid {C.BORDER_B}; border-radius: 9px; }}"
                f"QPushButton:hover {{ border: 2px solid #ffffff; }}")
            dot.clicked.connect(lambda _=False, h=hexcol: self._bar_pick_accent(h))
            accent_row.addWidget(dot)
        plus = QPushButton("+")
        plus.setCursor(Qt.CursorShape.PointingHandCursor)
        plus.setFixedSize(18, 18)
        plus.setToolTip("Eigene Farbe (CUSTOM COLOR)")
        plus.setStyleSheet(
            f"QPushButton {{ background: {C.PANEL}; color: {C.TEXT_DIM}; "
            f"border: 1px solid {C.BORDER_B}; border-radius: 9px; font-weight: bold; }}"
            f"QPushButton:hover {{ color: #ffffff; border-color: #ffffff; }}")
        plus.clicked.connect(self._bar_open_custom_color)
        accent_row.addWidget(plus)
        accent_col.addLayout(accent_row)
        lay.addLayout(accent_col)


        cust_col = QVBoxLayout(); cust_col.setSpacing(2)
        cust_col.addWidget(_sec_label("CUSTOMIZATION"))
        cust_grid = QGridLayout(); cust_grid.setSpacing(3)

        def _toggle_label(text):
            l = QLabel(text)
            l.setFont(QFont(FONT_BODY, 6, QFont.Weight.Bold))
            l.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none; letter-spacing: 1px;")
            return l

        cust_grid.addWidget(_toggle_label("GLOW EFFECTS"), 0, 0)
        self._bar_glow = ToggleSwitch(self._pending_theme["glow"])
        self._bar_glow.toggled.connect(self._bar_toggle_glow)
        cust_grid.addWidget(self._bar_glow, 0, 1)

        cust_grid.addWidget(_toggle_label("ANIMATIONS"), 1, 0)
        self._bar_anim = ToggleSwitch(self._pending_theme["anim"])
        self._bar_anim.toggled.connect(self._bar_toggle_anim)
        cust_grid.addWidget(self._bar_anim, 1, 1)
        lay.addLayout(cust_col)
        cust_col.addLayout(cust_grid)

        transp_col = QVBoxLayout(); transp_col.setSpacing(2)
        transp_head = QHBoxLayout()
        transp_head.addWidget(_sec_label("TRANSPARENCY"))
        self._bar_transp_lbl = QLabel(f"{self._pending_theme['transp']}%")
        self._bar_transp_lbl.setFont(QFont(FONT_BODY, 7, QFont.Weight.Bold))
        self._bar_transp_lbl.setStyleSheet(f"color: {C.TEXT}; background: transparent; border: none;")
        transp_head.addStretch()
        transp_head.addWidget(self._bar_transp_lbl)
        transp_col.addLayout(transp_head)
        from PyQt6.QtWidgets import QSlider
        self._bar_transp = QSlider(Qt.Orientation.Horizontal)
        self._bar_transp.setRange(
            _theme_manager.MIN_TRANSPARENCY if _theme_manager else 20, 100)
        self._bar_transp.setValue(self._pending_theme["transp"])
        self._bar_transp.setFixedWidth(120)
        self._bar_transp.setStyleSheet(
            f"QSlider::groove:horizontal {{ height: 4px; background: {C.BORDER}; border-radius: 2px; }}"
            f"QSlider::sub-page:horizontal {{ background: {C.PRI}; border-radius: 2px; }}"
            f"QSlider::handle:horizontal {{ width: 12px; height: 12px; margin: -4px 0; "
            f"border-radius: 6px; background: #ffffff; }}")
        self._bar_transp.valueChanged.connect(self._bar_transp_changed)
        transp_col.addWidget(self._bar_transp)
        lay.addLayout(transp_col)

        lay.addStretch()


        apply_col = QVBoxLayout(); apply_col.setSpacing(2)
        apply_col.addWidget(_sec_label("PREVIEW"))
        apply_btn = QPushButton("APPLY THEME")
        apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        apply_btn.setFixedHeight(26)
        apply_btn.setStyleSheet(
            f"QPushButton {{ background: {C.PRI}; color: #000000; border: none; "
            f"padding: 4px 18px; font-family: 'Rajdhani'; font-size: 8pt; "
            f"font-weight: bold; letter-spacing: 1.5px; border-radius: 4px; }}"
            f"QPushButton:hover {{ background: {C.GREEN}; }}")
        apply_btn.clicked.connect(self._bar_apply_theme)
        apply_col.addWidget(apply_btn)
        lay.addLayout(apply_col)

        return w

    def _bar_style_presets(self) -> None:
        active_profile = self._pending_theme.get("profile")
        bar_presets = _theme_manager.BAR_PRESETS if _theme_manager else {}
        for label, btn in self._bar_preset_btns.items():
            active = bar_presets.get(label) == active_profile
            col = C.PRI if active else C.TEXT_DIM
            bg = C.PRI_GHO if active else C.PANEL
            btn.setStyleSheet(
                f"QPushButton {{ background: {bg}; color: {col}; border: 1px solid {col}; "
                f"padding: 2px 8px; font-family: 'Rajdhani'; font-size: 7pt; "
                f"font-weight: bold; letter-spacing: 1px; border-radius: 3px; }}")

    def _bar_preview_colors(self, colors: dict) -> None:
        """Live-Vorschau: Farbklasse ueberschreiben, Rahmen-Stylesheets neu
        setzen und alle Widgets neu malen. Einzelne zur Konstruktionszeit
        eingebettete Stylesheets (z.B. Eingabefelder) folgen nach Neustart."""
        for key, value in colors.items():
            setattr(C, key, value)
        self._restyle_chrome()
        for widget in self.findChildren(QWidget):
            widget.update()

    def _bar_select_preset(self, label: str) -> None:
        if _theme_manager is None:
            return
        profile = _theme_manager.BAR_PRESETS.get(label)
        if not profile:
            return
        colors = dict(_theme_manager.DEFAULT_COLORS)
        colors.update(_theme_manager.PRESETS.get(profile, {}))
        if profile == _theme_manager.DEFAULT_PROFILE_NAME:
            colors = dict(_theme_manager.DEFAULT_COLORS)
        self._pending_theme["profile"] = profile
        self._pending_theme["colors"] = colors
        self._bar_style_presets()
        self._bar_preview_colors(colors)
        self._log.append_log(f"SYS: Theme-Vorschau '{label}' — APPLY THEME uebernimmt dauerhaft.")

    def _bar_pick_accent(self, hexcol: str) -> None:
        if _theme_manager is None:
            return
        colors = _theme_manager._dark_palette(hexcol)
        self._pending_theme["profile"] = None
        self._pending_theme["colors"] = colors
        self._bar_style_presets()
        self._bar_preview_colors(colors)

    def _bar_open_custom_color(self) -> None:
        current = self._pending_theme["colors"].get("PRI", C.PRI)
        popup = CustomColorPopup(current, self)
        popup.colorChosen.connect(self._bar_pick_accent)
        pos = self.mapToGlobal(self.rect().center())
        popup.move(pos.x() - popup.width() // 2, pos.y() - popup.height() // 2)
        popup.show()

    def _bar_toggle_glow(self, on: bool) -> None:
        self._pending_theme["glow"] = on
        self.hud.set_glow_enabled(on)

    def _bar_toggle_anim(self, on: bool) -> None:
        self._pending_theme["anim"] = on
        self.hud.set_animations_enabled(on)

    def _bar_transp_changed(self, val: int) -> None:
        self._pending_theme["transp"] = val
        self._bar_transp_lbl.setText(f"{val}%")
        self._set_transparency_preview(val)

    def _bar_apply_theme(self) -> None:
        """Persistiert Vorschau-Zustand: Profil/Farben + Glow/Anim/Transparenz."""
        if _theme_manager is None:
            return
        pending = self._pending_theme
        if pending.get("profile"):
            _theme_manager.set_active(pending["profile"])
        else:
            _theme_manager.save_profile("Custom", pending["colors"], make_active=True)
            pending["profile"] = "Custom"
        _theme_manager.save_settings({
            "glow_effects": pending["glow"],
            "animations": pending["anim"],
            "transparency_pct": pending["transp"],
        })
        self._bar_style_presets()
        self._bar_preview_colors(pending["colors"])
        self._apply_transparency()
        self._log.append_log(
            "SYS: Theme angewendet und gespeichert — Stylesheet-Elemente "
            "uebernehmen die Farben vollstaendig nach einem Neustart.")

    def _build_footer(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(22)
        w.setStyleSheet(f"background: {C.DARK}; border-top: 1px solid {C.BORDER};")
        lay = QHBoxLayout(w); lay.setContentsMargins(14, 0, 14, 0)

        def _fl(txt, color=C.TEXT_MED):
            l = QLabel(txt); l.setFont(QFont(FONT_BODY, 7))
            l.setStyleSheet(f"color: {color}; background: transparent;")
            return l

        lay.addWidget(_fl("[F4] Mute  ·  [F11] Fullscreen"))
        lay.addStretch()
        lay.addWidget(_fl("RENKER ARTIFICIAL INTELLIGENCE  ·  RENCORA V1  ·  CLASSIFIED"))
        lay.addStretch()
        lay.addWidget(_fl("© RENKER INDUSTRIES", C.PRI_DIM))
        return w

    def _on_file_selected(self, path: str):
        self._current_file = path
        p    = Path(path)
        cat  = _file_category(p)
        icon, _ = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size = _fmt_size(p.stat().st_size)
        self._file_hint.setText(f"{icon}  {p.name}  ·  {size}  ·  Tell RENCORA what to do with it")
        self._log.append_log(f"FILE: {p.name} ({size}) loaded")
        if self.on_text_command:
            msg = (
                f"[FILE_UPLOADED] path={path} | name={p.name} | "
                f"type={p.suffix.lstrip('.')} | size={size} | "
                f"Briefly tell the user you can see the file '{p.name}' "
                f"({size}) has been uploaded and ask what they'd like to do with it."
            )
            threading.Thread(target=self.on_text_command, args=(msg,), daemon=True).start()

    def notify_phone_connected(self) -> None:
        if self._remote_overlay and self._remote_overlay.isVisible():
            self._remote_overlay.mark_connected()

    def _open_remote(self):
        if not self.on_remote_clicked:
            self._log.append_log("SYS: Dashboard not running — remote unavailable.")
            return
        result = self.on_remote_clicked()
        if not result:
            self._log.append_log("SYS: Could not generate remote key.")
            return
        url    = result[0]
        key    = result[1]
        auto   = result[2] if len(result) >= 3 else ""
        manual = result[3] if len(result) >= 4 else url
        tunnel_url  = result[4] if len(result) >= 5 else None
        tunnel_auto = result[5] if len(result) >= 6 else ""
        if self._remote_overlay:
            self._remote_overlay._do_close()
        cw  = self.centralWidget()
        ow, oh = RemoteKeyOverlay._OW, RemoteKeyOverlay._OH
        ov  = RemoteKeyOverlay(url, key, auto_login_url=auto, manual_url=manual,
                               expiry_secs=600, parent=cw,
                               tunnel_url=tunnel_url, tunnel_auto_login_url=tunnel_auto,
                               get_tunnel_status_fn=self.on_get_tunnel_status)
        ov.set_new_key_callback(self.on_remote_clicked)
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.closed.connect(lambda: setattr(self, '_remote_overlay', None))
        ov.show()
        self._remote_overlay = ov
        self._log.append_log(f"SYS: Remote key generated — manual: {manual or url}")

    def _toggle_mute(self):
        self._muted = not self._muted
        self.hud.muted = self._muted
        self._style_mute_btn()
        if self._muted:
            self._apply_state("MUTED")
            self._log.append_log("SYS: Microphone muted.")
        else:
            self._apply_state("LISTENING")
            self._log.append_log("SYS: Microphone active.")

    def _style_mute_btn(self):
        if self._muted:
            self._mute_btn._icon = "mic"
            self._mute_btn._text = "MIC\nMUTED"
            self._mute_btn.set_active(True, C.MUTED_C)
        else:
            self._mute_btn._icon = "mic"
            self._mute_btn._text = "MIC\nACTIVE"
            self._mute_btn.set_active(True, C.GREEN)

    def _send(self):
        txt = self._input.text().strip()
        if not txt: return
        self._input.clear()
        self._log.append_log(f"You: {txt}")
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(txt,), daemon=True).start()

    def _apply_state(self, state: str):
        self.hud.state    = state
        self.hud.speaking = (state == "SPEAKING")

    def confirm_action(self, name: str, args: dict, level: int) -> bool:
        """Vom Agent-Thread aufgerufen: fordert eine Bestaetigung im Hauptthread an
        und wartet (mit Timeout) auf die Nutzerentscheidung. Fail-safe: bei Timeout
        oder Fehler wird verweigert."""
        ev = threading.Event()
        holder = {"ok": False}
        try:
            self._confirm_sig.emit((name, level, ev, holder))
        except Exception:
            return False
        ev.wait(timeout=120)
        return holder["ok"]

    def _on_confirm_request(self, req) -> None:
        name, level, ev, holder = req
        try:
            from PyQt6.QtWidgets import QMessageBox
            box = QMessageBox(self)
            box.setWindowTitle("RENCORA — Bestaetigung")
            box.setText(f"RENCORA moechte ausfuehren:\n\n{name}   (Risikostufe {level})")
            box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            box.setDefaultButton(QMessageBox.StandardButton.No)
            holder["ok"] = box.exec() == QMessageBox.StandardButton.Yes
        except Exception:
            holder["ok"] = False
        finally:
            ev.set()

    def _check_config(self) -> bool:
        if not API_FILE.exists(): return False
        try:
            from core.secrets import is_configured
            d = json.loads(API_FILE.read_text(encoding="utf-8"))
            return is_configured() and bool(d.get("os_system"))
        except Exception:
            return False

    def _show_setup(self):
        ov = SetupOverlay(self.centralWidget())
        cw = self.centralWidget()
        ow, oh = 460, 390
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.done.connect(self._on_setup_done)
        ov.show()
        self._overlay = ov

    def _on_setup_done(self, key: str, os_name: str):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        from core.secrets import set_gemini_key
        set_gemini_key(key, {"os_system": os_name})
        self._ready = True
        if self._overlay:
            self._overlay.hide()
            self._overlay = None
        self._apply_state("LISTENING")


        self._log.append_log(f"SYS: Initialised. OS={os_name.upper()}.")
        self._log.append_log("SYS: Security status cleared.")
        self._log.append_log("SYS: Microphone active.")
        self._log.append_log("SYS: RENCORA online.")
        self._log.append_log("SYS: All systems operational.")

class _RootShim:
    def __init__(self, app: QApplication):
        self._app = app
    def mainloop(self):
        self._app.exec()
    def protocol(self, *_):
        pass


class BasiUI:
    def __init__(self, face_path: str, size=None):
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._app.setStyle("Fusion")
        self._win = MainWindow(face_path)
        self._win.show()
        self.root = _RootShim(self._app)

    @property
    def muted(self) -> bool:
        return self._win._muted

    @muted.setter
    def muted(self, v: bool):
        if v != self._win._muted:
            self._win._toggle_mute()

    @property
    def current_file(self) -> str | None:
        return self._win._drop_zone.current_file()

    @property
    def on_text_command(self):
        return self._win.on_text_command

    @on_text_command.setter
    def on_text_command(self, cb):
        self._win.on_text_command = cb

    @property
    def on_remote_clicked(self):
        return self._win.on_remote_clicked

    @on_remote_clicked.setter
    def on_remote_clicked(self, cb):
        self._win.on_remote_clicked = cb

    @property
    def on_get_tunnel_status(self):
        return self._win.on_get_tunnel_status

    @on_get_tunnel_status.setter
    def on_get_tunnel_status(self, cb):
        self._win.on_get_tunnel_status = cb

    def notify_phone_connected(self) -> None:
        self._win.notify_phone_connected()

    def set_state(self, state: str):
        self._win._state_sig.emit(state)


        try:
            from core.hologram_bridge import hologram_bridge
            hologram_bridge.send_thought_state(state)
        except Exception:
            pass

    def write_log(self, text: str):
        self._win._log_sig.emit(text)

    def wait_for_api_key(self):
        while not self._win._ready:
            time.sleep(0.1)

    def start_speaking(self):
        self.set_state("SPEAKING")

    def stop_speaking(self):
        if not self.muted:
            self.set_state("LISTENING")