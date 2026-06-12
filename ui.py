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

from PyQt6.QtCore import (
    QEasingCurve, QMimeData, QObject, QPointF, QRectF, QSize, Qt,
    QTimer, QUrl, pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush, QColor, QDragEnterEvent, QDropEvent, QFont, QFontDatabase,
    QKeySequence, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
    QRadialGradient, QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QPushButton, QScrollArea, QSizePolicy, QTextEdit,
    QVBoxLayout, QWidget, QProgressBar,
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
_LEFT_W  = 200
_RIGHT_W = 340

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"


class C:
    BG        = "#00060a"
    PANEL     = "#010d14"
    PANEL2    = "#010f18"
    BORDER    = "#0d3347"
    BORDER_B  = "#1a5c7a"
    BORDER_A  = "#0f4060"
    PRI       = "#00d4ff"
    PRI_DIM   = "#007a99"
    PRI_GHO   = "#001f2e"
    ACC       = "#ff6b00"
    ACC2      = "#ffcc00"
    GREEN     = "#00ff88"
    GREEN_D   = "#00aa55"
    RED       = "#ff3355"
    MUTED_C   = "#ff3366"
    TEXT      = "#8ffcff"
    TEXT_DIM  = "#3a8a9a"
    TEXT_MED  = "#5ab8cc"
    WHITE     = "#d8f8ff"
    DARK      = "#000d14"
    BAR_BG    = "#011520"


def qcol(h: str, a: int = 255) -> QColor:
    c = QColor(h); c.setAlpha(a); return c

class _SysMetrics:
    MAX_HISTORY = 60
    _CACHE_TTL = 5.0

    def __init__(self):
        self.cpu  = 0.0
        self.mem  = 0.0
        self.net  = 0.0
        self.net_up = 0.0
        self.net_down = 0.0
        self.gpu  = -1.0
        self.tmp  = -1.0
        self.cpu_cores: list[float] = []
        self.connections: int = 0
        self.top_processes: list[tuple[str, float]] = []

        self.cpu_history: list[float] = []
        self.mem_history: list[float] = []
        self.net_up_history: list[float] = []
        self.net_down_history: list[float] = []
        self.gpu_history: list[float] = []

        self._lock = threading.Lock()
        self._last_net = psutil.net_io_counters()
        self._last_net_t = time.time()

        self._cached_gpu = -1.0
        self._cached_tmp = -1.0
        self._last_gpu_t = 0.0
        self._last_tmp_t = 0.0

        self._running = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def _loop(self):
        while self._running:
            try:
                self._update()
            except Exception:
                pass
            time.sleep(1.0)

    def _update(self):
        cpu_cores = psutil.cpu_percent(interval=None, percpu=True)
        cpu_avg = sum(cpu_cores) / len(cpu_cores) if cpu_cores else 0.0
        mem = psutil.virtual_memory().percent

        nc  = psutil.net_io_counters()
        now = time.time()
        dt  = now - self._last_net_t
        if dt > 0:
            sent_bps = (nc.bytes_sent - self._last_net.bytes_sent) / dt
            recv_bps = (nc.bytes_recv - self._last_net.bytes_recv) / dt
            net_up   = sent_bps / (1024 * 1024)
            net_down = recv_bps / (1024 * 1024)
            net      = net_up + net_down
        else:
            net = net_up = net_down = 0.0
        self._last_net   = nc
        self._last_net_t = now

        # GPU with 5s cache
        if now - self._last_gpu_t > self._CACHE_TTL:
            self._cached_gpu = self._get_gpu()
            self._last_gpu_t = now
        gpu = self._cached_gpu

        # Temp with 5s cache
        if now - self._last_tmp_t > self._CACHE_TTL:
            self._cached_tmp = self._get_temp()
            self._last_tmp_t = now
        tmp = self._cached_tmp

        try:
            conns = len(psutil.net_connections())
        except Exception:
            conns = 0

        top_procs = []
        try:
            psutil.cpu_percent(interval=0.1)
            procs = []
            for p in psutil.process_iter(['name', 'cpu_percent']):
                try:
                    n = p.info['name'] or '?'
                    c = p.info['cpu_percent'] or 0.0
                    procs.append((n, c))
                except Exception:
                    pass
            procs.sort(key=lambda x: x[1], reverse=True)
            top_procs = procs[:5]
        except Exception:
            pass

        for h in [self.cpu_history, self.mem_history,
                  self.net_up_history, self.net_down_history, self.gpu_history]:
            h.append(0.0)

        self.cpu_history[-1] = cpu_avg
        self.mem_history[-1] = mem
        self.net_up_history[-1] = net_up
        self.net_down_history[-1] = net_down
        self.gpu_history[-1] = gpu if gpu >= 0 else 0.0

        for h in [self.cpu_history, self.mem_history,
                  self.net_up_history, self.net_down_history, self.gpu_history]:
            if len(h) > self.MAX_HISTORY:
                del h[:-self.MAX_HISTORY]

        with self._lock:
            self.cpu = cpu_avg
            self.mem = mem
            self.net = net
            self.net_up = net_up
            self.net_down = net_down
            self.gpu = gpu
            self.tmp = tmp
            self.cpu_cores = cpu_cores
            self.connections = conns
            self.top_processes = top_procs

    def _get_gpu(self) -> float:
        # NVIDIA
        try:
            r = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=2
            )
            if r.returncode == 0:
                vals = [float(v.strip()) for v in r.stdout.strip().split("\n") if v.strip()]
                if vals:
                    return sum(vals) / len(vals)
        except Exception:
            pass

        # AMD (Linux)
        if _OS == "Linux":
            try:
                r = subprocess.run(
                    ["rocm-smi", "--showuse", "--csv"],
                    capture_output=True, text=True, timeout=2
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

            # Intel GPU (Linux)
            try:
                r = subprocess.run(
                    ["intel_gpu_top", "-J", "-s", "500"],
                    capture_output=True, text=True, timeout=1
                )
                if r.returncode == 0 and "Render/3D" in r.stdout:
                    import re
                    m = re.search(r'"busy":\s*([\d.]+)', r.stdout)
                    if m:
                        return float(m.group(1))
            except Exception:
                pass

        # macOS — powermetrics (GPU Engine)
        if _OS == "Darwin":
            try:
                r = subprocess.run(
                    ["sudo", "-n", "powermetrics", "-n", "1", "-i", "500",
                     "--samplers", "gpu_power"],
                    capture_output=True, text=True, timeout=2
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
                    ["osx-cpu-temp"], capture_output=True, text=True, timeout=2
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
                    capture_output=True, text=True, timeout=3
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
                "net_up": self.net_up,
                "net_down": self.net_down,
                "gpu": self.gpu,
                "tmp": self.tmp,
                "cpu_cores": list(self.cpu_cores),
                "connections": self.connections,
                "top_processes": list(self.top_processes),
                "cpu_history": list(self.cpu_history),
                "mem_history": list(self.mem_history),
                "net_up_history": list(self.net_up_history),
                "net_down_history": list(self.net_down_history),
                "gpu_history": list(self.gpu_history),
            }


_metrics = _SysMetrics()

class HudCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self.setMinimumSize(300, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.muted    = False
        self.speaking = False
        self.state    = "INITIALISING"

        self._tick       = 0
        self._stream_phase = 0.0
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

        self._orbit_angle1 = 0.0
        self._orbit_angle2 = 60.0
        self._orbit_angle3 = 120.0
        self._node_pulse = 0.0
        self._data_nodes: list[dict] = []
        for i in range(8):
            self._data_nodes.append({
                "angle": i * 45.0,
                "size": random.uniform(2, 5),
                "speed": random.uniform(0.3, 0.8),
                "phase": random.uniform(0, 6.28),
            })

        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._tmr.start(16)

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

        speed_mul = 2.0 if self.speaking else 1.0
        speeds = [1.3 * speed_mul, -0.9 * speed_mul, 2.0 * speed_mul]
        for i, spd in enumerate(speeds):
            self._rings[i] = (self._rings[i] + spd) % 360

        self._scan  = (self._scan  + (3.0 if self.speaking else 1.3)) % 360
        self._scan2 = (self._scan2 + (-2.0 if self.speaking else -0.75)) % 360

        self._orbit_angle1 = (self._orbit_angle1 + 1.2 * speed_mul) % 360
        self._orbit_angle2 = (self._orbit_angle2 + 0.8 * speed_mul) % 360
        self._orbit_angle3 = (self._orbit_angle3 + 1.5 * speed_mul) % 360
        self._node_pulse = (self._node_pulse + 0.04 * speed_mul) % 6.28

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
        self.update()

    def _draw_avatar(self, p: QPainter, cx: float, cy: float, fw: float):
        base_r = fw * 0.27 * self._scale
        accent = qcol(C.MUTED_C if self.muted else (C.ACC if self.speaking else C.PRI))

        def _radial(qcol_center, qcol_edge, r):
            grad = QRadialGradient(cx, cy, r)
            grad.setColorAt(0.0, qcol_center)
            grad.setColorAt(0.6, qcol_center)
            grad.setColorAt(1.0, qcol_edge)
            return grad

        # energy rings (orbit)
        for idx, (angle, orbit_r, w, color) in enumerate([
            (self._orbit_angle1, base_r * 1.55, 2.5, accent),
            (self._orbit_angle2, base_r * 1.85, 2.0, qcol(C.PRI_DIM)),
            (self._orbit_angle3, base_r * 2.10, 1.5, qcol(C.ACC2)),
        ]):
            rad = math.radians(angle)
            ox = cx + orbit_r * math.cos(rad)
            oy = cy + orbit_r * math.sin(rad) * 0.4
            orb_a = max(0, min(255, int(self._halo * 2.2)))
            col = QColor(color); col.setAlpha(orb_a)
            p.setPen(QPen(col, w))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(ox - 3, oy - 3, 6, 6))

            # orbit path (subtle ellipse)
            col_trail = QColor(color); col_trail.setAlpha(orb_a // 4)
            p.setPen(QPen(col_trail, 1))
            p.drawEllipse(QRectF(cx - orbit_r, cy - orbit_r * 0.4, orbit_r * 2, orbit_r * 0.8))

        # outer glow layers
        for i in range(12, 0, -1):
            r = base_r * (1.0 + (12 - i) * 0.06)
            frc = i / 12
            a = max(0, min(255, int(self._halo * 1.5 * frc)))
            if self.muted:
                col = QColor(200, 30, 60, a)
            elif self.speaking:
                col = QColor(255, 120 + int(80 * frc), 0, a)
            else:
                col = QColor(0, int(100 + 50 * frc), int(200 + 55 * frc), a)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(col))
            p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

        # core — bright center
        core_a = max(0, min(255, int(self._halo * 3.0)))
        if self.muted:
            c1, c2 = QColor(180, 0, 40, core_a), QColor(80, 0, 20, 0)
        elif self.speaking:
            c1, c2 = QColor(255, 200, 50, core_a), QColor(255, 80, 0, 0)
        else:
            c1, c2 = QColor(80, 220, 255, core_a), QColor(0, 60, 140, 0)
        core_r = base_r * 0.55
        p.setBrush(QBrush(_radial(c1, c2, core_r)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(cx - core_r, cy - core_r, core_r * 2, core_r * 2))

        # inner bright spot
        spot_r = core_r * 0.35
        spot_off = core_r * 0.25
        grad2 = QRadialGradient(cx - spot_off, cy - spot_off, spot_r)
        grad2.setColorAt(0.0, QColor(255, 255, 255, 180))
        grad2.setColorAt(0.5, QColor(255, 255, 255, 60))
        grad2.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(QBrush(grad2))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(cx - spot_off - spot_r, cy - spot_off - spot_r, spot_r * 2, spot_r * 2))

        # data nodes around perimeter
        node_base_r = base_r * 2.5
        for node in self._data_nodes:
            ang_r = math.radians(node["angle"] + self._tick * node["speed"])
            nx = cx + node_base_r * math.cos(ang_r)
            ny = cy + node_base_r * math.sin(ang_r) * 0.4
            pulse = math.sin(self._node_pulse + node["phase"]) * 0.5 + 0.5
            sz = node["size"] * (0.5 + pulse * 0.8)
            na = max(0, min(255, int(self._halo * (0.3 + pulse * 0.7))))
            ncol = QColor(accent); ncol.setAlpha(na)
            p.setBrush(QBrush(ncol))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(nx - sz, ny - sz, sz * 2, sz * 2))

            # connection line to center
            if pulse > 0.6:
                lcol = QColor(accent); lcol.setAlpha(na // 3)
                p.setPen(QPen(lcol, 0.5))
                p.drawLine(QPointF(cx, cy), QPointF(nx, ny))

        # label
        lbl_a = max(0, min(255, int(self._halo * 2.5)))
        lbl_col = QColor(accent); lbl_col.setAlpha(lbl_a)
        p.setPen(QPen(lbl_col, 1))
        lbl_size = max(9, int(fw * 0.025))
        p.setFont(QFont("Courier New", lbl_size, QFont.Weight.Bold))
        lbl_y = cy + base_r * 1.1 + lbl_size + 12
        lbl = "● N O X ●"
        p.drawText(QRectF(cx - fw * 0.3, lbl_y, fw * 0.6, lbl_size + 6),
                   Qt.AlignmentFlag.AlignCenter, lbl)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), qcol(C.BG))

        W, H = self.width(), self.height()
        cx, cy = W / 2, H / 2
        fw = min(W, H)

        # grid dots
        p.setPen(QPen(qcol(C.PRI_GHO), 1))
        for x in range(0, W, 48):
            for y in range(0, H, 48):
                p.drawPoint(x, y)

        r_face = fw * 0.31

        # halo glow
        for i in range(10):
            r   = r_face * (1.8 - i * 0.08)
            frc = 1.0 - i / 10
            a   = max(0, min(255, int(self._halo * 0.085 * frc)))
            col = qcol(C.MUTED_C if self.muted else C.PRI, a)
            p.setPen(QPen(col, 1.5)); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

        # pulse rings
        for pr in self._pulses:
            a   = max(0, int(230 * (1.0 - pr / (fw * 0.74))))
            col = qcol(C.MUTED_C if self.muted else C.PRI, a)
            p.setPen(QPen(col, 1.5)); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(cx - pr, cy - pr, pr * 2, pr * 2))

        # spinning arc rings
        for idx, (r_frac, w_r, arc_l, gap) in enumerate(
            [(0.48, 3, 115, 78), (0.40, 2, 78, 55), (0.32, 1, 56, 40)]
        ):
            ring_r = fw * r_frac
            base   = self._rings[idx]
            a_val  = max(0, min(255, int(self._halo * (1.0 - idx * 0.18))))
            col    = qcol(C.MUTED_C if self.muted else C.PRI, a_val)
            p.setPen(QPen(col, w_r)); p.setBrush(Qt.BrushStyle.NoBrush)
            angle = base
            rect  = QRectF(cx - ring_r, cy - ring_r, ring_r * 2, ring_r * 2)
            while angle < base + 360:
                p.drawArc(rect, int(angle * 16), int(arc_l * 16))
                angle += arc_l + gap

        # scanners
        sr = fw * 0.50
        sa = min(255, int(self._halo * 1.5))
        ex = 75 if self.speaking else 44
        p.setPen(QPen(qcol(C.MUTED_C if self.muted else C.PRI, sa), 2.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        srect = QRectF(cx - sr, cy - sr, sr * 2, sr * 2)
        p.drawArc(srect, int(self._scan * 16), int(ex * 16))
        p.setPen(QPen(qcol(C.ACC, sa // 2), 1.5))
        p.drawArc(srect, int(self._scan2 * 16), int(ex * 16))

        # tick marks
        t_out, t_in = fw * 0.497, fw * 0.474
        p.setPen(QPen(qcol(C.PRI, 140), 1))
        for deg in range(0, 360, 10):
            rad = math.radians(deg)
            inn = t_in if deg % 30 == 0 else t_in + 6
            p.drawLine(
                QPointF(cx + t_out * math.cos(rad), cy - t_out * math.sin(rad)),
                QPointF(cx + inn  * math.cos(rad), cy - inn  * math.sin(rad)),
            )

        # crosshair
        ch_r, gap_h = fw * 0.51, fw * 0.16
        p.setPen(QPen(qcol(C.PRI, int(self._halo * 0.5)), 1))
        p.drawLine(QPointF(cx - ch_r, cy), QPointF(cx - gap_h, cy))
        p.drawLine(QPointF(cx + gap_h, cy), QPointF(cx + ch_r, cy))
        p.drawLine(QPointF(cx, cy - ch_r), QPointF(cx, cy - gap_h))
        p.drawLine(QPointF(cx, cy + gap_h), QPointF(cx, cy + ch_r))

        # corner brackets
        bl = 24
        bc = qcol(C.PRI, 210)
        hl, hr = cx - fw // 2, cx + fw // 2
        ht, hb = cy - fw // 2, cy + fw // 2
        p.setPen(QPen(bc, 2))
        for bx, by, dx, dy in [(hl,ht,1,1),(hr,ht,-1,1),(hl,hb,1,-1),(hr,hb,-1,-1)]:
            p.drawLine(QPointF(bx, by), QPointF(bx + dx * bl, by))
            p.drawLine(QPointF(bx, by), QPointF(bx, by + dy * bl))

        # modern avatar — animated AI core
        self._draw_avatar(p, cx, cy, fw)

        # particles
        for pt in self._particles:
            a = max(0, min(255, int(pt[4] * 255)))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(qcol(C.PRI, a)))
            p.drawEllipse(QPointF(pt[0], pt[1]), 2.5, 2.5)

        # status text
        sy = cy + fw * 0.40
        if self.muted:
            txt, col = "⊘  MUTED",     qcol(C.MUTED_C)
        elif self.speaking:
            txt, col = "●  SPEAKING",  qcol(C.ACC)
        elif self.state == "THINKING":
            sym = "◈" if self._blink else "◇"
            txt, col = f"{sym}  THINKING",   qcol(C.ACC2)
        elif self.state == "PROCESSING":
            sym = "▷" if self._blink else "▶"
            txt, col = f"{sym}  PROCESSING", qcol(C.ACC2)
        elif self.state == "LISTENING":
            sym = "●" if self._blink else "○"
            txt, col = f"{sym}  LISTENING",  qcol(C.GREEN)
        else:
            sym = "●" if self._blink else "○"
            txt, col = f"{sym}  {self.state}", qcol(C.PRI)

        p.setPen(QPen(col, 1))
        p.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        p.drawText(QRectF(0, sy, W, 26), Qt.AlignmentFlag.AlignCenter, txt)

        # waveform
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
            p.fillRect(QRectF(wx0 + i * bw, wy + 20 - hgt, bw - 1, hgt), cl)

        # scanlines
        p.setPen(QPen(QColor(0, 0, 0, 30), 0))
        for sy_ in range(0, H, 3):
            p.drawLine(0, sy_, W, sy_)

        # vignette
        vg = QRadialGradient(cx, cy, fw * 0.55)
        vg.setColorAt(0.0, QColor(0, 0, 0, 0))
        vg.setColorAt(0.7, QColor(0, 0, 0, 20))
        vg.setColorAt(1.0, QColor(0, 0, 0, 160))
        p.setBrush(QBrush(vg))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(self.rect())

        # data stream at bottom
        self._stream_phase += 0.08
        stream_y = H - 18
        hex_chars = "0123456789ABCDEF"
        stream_w = 10
        n_chars = W // stream_w
        for si in range(n_chars):
            offset = int(self._stream_phase + si * 0.7) % len(hex_chars)
            ch = hex_chars[(offset + si) % len(hex_chars)]
            alpha = max(20, min(100, int(60 + 40 * math.sin(self._stream_phase * 0.5 + si * 0.3))))
            p.setPen(QPen(QColor(0, int(180 + 75 * math.sin(si * 0.2)), int(220 + 35 * math.sin(si * 0.3)), alpha), 1))
            p.setFont(QFont("Courier New", 7))
            p.drawText(QRectF(si * stream_w, stream_y, stream_w, 14),
                       Qt.AlignmentFlag.AlignCenter, ch)

def _draw_holo_brackets(p, W, H, color, cl=10, a_top=50, a_main=180, a_glow=220):
    p.setPen(QPen(qcol(color, a_top), 0.5))
    p.drawLine(QPointF(cl + 2, 2), QPointF(W - cl - 2, 2))
    p.drawLine(QPointF(cl + 2, H - 2), QPointF(W - cl - 2, H - 2))
    for off, a in [(1, a_top - 20), (0, a_main)]:
        co = qcol(color, a)
        p.setPen(QPen(co, 1.2 if off == 0 else 0.8))
        p.drawLine(QPointF(2 + off, 2 + off), QPointF(2 + cl + off, 2 + off))
        p.drawLine(QPointF(2 + off, 2 + off), QPointF(2 + off, 2 + cl + off))
        p.drawLine(QPointF(W - 2 - off, 2 + off), QPointF(W - 2 - cl - off, 2 + off))
        p.drawLine(QPointF(W - 2 - off, 2 + off), QPointF(W - 2 - off, 2 + cl + off))
        p.drawLine(QPointF(2 + off, H - 2 - off), QPointF(2 + cl + off, H - 2 - off))
        p.drawLine(QPointF(2 + off, H - 2 - off), QPointF(2 + off, H - 2 - cl - off))
        p.drawLine(QPointF(W - 2 - off, H - 2 - off), QPointF(W - 2 - cl - off, H - 2 - off))
        p.drawLine(QPointF(W - 2 - off, H - 2 - off), QPointF(W - 2 - off, H - 2 - cl - off))
    for dx, dy in [(2,2),(W-2,2),(2,H-2),(W-2,H-2)]:
        p.setBrush(QBrush(qcol(color, a_glow)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(dx, dy), 1.5, 1.5)


class MetricBar(QWidget):

    def __init__(self, label: str, color: str = C.PRI, parent=None):
        super().__init__(parent)
        self._label = label
        self._color = color
        self._value = 0.0
        self._text  = "--"
        self._history: list[float] = []
        self._max_h = 1.0
        self.setFixedHeight(42)
        self.setMinimumWidth(80)
        self._font_label = QFont("Courier New", 7, QFont.Weight.Bold)
        self._font_value = QFont("Courier New", 9, QFont.Weight.Bold)

    def set_value(self, pct: float, text: str):
        self._value = max(0.0, min(100.0, pct))
        self._text  = text
        self.update()

    def set_history(self, hist: list[float]):
        self._history = hist[-60:]
        if hist:
            self._max_h = max(hist) if max(hist) > 0 else 1.0
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        _draw_holo_brackets(p, W, H, self._color, a_main=180)

        # sparkline
        if self._history:
            spk_h = 12
            spk_y = 3
            spk_w = W - 20
            spk_x = 10
            step  = spk_w / max(len(self._history) - 1, 1)
            path  = QPainterPath()
            first = True
            for i, v in enumerate(self._history):
                x = spk_x + i * step
                y = spk_y + spk_h - (v / self._max_h) * spk_h
                if first:
                    path.moveTo(x, y)
                    first = False
                else:
                    path.lineTo(x, y)
            spk_col = qcol(self._color, 140)
            p.setPen(QPen(spk_col, 1.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)

        # label
        p.setFont(self._font_label)
        p.setPen(QPen(qcol(self._color, 160), 1))
        p.drawText(QRectF(8, 14, 50, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._label)

        if self._value > 85:
            bar_col = qcol(C.RED)
        elif self._value > 65:
            bar_col = qcol(C.ACC)
        else:
            bar_col = qcol(self._color)

        # value
        p.setFont(self._font_value)
        p.setPen(QPen(bar_col if self._text != "--" else qcol(self._color, 80), 1))
        p.drawText(QRectF(0, 13, W - 6, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self._text)

        # holographic bar
        bar_h   = 2
        bar_y   = H - bar_h - 4
        bar_w   = W - 16
        bar_x   = 8
        fill_w  = int(bar_w * self._value / 100)

        p.setBrush(QBrush(qcol(self._color, 40)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 1, 1)

        if fill_w > 0:
            p.setBrush(QBrush(bar_col))
            p.setPen(QPen(qcol(self._color, 100), 0.5))
            p.drawRoundedRect(QRectF(bar_x, bar_y, fill_w, bar_h), 1, 1)

            # glow below bar
            p.setBrush(QBrush(bar_col.lighter(150)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(bar_x, bar_y + 1, fill_w, 1), 0.5, 0.5)


class CpuCoresWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cores: list[float] = []
        self.setFixedHeight(30)
        self.setMinimumWidth(80)
        self._font = QFont("Courier New", 7)

    def set_cores(self, cores: list[float]):
        self._cores = cores
        self.update()

    def paintEvent(self, _):
        if not self._cores:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        n = len(self._cores)
        gap = 3
        bw = min(12, (W - gap * (n + 1)) // n)
        bx = (W - (bw * n + gap * (n - 1))) // 2
        by = 4
        bh = H - by * 2

        for i, val in enumerate(self._cores):
            x = bx + i * (bw + gap)
            fill_h = max(1, int(bh * min(val, 100) / 100))

            # background column
            p.setBrush(QBrush(qcol(C.PRI, 25)))
            p.setPen(QPen(qcol(C.PRI, 60), 0.5))
            p.drawRoundedRect(QRectF(x, by, bw, bh), 1, 1)

            # fill
            bar_col = qcol(C.RED) if val > 85 else (qcol(C.ACC) if val > 65 else qcol(C.PRI))
            p.setBrush(QBrush(bar_col))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(x + 0.5, by + bh - fill_h + 0.5, bw - 1, fill_h - 1), 1, 1)

            # glow dot on top of filled bar
            if fill_h > 3:
                p.setBrush(QBrush(bar_col.lighter(180)))
                p.drawRect(QRectF(x + 1, by + bh - fill_h, bw - 2, 1))


class NetworkWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._up = 0.0
        self._down = 0.0
        self._up_history: list[float] = []
        self._down_history: list[float] = []
        self._tick = 0
        self._max_h = 1.0
        self.setFixedHeight(48)
        self.setMinimumWidth(80)
        self._font_val = QFont("Courier New", 8, QFont.Weight.Bold)
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._anim)
        self._tmr.start(50)

    def _anim(self):
        self._tick += 1
        self.update()

    def set_values(self, up: float, down: float,
                   up_hist: list[float], down_hist: list[float]):
        self._up = up
        self._down = down
        self._up_history = up_hist[-60:]
        self._down_history = down_hist[-60:]
        mx = max(max(up_hist or [0]), max(down_hist or [0]))
        self._max_h = mx if mx > 0 else 1.0

    def _fmt(self, val: float) -> str:
        if val < 1.0:
            return f"{val*1024:.0f}K"
        return f"{val:.1f}M"

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        _draw_holo_brackets(p, W, H, C.PRI_DIM, a_main=150)

        # up/down
        arrow_pulse = math.sin(self._tick * 0.15) * 0.3 + 0.7

        up_col = qcol(C.ACC, int(170 + 85 * arrow_pulse if self._up > 0.01 else 80))
        p.setPen(QPen(up_col, 1))
        p.setFont(self._font_val)
        p.drawText(QRectF(4, 2, W // 2 - 2, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f"▲ {self._fmt(self._up)}/s")

        down_col = qcol(C.GREEN, int(170 + 85 * arrow_pulse if self._down > 0.01 else 80))
        p.setPen(QPen(down_col, 1))
        p.drawText(QRectF(W // 2, 2, W // 2 - 4, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   f"▼ {self._fmt(self._down)}/s")

        # sparklines area
        bh = 16
        by = 20
        bw = W - 16
        bx = 8

        if self._up_history:
            step = bw / max(len(self._up_history) - 1, 1)
            path = QPainterPath()
            first = True
            for i, v in enumerate(self._up_history):
                x = bx + i * step
                y = by + bh - (v / self._max_h) * bh
                if first:
                    path.moveTo(x, y)
                    first = False
                else:
                    path.lineTo(x, y)
            p.setPen(QPen(qcol(C.ACC, 100), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)

        if self._down_history:
            step = bw / max(len(self._down_history) - 1, 1)
            path = QPainterPath()
            first = True
            for i, v in enumerate(self._down_history):
                x = bx + i * step
                y = by + bh - (v / self._max_h) * bh
                if first:
                    path.moveTo(x, y)
                    first = False
                else:
                    path.lineTo(x, y)
            p.setPen(QPen(qcol(C.GREEN, 100), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)

        # up/down split bar at bottom
        total = self._up + self._down
        bar_h = 2
        bar_y = H - bar_h - 4
        if total > 0:
            up_fr = self._up / total
            up_w = max(1, int((W - 16) * up_fr))
            dn_w = max(0, int((W - 16) * (1 - up_fr)) - up_w)
            p.setBrush(QBrush(qcol(C.ACC, 140)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(8, bar_y, up_w, bar_h), 1, 1)
            if dn_w > 0:
                p.setBrush(QBrush(qcol(C.GREEN, 140)))
                p.drawRoundedRect(QRectF(8 + up_w, bar_y, dn_w, bar_h), 1, 1)

class LogWidget(QTextEdit):
    _sig = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(QFont("Courier New", 9))
        self.setStyleSheet(f"""
            QTextEdit {{
                background: {C.PANEL};
                color: {C.TEXT};
                border: 1px solid {C.BORDER};
                border-radius: 4px;
                padding: 6px;
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
        self._queue: list[str] = []
        self._typing  = False
        self._text    = ""
        self._pos     = 0
        self._tag     = "sys"
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._sig.connect(self._enqueue)

    def append_log(self, text: str):
        self._sig.emit(text)

    def _enqueue(self, text: str):
        self._queue.append(text)
        if not self._typing:
            self._next()

    def _next(self):
        if not self._queue:
            self._typing = False
            return
        self._typing = True
        self._text   = self._queue.pop(0)
        self._pos    = 0
        tl = self._text.lower()
        if   tl.startswith("you:"):    self._tag = "you"
        elif tl.startswith("nox:"):    self._tag = "ai"
        elif tl.startswith("file:"):   self._tag = "file"
        elif tl.startswith("[err"):    self._tag = "err"
        else:                          self._tag = "sys"
        self._tmr.start(6)

    def _step(self):
        if self._pos < len(self._text):
            ch  = self._text[self._pos]
            cur = self.textCursor()
            fmt = cur.charFormat()
            col = {
                "you":  qcol(C.WHITE),
                "ai":   qcol(C.PRI),
                "err":  qcol(C.RED),
                "file": qcol(C.GREEN),
                "sys":  qcol(C.ACC2),
            }.get(self._tag, qcol(C.TEXT))
            fmt.setForeground(QBrush(col))
            cur.movePosition(cur.MoveOperation.End)
            cur.insertText(ch, fmt)
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            self._pos += 1
        else:
            self._tmr.stop()
            cur = self.textCursor()
            cur.movePosition(cur.MoveOperation.End)
            cur.insertText("\n")
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            QTimer.singleShot(20, self._next)

_FILE_ICONS = {
    "image":   ("🖼", "#00d4ff"), "video":   ("🎬", "#ff6b00"),
    "audio":   ("🎵", "#cc44ff"), "pdf":     ("📄", "#ff4444"),
    "word":    ("📝", "#4488ff"), "excel":   ("📊", "#44bb44"),
    "code":    ("💻", "#ffcc00"), "archive": ("📦", "#ff8844"),
    "pptx":    ("📊", "#ff6622"), "text":    ("📃", "#aaaaaa"),
    "data":    ("🔧", "#88ddff"), "unknown": ("📎", "#888888"),
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
            self, "Select a file for NOX", str(Path.home()),
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
        p.setFont(QFont("Courier New", 8))
        p.setPen(QPen(qcol(C.PRI_DIM if not hover else C.TEXT), 1))
        p.drawText(QRectF(0, cy + 8, W, 16), Qt.AlignmentFlag.AlignCenter,
                   "Drop file here  or  Click to Browse")
        p.setFont(QFont("Courier New", 7))
        p.setPen(QPen(qcol("#1a4a5a"), 1))
        p.drawText(QRectF(0, cy + 24, W, 14), Qt.AlignmentFlag.AlignCenter,
                   "Images · Video · Audio · PDF · Docs · Code · Data")

    def _paint_drag_over(self, p, W, H):
        cx, cy = W / 2, H / 2
        p.setFont(QFont("Courier New", 20))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy - 24, W, 32), Qt.AlignmentFlag.AlignCenter, "⬇")
        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
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

        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.WHITE), 1))
        name = path.name if len(path.name) <= 34 else path.name[:31] + "..."
        p.drawText(QRectF(tx, H * 0.18, tw, 16),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)

        p.setFont(QFont("Courier New", 7))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(tx, H * 0.18 + 18, tw, 14),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f"{ext_str}  ·  {size_str}")

        p.setFont(QFont("Courier New", 6))
        p.setPen(QPen(qcol("#1e5c6a"), 1))
        par = str(path.parent)
        if len(par) > 42: par = "…" + par[-41:]
        p.drawText(QRectF(tx, H * 0.18 + 34, tw, 12),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, par)

        p.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.RED, 180), 1))
        p.drawText(QRectF(W - 34, 0, 28, H), Qt.AlignmentFlag.AlignCenter, "✕")

    def mousePressEvent(self, e):
        z = self._z
        if z._current_file and e.pos().x() > self.width() - 34:
            z.clear_file()
        else:
            z.mousePressEvent(e)


class SetupOverlay(QWidget):
    done = pyqtSignal(str, str, str)

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
            w.setFont(QFont("Courier New", font_size,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            return w

        layout.addWidget(_lbl("◈  INITIALISATION REQUIRED", 13, True))
        layout.addWidget(_lbl("Configure N O X. before first boot.", 9, color=C.PRI_DIM))
        layout.addSpacing(6)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER};"); layout.addWidget(sep)
        layout.addSpacing(4)

        layout.addWidget(_lbl("GEMINI API KEY", 8, color=C.TEXT_DIM,
                               align=Qt.AlignmentFlag.AlignLeft))
        self._key_input = QLineEdit()
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_input.setPlaceholderText("AIza…")
        self._key_input.setFont(QFont("Courier New", 10))
        self._key_input.setFixedHeight(32)
        self._key_input.setStyleSheet(f"""
            QLineEdit {{
                background: #000d12; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 3px; padding: 4px 8px;
            }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
        """)
        layout.addWidget(self._key_input)
        layout.addSpacing(8)

        layout.addWidget(_lbl("OPENROUTER API KEY", 8, color=C.TEXT_DIM,
                       align=Qt.AlignmentFlag.AlignLeft))
        self._or_input = QLineEdit()
        self._or_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._or_input.setPlaceholderText("sk-or-…")
        self._or_input.setFont(QFont("Courier New", 10))
        self._or_input.setFixedHeight(32)
        self._or_input.setStyleSheet(f"""
            QLineEdit {{
                background: #000d12; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 3px; padding: 4px 8px;
            }}
            QLineEdit:focus {{ border: 1px solid {C.ACC2}; }}
        """)
        layout.addWidget(self._or_input)

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
        for key, label in [("windows","⊞  Windows"),("mac","  macOS"),("linux","🐧  Linux")]:
            btn = QPushButton(label)
            btn.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
            btn.setFixedHeight(32)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, k=key: self._sel(k))
            os_row.addWidget(btn)
            self._os_btns[key] = btn
        layout.addLayout(os_row)
        self._sel(detected)
        layout.addSpacing(12)

        init_btn = QPushButton("▸  INITIALISE SYSTEMS")
        init_btn.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
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
        or_key = self._or_input.text().strip()
        if not key and not or_key:
            self._key_input.setStyleSheet(
                self._key_input.styleSheet() +
                f" QLineEdit {{ border: 1px solid {C.RED}; }}"
            )
            self._or_input.setStyleSheet(
                self._or_input.styleSheet() +
                f" QLineEdit {{ border: 1px solid {C.RED}; }}"
            )
            return
        self.done.emit(key, or_key, self._sel_os)


class _HoloLabel(QLabel):
    def __init__(self, txt, col, parent=None):
        super().__init__(txt, parent)
        self._hcol = col
        self.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        _draw_holo_brackets(p, self.width(), self.height(), self._hcol, cl=6, a_main=60)
        p.setPen(QPen(qcol(self._hcol, 180), 1))
        p.setFont(self.font())
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.text())


class MainWindow(QMainWindow):
    _log_sig   = pyqtSignal(str)
    _state_sig = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("NOX — Dev FirstIA")
        self.setMinimumSize(_MIN_W, _MIN_H)
        self.resize(_DEFAULT_W, _DEFAULT_H)

        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            (screen.width()  - _DEFAULT_W) // 2,
            (screen.height() - _DEFAULT_H) // 2,
        )

        self.on_text_command  = None
        self._muted           = False
        self._current_file: str | None = None

        central = QWidget()
        central.setStyleSheet(f"background: {C.BG};")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self._left_panel = self._build_left_panel()
        body.addWidget(self._left_panel, stretch=0)

        self.hud = HudCanvas()
        self.hud.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        body.addWidget(self.hud, stretch=5)

        self._right_panel = self._build_right_panel()
        body.addWidget(self._right_panel, stretch=0)

        root.addLayout(body, stretch=1)
        root.addWidget(self._build_footer())

        self._clock_tmr = QTimer(self)
        self._clock_tmr.timeout.connect(self._tick_clock)
        self._clock_tmr.start(1000)
        self._tick_clock()

        # Metrik güncelleme timer'ı
        self._metric_tmr = QTimer(self)
        self._metric_tmr.timeout.connect(self._update_metrics)
        self._metric_tmr.start(1000)
        self._update_metrics()

        self._log_sig.connect(self._log.append_log)
        self._state_sig.connect(self._apply_state)

        self._overlay: SetupOverlay | None = None
        self._ready = self._check_config()
        if not self._ready:
            self._show_setup()

        sc_mute = QShortcut(QKeySequence("F4"), self)
        sc_mute.activated.connect(self._toggle_mute)
        sc_full = QShortcut(QKeySequence("F11"), self)
        sc_full.activated.connect(self._toggle_fullscreen)

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._overlay and self._overlay.isVisible():
            ow, oh = 460, 390
            cw = self.centralWidget()
            self._overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )

    def _update_metrics(self):
        snap = _metrics.snapshot()

        cpu = snap["cpu"]
        self._bar_cpu.set_value(cpu, f"{cpu:.0f}%")
        self._bar_cpu.set_history(snap["cpu_history"])
        self._cpu_cores.set_cores(snap["cpu_cores"])

        mem = snap["mem"]
        self._bar_mem.set_value(mem, f"{mem:.0f}%")
        self._bar_mem.set_history(snap["mem_history"])

        nu, nd = snap["net_up"], snap["net_down"]
        self._bar_net.set_values(nu, nd, snap["net_up_history"], snap["net_down_history"])

        gpu = snap["gpu"]
        if gpu >= 0:
            self._bar_gpu.set_value(gpu, f"{gpu:.0f}%")
            self._bar_gpu.set_history(snap["gpu_history"])
        else:
            self._bar_gpu.set_value(0, "N/A")

        tmp = snap["tmp"]
        if tmp >= 0:
            tmp_pct = min(100, (tmp / 100) * 100)
            self._bar_tmp.set_value(tmp_pct, f"{tmp:.0f}°C")
        else:
            self._bar_tmp.set_value(0, "N/A")

        try:
            boot_t  = psutil.boot_time()
            elapsed = time.time() - boot_t
            h = int(elapsed // 3600)
            m = int((elapsed % 3600) // 60)
            self._uptime_lbl.setText(f"UP  {h:02d}:{m:02d}")
        except Exception:
            self._uptime_lbl.setText("UP  --:--")

        try:
            proc_count = len(psutil.pids())
            self._proc_lbl.setText(f"PROC  {proc_count}")
        except Exception:
            self._proc_lbl.setText("PROC  --")

        conns = snap["connections"]
        self._conn_lbl.setText(f"CONN  {conns}")

        procs = snap["top_processes"]
        self._top_proc_lbl.setText(
            "PROC  " + "  ".join(f"{n[:6]} {c:.1f}%" for n, c in procs[:3])
            if procs else "PROC  --"
        )

        self._update_quota()

    def _update_quota(self):
        try:
            db = Path("memory/procedural.db")
            if db.exists():
                import sqlite3
                conn = sqlite3.connect(str(db))
                total = conn.execute("SELECT COUNT(*) FROM tool_log").fetchone()[0]
                fails = conn.execute("SELECT COUNT(*) FROM tool_log WHERE success=0").fetchone()[0]
                conn.close()
                self._q_tool_calls.setText(f"TL  {total} calls")
                fail_pct = f" ({fails/total*100:.0f}%)" if total else ""
                self._q_tool_fails.setText(f"FL  {fails} fails{fail_pct}")
        except Exception:
            pass

    def _build_header(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(54)
        w.setStyleSheet(f"background: {C.DARK}; border-bottom: 1px solid {C.BORDER_B};")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(16, 0, 16, 0)

        def _badge(txt, color=C.TEXT_MED):
            l = QLabel(txt)
            l.setFont(QFont("Courier New", 8))
            l.setStyleSheet(f"color: {color}; background: transparent;")
            return l

        lay.addWidget(_badge("NOX", C.PRI_DIM))
        lay.addStretch()

        mid = QVBoxLayout(); mid.setSpacing(1)
        title = QLabel("N O X")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont("Courier New", 17, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        mid.addWidget(title)
        sub = QLabel("Dev · FirstIA · Cyber Security")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setFont(QFont("Courier New", 7))
        sub.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent;")
        mid.addWidget(sub)
        lay.addLayout(mid)
        lay.addStretch()

        right_col = QVBoxLayout(); right_col.setSpacing(2)
        self._clock_lbl = QLabel("00:00:00")
        self._clock_lbl.setFont(QFont("Courier New", 14, QFont.Weight.Bold))
        self._clock_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        self._clock_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_col.addWidget(self._clock_lbl)
        self._date_lbl = QLabel("")
        self._date_lbl.setFont(QFont("Courier New", 7))
        self._date_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        self._date_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_col.addWidget(self._date_lbl)
        lay.addLayout(right_col)
        return w

    def _tick_clock(self):
        self._clock_lbl.setText(time.strftime("%H:%M:%S"))
        self._date_lbl.setText(time.strftime("%a %d %b %Y"))

    def _build_left_panel(self) -> QWidget:
        w = QWidget()
        w.setFixedWidth(_LEFT_W)
        w.setStyleSheet(f"background: {C.DARK}; border-right: 1px solid {C.BORDER};")

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }"
                             "QScrollBar:vertical { width: 4px; background: transparent; }"
                             "QScrollBar::handle:vertical { background: #0d3347; border-radius: 2px; }")

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(6, 8, 6, 8)
        lay.setSpacing(3)

        hdr = QLabel("◈ SYS MONITOR")
        hdr.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI}; background: transparent; "
                          f"border-bottom: 1px solid {C.BORDER}; padding-bottom: 3px;")
        lay.addWidget(hdr)
        lay.addSpacing(1)

        self._bar_cpu = MetricBar("CPU", C.PRI)
        self._cpu_cores = CpuCoresWidget()
        self._bar_mem = MetricBar("MEM", C.ACC2)
        self._bar_net = NetworkWidget()
        self._bar_gpu = MetricBar("GPU", C.ACC)
        self._bar_tmp = MetricBar("TMP", "#ff6688")

        lay.addWidget(self._bar_cpu)
        lay.addWidget(self._cpu_cores)
        lay.addWidget(self._bar_mem)
        lay.addWidget(self._bar_net)
        lay.addWidget(self._bar_gpu)
        lay.addWidget(self._bar_tmp)

        lay.addSpacing(2)

        info_panel = QWidget()
        ip_lay = QVBoxLayout(info_panel)
        ip_lay.setContentsMargins(5, 4, 5, 4)
        ip_lay.setSpacing(1)

        self._uptime_lbl = QLabel("UP  --:--")
        self._uptime_lbl.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        self._uptime_lbl.setStyleSheet(f"color: {C.GREEN}; background: transparent; border: none;")
        ip_lay.addWidget(self._uptime_lbl)

        self._proc_lbl = QLabel("PROC  --")
        self._proc_lbl.setFont(QFont("Courier New", 7))
        self._proc_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        ip_lay.addWidget(self._proc_lbl)

        self._conn_lbl = QLabel("CONN  --")
        self._conn_lbl.setFont(QFont("Courier New", 7))
        self._conn_lbl.setStyleSheet(f"color: {C.ACC2}; background: transparent; border: none;")
        ip_lay.addWidget(self._conn_lbl)

        self._top_proc_lbl = QLabel("")
        self._top_proc_lbl.setFont(QFont("Courier New", 6))
        self._top_proc_lbl.setStyleSheet(f"color: {C.ACC}; background: transparent; border: none;")
        self._top_proc_lbl.setWordWrap(True)
        ip_lay.addWidget(self._top_proc_lbl)

        os_name = {"Windows": "WIN", "Darwin": "macOS", "Linux": "LINUX"}.get(_OS, _OS.upper())
        os_lbl = QLabel(f"OS  {os_name}")
        os_lbl.setFont(QFont("Courier New", 7))
        os_lbl.setStyleSheet(f"color: {C.ACC2}; background: transparent; border: none;")
        ip_lay.addWidget(os_lbl)

        lay.addWidget(info_panel)

        sep_q = QFrame()
        sep_q.setFrameShape(QFrame.Shape.HLine)
        sep_q.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep_q)

        q_hdr = QLabel("◈ API QUOTA")
        q_hdr.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        q_hdr.setStyleSheet(f"color: {C.ACC2}; background: transparent; "
                            f"border-bottom: 1px solid {C.BORDER}; padding-bottom: 3px;")
        lay.addWidget(q_hdr)
        lay.addSpacing(1)

        self._q_or_total = QLabel("OR  -- req")
        self._q_or_total.setFont(QFont("Courier New", 7))
        self._q_or_total.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        lay.addWidget(self._q_or_total)

        self._q_or_rate = QLabel("OR  rate --")
        self._q_or_rate.setFont(QFont("Courier New", 6))
        self._q_or_rate.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
        lay.addWidget(self._q_or_rate)

        self._q_gemini = QLabel("GM  -- req")
        self._q_gemini.setFont(QFont("Courier New", 7))
        self._q_gemini.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        lay.addWidget(self._q_gemini)

        self._q_tool_calls = QLabel("TL  -- calls")
        self._q_tool_calls.setFont(QFont("Courier New", 7))
        self._q_tool_calls.setStyleSheet(f"color: {C.PRI}; background: transparent; border: none;")
        lay.addWidget(self._q_tool_calls)

        self._q_tool_fails = QLabel("FL  -- fails")
        self._q_tool_fails.setFont(QFont("Courier New", 6))
        self._q_tool_fails.setStyleSheet(f"color: {C.ACC}; background: transparent; border: none;")
        lay.addWidget(self._q_tool_fails)

        lay.addStretch()

        for txt, col in [
            ("AI CORE\nACTIVE",     C.GREEN),
            ("SEC\nCLEARED",        C.PRI),
            ("PROTOCOL\nXXXVIII",   C.TEXT_DIM),
        ]:
            lbl = _HoloLabel(txt, col)
            lay.addWidget(lbl)

        scroll.setWidget(inner)
        outer_lay = QVBoxLayout(w)
        outer_lay.setContentsMargins(0, 0, 0, 0)
        outer_lay.addWidget(scroll)
        return w
    def _build_right_panel(self) -> QWidget:
        w = QWidget()
        w.setFixedWidth(_RIGHT_W)
        w.setStyleSheet(f"background: {C.DARK}; border-left: 1px solid {C.BORDER};")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        def _sec(txt):
            l = QLabel(f"▸ {txt}")
            l.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
            l.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
            return l

        lay.addWidget(_sec("ACTIVITY LOG"))
        self._log = LogWidget()
        lay.addWidget(self._log, stretch=1)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep)

        lay.addWidget(_sec("FILE UPLOAD"))
        self._drop_zone = FileDropZone()
        self._drop_zone.file_selected.connect(self._on_file_selected)
        lay.addWidget(self._drop_zone)

        self._file_hint = QLabel("No file loaded — drop or click above to upload")
        self._file_hint.setFont(QFont("Courier New", 7))
        self._file_hint.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        self._file_hint.setWordWrap(True)
        lay.addWidget(self._file_hint)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep2)

        lay.addWidget(_sec("COMMAND INPUT"))
        lay.addLayout(self._build_input_row())

        self._mute_btn = QPushButton("🎙  MICROPHONE ACTIVE")
        self._mute_btn.setFixedHeight(30)
        self._mute_btn.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._mute_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mute_btn.clicked.connect(self._toggle_mute)
        self._style_mute_btn()
        lay.addWidget(self._mute_btn)

        self._dev_btn = QPushButton("🛠  DEV TOOLS: OFF")
        self._dev_btn.setFixedHeight(30)
        self._dev_btn.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._dev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dev_btn.clicked.connect(self._toggle_dev)
        self._style_dev_btn()
        lay.addWidget(self._dev_btn)

        fs_btn = QPushButton("⛶  FULLSCREEN  [F11]")
        fs_btn.setFixedHeight(26)
        fs_btn.setFont(QFont("Courier New", 7))
        fs_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        fs_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px;
            }}
            QPushButton:hover {{
                color: {C.PRI}; border: 1px solid {C.BORDER_B};
            }}
        """)
        fs_btn.clicked.connect(self._toggle_fullscreen)
        lay.addWidget(fs_btn)

        return w

    def _build_input_row(self) -> QHBoxLayout:
        row = QHBoxLayout(); row.setSpacing(5)
        self._input = QLineEdit()
        self._input.setPlaceholderText("Type a command or question…")
        self._input.setFont(QFont("Courier New", 9))
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
        send.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
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

    def _build_footer(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(22)
        w.setStyleSheet(f"background: {C.DARK}; border-top: 1px solid {C.BORDER};")
        lay = QHBoxLayout(w); lay.setContentsMargins(14, 0, 14, 0)

        def _fl(txt, color=C.TEXT_MED):
            l = QLabel(txt); l.setFont(QFont("Courier New", 7))
            l.setStyleSheet(f"color: {color}; background: transparent;")
            return l

        lay.addWidget(_fl("[F4] Mute  ·  [F11] Fullscreen"))
        lay.addStretch()
        lay.addWidget(_fl("GENESIS  ·  NOX  ·  CLASSIFIED"))
        lay.addStretch()
        lay.addWidget(_fl("© NOX SYSTEMS", C.PRI_DIM))
        return w

    def _on_file_selected(self, path: str):
        self._current_file = path
        p    = Path(path)
        cat  = _file_category(p)
        icon, _ = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size = _fmt_size(p.stat().st_size)
        self._file_hint.setText(f"{icon}  {p.name}  ·  {size}  ·  Tell NOX what to do with it")
        self._log.append_log(f"FILE: {p.name} ({size}) loaded")
        if self.on_text_command:
            msg = (
                f"[FILE_UPLOADED] path={path} | name={p.name} | "
                f"type={p.suffix.lstrip('.')} | size={size} | "
                f"Briefly tell the user you can see the file '{p.name}' "
                f"({size}) has been uploaded and ask what they'd like to do with it."
            )
            threading.Thread(target=self.on_text_command, args=(msg,), daemon=True).start()

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
            self._mute_btn.setText("🔇  MICROPHONE MUTED")
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #140006; color: {C.MUTED_C};
                    border: 1px solid {C.MUTED_C}; border-radius: 3px;
                }}
            """)
        else:
            self._mute_btn.setText("🎙  MICROPHONE ACTIVE")
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #00140a; color: {C.GREEN};
                    border: 1px solid {C.GREEN}; border-radius: 3px;
                }}
                QPushButton:hover {{ background: #001f10; }}
            """)

    def _toggle_dev(self):
        from memory.config_manager import code_execution_allowed, set_code_execution_allowed
        new_val = not code_execution_allowed()
        set_code_execution_allowed(new_val)
        self._style_dev_btn()
        if new_val:
            self._log.append_log("SYS: Dev tools enabled — generated code may run.")
        else:
            self._log.append_log("SYS: Dev tools disabled — generated code blocked.")

    def _style_dev_btn(self):
        from memory.config_manager import code_execution_allowed
        if code_execution_allowed():
            self._dev_btn.setText("🛠  DEV TOOLS: ON")
            self._dev_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #140a00; color: {C.ACC};
                    border: 1px solid {C.ACC}; border-radius: 3px;
                }}
                QPushButton:hover {{ background: #1f1000; }}
            """)
        else:
            self._dev_btn.setText("🛠  DEV TOOLS: OFF")
            self._dev_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #00140a; color: {C.GREEN};
                    border: 1px solid {C.GREEN}; border-radius: 3px;
                }}
                QPushButton:hover {{ background: #001f10; }}
            """)

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

    def _check_config(self) -> bool:
        if not API_FILE.exists(): return False
        try:
            d = json.loads(API_FILE.read_text(encoding="utf-8"))
            if not bool(d.get("os_system")):
                return False
            return bool(d.get("gemini_api_key") or d.get("openrouter_api_key") or d.get("moonshot_api_key"))
        except Exception:
            return False

    def _show_setup(self):
        ov = SetupOverlay(self.centralWidget())
        cw = self.centralWidget()
        ow, oh = 460, 430
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.done.connect(self._on_setup_done)
        ov.show()
        self._overlay = ov

    # Change signature:
    def _on_setup_done(self, key: str, or_key: str, os_name: str):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        existing = {}
        if API_FILE.exists():
            try:
                existing = json.loads(API_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        existing.update({
            "gemini_api_key": key or existing.get("gemini_api_key", ""),
            "openrouter_api_key": or_key or existing.get("openrouter_api_key", ""),
            "os_system": os_name,
        })
        API_FILE.write_text(json.dumps(existing, indent=4), encoding="utf-8")
        self._ready = True
        if self._overlay:
            self._overlay.hide()
            self._overlay = None
        self._apply_state("LISTENING")
        self._log.append_log(f"SYS: Initialised. OS={os_name.upper()}. NOX online.")

class _RootShim:
    def __init__(self, app: QApplication):
        self._app = app
    def mainloop(self):
        self._app.exec()
    def protocol(self, *_):
        pass


class NoxUI:
    def __init__(self, size=None):
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._app.setStyle("Fusion")
        self._win = MainWindow()
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

    def set_state(self, state: str):
        self._win._state_sig.emit(state)

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