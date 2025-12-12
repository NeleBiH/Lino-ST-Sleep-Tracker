# Lino-ST — Your Desktop Sleep Tracker (PySide6)
# Version: 0.2
# Created by Nele
# License: MIT
#
# Features:
# - Start/Stop microphone monitoring
# - Auto-record to ./recordings when level crosses threshold (pre-roll & hang time + hysteresis)
# - Live microphone meter (dB and percentage)
# - Per-clip list with Play/Stop and Delete
# - Language switcher (EN/HR/DE) with instant relabeling
# - Sleep session history (Day/Start/End/Sleep Duration)
# - Loads existing recordings on startup
# - Export recordings to ZIP
# - Delete all recordings
#
# Setup helper:
# - Run:  python "Lino-ST.py" --setup
#   Detects your Linux distro and installs system packages for PortAudio/ALSA (needs sudo),
#   then pip-installs PySide6, numpy, sounddevice, soundfile.
#   Sudo je potreban jer se instaliraju **sistemske** biblioteke (PortAudio).

import sys, os, json, queue, datetime, collections, typing, weakref, subprocess
import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
import sounddevice as sd

VERSION = "0.2"
APP_DIR = os.path.dirname(os.path.abspath(__file__))


# ===================== Wake Lock (prevent sleep/hibernate) =====================
class WakeLock:
    """Prevent system sleep/hibernate while monitoring. Display can still turn off."""

    def __init__(self):
        self._inhibit_fd = None
        self._dbus_cookie = None

    def acquire(self) -> bool:
        """Acquire wake lock to prevent sleep/hibernate."""
        # Try systemd-inhibit first (works on most modern Linux)
        if self._try_systemd_inhibit():
            return True
        # Try D-Bus org.freedesktop.ScreenSaver
        if self._try_dbus_screensaver():
            return True
        # Try D-Bus org.gnome.SessionManager
        if self._try_dbus_gnome():
            return True
        return False

    def release(self):
        """Release wake lock."""
        if self._inhibit_fd is not None:
            try:
                os.close(self._inhibit_fd)
            except Exception:
                pass
            self._inhibit_fd = None
        if self._dbus_cookie is not None:
            self._release_dbus()
            self._dbus_cookie = None

    def _try_systemd_inhibit(self) -> bool:
        """Use systemd-inhibit via file descriptor."""
        try:
            import socket

            # Connect to systemd via D-Bus
            bus_path = os.environ.get(
                "DBUS_SYSTEM_BUS_ADDRESS", "unix:path=/run/dbus/system_bus_socket"
            )
            # Simpler approach: use subprocess with systemd-inhibit
            # This keeps a process running that holds the inhibit lock
            return False  # Skip this, use D-Bus method instead
        except Exception:
            return False

    def _try_dbus_screensaver(self) -> bool:
        """Use org.freedesktop.ScreenSaver D-Bus interface."""
        try:
            import dbus

            bus = dbus.SessionBus()
            obj = bus.get_object(
                "org.freedesktop.ScreenSaver", "/org/freedesktop/ScreenSaver"
            )
            iface = dbus.Interface(obj, "org.freedesktop.ScreenSaver")
            # Inhibit sleep (not screen saver - we allow display off)
            self._dbus_cookie = iface.Inhibit("Lino-ST", "Recording sleep audio")
            self._dbus_interface = iface
            self._dbus_method = "freedesktop"
            return True
        except Exception:
            return False

    def _try_dbus_gnome(self) -> bool:
        """Use org.gnome.SessionManager D-Bus interface."""
        try:
            import dbus

            bus = dbus.SessionBus()
            obj = bus.get_object(
                "org.gnome.SessionManager", "/org/gnome/SessionManager"
            )
            iface = dbus.Interface(obj, "org.gnome.SessionManager")
            # Flags: 4 = Inhibit suspend/hibernate
            self._dbus_cookie = iface.Inhibit("Lino-ST", 0, "Recording sleep audio", 4)
            self._dbus_interface = iface
            self._dbus_method = "gnome"
            return True
        except Exception:
            return False

    def _release_dbus(self):
        """Release D-Bus inhibit."""
        try:
            if hasattr(self, "_dbus_interface") and self._dbus_cookie:
                if self._dbus_method == "gnome":
                    self._dbus_interface.Uninhibit(self._dbus_cookie)
                else:
                    self._dbus_interface.UnInhibit(self._dbus_cookie)
        except Exception:
            pass


# ===================== setup helper =====================
def detect_distro() -> str:
    try:
        with open("/etc/os-release", "r", encoding="utf-8") as f:
            data = f.read().lower()

        def val(k):
            for line in data.splitlines():
                if line.startswith(k + "="):
                    return line.split("=", 1)[1].strip().strip('"')
            return ""

        blob = val("id") + " " + val("id_like")
        if any(x in blob for x in ["ubuntu", "debian", "linuxmint", "elementary"]):
            return "debian"
        if any(x in blob for x in ["fedora", "rhel", "centos"]):
            return "fedora"
        if "arch" in blob:
            return "arch"
        if any(x in blob for x in ["opensuse", "suse", "sle"]):
            return "opensuse"
        return val("id") or ""
    except Exception:
        return ""


def system_install_cmd(distro: str) -> str:
    if distro == "debian":
        return (
            "sudo apt update && sudo apt install -y "
            "libportaudio2 portaudio19-dev python3-dev libsndfile1 "
            "gstreamer1.0-plugins-base gstreamer1.0-plugins-good "
            "gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly"
        )
    if distro == "fedora":
        return (
            "sudo dnf install -y portaudio portaudio-devel python3-devel libsndfile "
            "gstreamer1-plugins-base gstreamer1-plugins-good "
            "gstreamer1-plugins-bad-free gstreamer1-plugins-ugly"
        )
    if distro == "arch":
        return (
            "sudo pacman -S --noconfirm portaudio libsndfile gstreamer "
            "gst-plugins-base gst-plugins-good gst-plugins-bad gst-plugins-ugly"
        )
    if distro == "opensuse":
        return (
            "sudo zypper install -y portaudio-devel libsndfile1 "
            "gstreamer-plugins-base gstreamer-plugins-good "
            "gstreamer-plugins-bad gstreamer-plugins-ugly"
        )
    return "echo 'Install PortAudio + GStreamer (base/good/bad/ugly) + libsndfile on your distro'"


def pip_install_cmd() -> str:
    py = sys.executable
    return f"{py} -m pip install -U pip && {py} -m pip install PySide6 numpy sounddevice soundfile"


if "--setup" in sys.argv:
    d = detect_distro()
    print(f"[setup] distro: {d or 'unknown'}")
    print("[setup] will run:\n ", system_install_cmd(d), "\n ", pip_install_cmd())
    ok = input("[setup] proceed (needs sudo)? [y/N]: ").strip().lower() == "y"
    if not ok:
        sys.exit(0)
    subprocess.call(system_install_cmd(d), shell=True)
    subprocess.call(pip_install_cmd(), shell=True)
    print("[setup] done. Re-run the app.")
    sys.exit(0)

# ===================== THEME/QSS =====================
THEME_PALETTE = dict(
    bg1="#0B1220",
    bg2="#0B1A36",
    fg="#E5E7EB",
    card="rgba(17,25,40,0.55)",
    border="rgba(255,255,255,0.12)",
    accent="#6366F1",
    accent2="#4F46E5",
    muted="#94a3b8",
)


def qss_for(p: dict) -> str:
    btn_fg = "#000" if p["accent2"].lower() in ("#ffffff", "#fff") else p["fg"]
    sel_fg = "#000" if p["accent2"].lower() in ("#ffffff", "#fff") else "#fff"
    return f"""
* {{ font-family: Inter, "Segoe UI", Roboto, Arial; color: {p["fg"]}; }}
QWidget#root {{
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {p["bg1"]}, stop:1 {p["bg2"]});
}}

/* Cards - Glossy effect */
QFrame.card {{
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 rgba(255,255,255,0.12),
    stop:0.03 rgba(255,255,255,0.08),
    stop:0.5 {p["card"]},
    stop:1 rgba(0,0,0,0.15));
  border: 1px solid {p["border"]};
  border-top: 1px solid rgba(255,255,255,0.18);
  border-radius: 16px;
}}

/* Badges - Glossy */
QLabel.badge {{
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 rgba(255,255,255,0.18),
    stop:0.5 rgba(255,255,255,0.10),
    stop:1 rgba(255,255,255,0.05));
  border-radius: 12px;
  padding: 4px 10px;
  font-size: 12px;
  border: 1px solid rgba(255,255,255,0.1);
}}

/* Buttons - Glossy with bloom */
QPushButton {{
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 rgba(255,255,255,0.15),
    stop:0.4 {p["accent2"]},
    stop:1 rgba(0,0,0,0.2));
  color: {btn_fg};
  padding: 10px 16px;
  border-radius: 14px;
  border: 1px solid rgba(255,255,255,0.15);
  border-bottom: 1px solid rgba(0,0,0,0.3);
}}
QPushButton:hover {{
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 rgba(255,255,255,0.25),
    stop:0.4 {p["accent"]},
    stop:1 rgba(0,0,0,0.15));
}}
QPushButton[variant="ghost"] {{
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 rgba(255,255,255,0.12),
    stop:0.5 rgba(255,255,255,0.06),
    stop:1 rgba(0,0,0,0.1));
  border: 1px solid rgba(255,255,255,0.08);
}}
QPushButton[variant="ghost"]:hover {{
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 rgba(255,255,255,0.20),
    stop:0.5 rgba(255,255,255,0.12),
    stop:1 rgba(0,0,0,0.08));
}}
QPushButton[variant="pill"] {{
  background: {p["accent"]};
  color: #fff;
  border-radius: 22px; padding: 14px 22px; font-weight:600;
  border: none;
}}
QPushButton[variant="pill"]:hover {{
  background: {p["accent2"]};
}}

/* Dialog buttons - same style as ghost buttons */
QDialogButtonBox QPushButton {{
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 rgba(255,255,255,0.12),
    stop:0.5 rgba(255,255,255,0.06),
    stop:1 rgba(0,0,0,0.1));
  border: 1px solid rgba(255,255,255,0.08);
  color: {p["fg"]};
  padding: 10px 16px;
  border-radius: 14px;
}}
QDialogButtonBox QPushButton:hover {{
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 rgba(255,255,255,0.20),
    stop:0.5 rgba(255,255,255,0.12),
    stop:1 rgba(0,0,0,0.08));
}}

/* Tabs - Glossy */
QTabWidget::pane {{ border:0; margin-top:6px; }}
QTabBar::tab {{
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 rgba(255,255,255,0.10),
    stop:0.5 rgba(255,255,255,0.04),
    stop:1 rgba(0,0,0,0.05));
  padding: 6px 12px;
  border-radius: 10px; margin-right: 6px;
  border: 1px solid rgba(255,255,255,0.06);
}}
QTabBar::tab:selected {{
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 rgba(255,255,255,0.22),
    stop:0.5 rgba(255,255,255,0.12),
    stop:1 rgba(0,0,0,0.08));
  border: 1px solid rgba(255,255,255,0.12);
}}

/* Progress - Glossy bloom effect */
QProgressBar {{
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 rgba(0,0,0,0.3),
    stop:0.5 rgba(255,255,255,0.05),
    stop:1 rgba(0,0,0,0.2));
  border: 1px solid {p["border"]};
  border-radius: 10px; height: 20px; text-align:center;
}}
QProgressBar::chunk {{
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 rgba(255,255,255,0.3),
    stop:0.3 {p["accent"]},
    stop:0.7 {p["accent2"]},
    stop:1 rgba(0,0,0,0.2));
  border-radius: 9px;
}}

/* Slider - Thick glossy progress-bar style */
QSlider::groove:horizontal {{
  height: 16px;
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 rgba(0,0,0,0.4),
    stop:0.3 rgba(255,255,255,0.08),
    stop:0.7 rgba(255,255,255,0.04),
    stop:1 rgba(0,0,0,0.3));
  border-radius: 8px;
  border: 1px solid rgba(255,255,255,0.1);
}}
QSlider::sub-page:horizontal {{
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 rgba(255,255,255,0.35),
    stop:0.3 {p["accent"]},
    stop:0.7 {p["accent2"]},
    stop:1 rgba(0,0,0,0.25));
  border-radius: 8px;
}}
QSlider::handle:horizontal {{
  width: 22px; height: 22px; margin: -4px 0;
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 rgba(255,255,255,0.9),
    stop:0.5 rgba(220,220,240,1),
    stop:1 rgba(180,180,200,1));
  border: 2px solid {p["accent"]};
  border-radius: 11px;
}}
QSlider::handle:horizontal:hover {{
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 #ffffff,
    stop:0.5 rgba(240,240,255,1),
    stop:1 rgba(200,200,220,1));
  border: 2px solid {p["accent2"]};
}}

/* ComboBox - Glossy */
QComboBox {{
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 rgba(255,255,255,0.12),
    stop:0.5 {p["card"]},
    stop:1 rgba(0,0,0,0.15));
  border: 1px solid {p["border"]};
  border-top: 1px solid rgba(255,255,255,0.15);
  padding: 8px 12px; border-radius: 10px;
}}
QComboBox::drop-down {{ width: 22px; border: 0; }}
QComboBox QAbstractItemView {{
  background: {p["card"]}; color: {p["fg"]}; border: 1px solid {p["border"]};
  selection-background-color: {p["accent"]};
  selection-color: {sel_fg};
}}

/* Table card wrapper - Glossy */
QFrame.tableCard {{
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 rgba(255,255,255,0.10),
    stop:0.02 rgba(255,255,255,0.06),
    stop:0.5 {p["card"]},
    stop:1 rgba(0,0,0,0.12));
  border: 1px solid {p["border"]};
  border-top: 1px solid rgba(255,255,255,0.15);
  border-radius: 16px;
}}

/* Tables */
QTableWidget, QTableView {{
  background: transparent;
  border: none;
  gridline-color: {p["border"]};
  selection-background-color: {p["accent"]};
  selection-color: {sel_fg};
  alternate-background-color: rgba(255,255,255,0.03);
}}
QTableView::item {{ padding: 8px 10px; }}
QHeaderView::section {{
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 rgba(255,255,255,0.12),
    stop:0.5 rgba(255,255,255,0.06),
    stop:1 rgba(0,0,0,0.1));
  color: {p["fg"]};
  border: 0;
  border-bottom: 1px solid {p["border"]};
  padding: 10px 12px;
  font-weight: 600;
}}
QTableCornerButton::section {{
  background: rgba(255,255,255,0.08);
  border: 0;
  border-bottom: 1px solid {p["border"]};
}}

QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{
  background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
    stop:0 rgba(255,255,255,0.25),
    stop:0.5 rgba(255,255,255,0.18),
    stop:1 rgba(255,255,255,0.12));
  border-radius: 5px;
}}
"""


# ===================== icons =====================
def icon_play(size=20, color="#ffffff") -> QtGui.QIcon:
    pix = QtGui.QPixmap(size, size)
    pix.fill(QtCore.Qt.GlobalColor.transparent)
    p = QtGui.QPainter(pix)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    p.setBrush(QtGui.QColor(color))
    p.setPen(QtCore.Qt.PenStyle.NoPen)
    path = QtGui.QPainterPath()
    path.moveTo(size * 0.32, size * 0.24)
    path.lineTo(size * 0.32, size * 0.76)
    path.lineTo(size * 0.78, size * 0.5)
    path.closeSubpath()
    p.drawPath(path)
    p.end()
    return QtGui.QIcon(pix)


def icon_stop(size=20, color="#ffffff") -> QtGui.QIcon:
    pix = QtGui.QPixmap(size, size)
    pix.fill(QtCore.Qt.GlobalColor.transparent)
    p = QtGui.QPainter(pix)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    p.setBrush(QtGui.QColor(color))
    p.setPen(QtCore.Qt.PenStyle.NoPen)
    r = QtCore.QRectF(size * 0.28, size * 0.28, size * 0.44, size * 0.44)
    p.drawRoundedRect(r, 4, 4)
    p.end()
    return QtGui.QIcon(pix)


def icon_trash(size=18, color="#ffffff") -> QtGui.QIcon:
    pix = QtGui.QPixmap(size, size)
    pix.fill(QtCore.Qt.GlobalColor.transparent)
    p = QtGui.QPainter(pix)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    pen = QtGui.QPen(QtGui.QColor(color))
    pen.setWidth(2)
    p.setPen(pen)
    p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
    p.drawRect(QtCore.QRectF(size * 0.28, size * 0.35, size * 0.44, size * 0.46))
    p.drawLine(
        QtCore.QPointF(size * 0.24, size * 0.35),
        QtCore.QPointF(size * 0.76, size * 0.35),
    )
    p.drawLine(
        QtCore.QPointF(size * 0.36, size * 0.46),
        QtCore.QPointF(size * 0.36, size * 0.74),
    )
    p.drawLine(
        QtCore.QPointF(size * 0.5, size * 0.46), QtCore.QPointF(size * 0.5, size * 0.74)
    )
    p.drawLine(
        QtCore.QPointF(size * 0.64, size * 0.46),
        QtCore.QPointF(size * 0.64, size * 0.74),
    )
    p.drawLine(
        QtCore.QPointF(size * 0.34, size * 0.30),
        QtCore.QPointF(size * 0.66, size * 0.30),
    )
    p.drawLine(
        QtCore.QPointF(size * 0.40, size * 0.26),
        QtCore.QPointF(size * 0.60, size * 0.26),
    )
    p.end()
    return QtGui.QIcon(pix)


def icon_mic(size=18, color="#ffffff") -> QtGui.QIcon:
    pix = QtGui.QPixmap(size, size)
    pix.fill(QtCore.Qt.GlobalColor.transparent)
    p = QtGui.QPainter(pix)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    p.setPen(QtCore.Qt.PenStyle.NoPen)
    p.setBrush(QtGui.QColor(color))
    p.drawRoundedRect(
        QtCore.QRectF(size * 0.38, size * 0.18, size * 0.24, size * 0.44), 6, 6
    )
    p.drawRect(QtCore.QRectF(size * 0.33, size * 0.40, size * 0.34, size * 0.20))
    p.drawRoundedRect(
        QtCore.QRectF(size * 0.26, size * 0.40, size * 0.48, size * 0.18), 9, 9
    )
    p.drawRect(QtCore.QRectF(size * 0.47, size * 0.62, size * 0.06, size * 0.18))
    p.drawRoundedRect(
        QtCore.QRectF(size * 0.38, size * 0.78, size * 0.24, size * 0.05), 2, 2
    )
    p.end()
    return QtGui.QIcon(pix)


def icon_app(size=64) -> QtGui.QIcon:
    """Load app icon from Icons folder."""
    icons_dir = os.path.join(APP_DIR, "Icons")
    # Try to find best matching size
    size_map = {
        16: "icon_16x16.png",
        32: "icon_32x32.png",
        64: "icon_64x64.png",
        128: "icon_128x128.png",
        256: "icon_256x256.png",
    }
    # Find closest size
    best_size = min(size_map.keys(), key=lambda x: abs(x - size))
    icon_path = os.path.join(icons_dir, size_map[best_size])
    if os.path.exists(icon_path):
        return QtGui.QIcon(icon_path)
    # Fallback to any available icon
    for fname in size_map.values():
        path = os.path.join(icons_dir, fname)
        if os.path.exists(path):
            return QtGui.QIcon(path)
    # Ultimate fallback - generated icon
    pix = QtGui.QPixmap(size, size)
    pix.fill(QtCore.Qt.GlobalColor.transparent)
    p = QtGui.QPainter(pix)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    bg = QtGui.QColor(60, 65, 80)
    p.setBrush(bg)
    p.setPen(QtCore.Qt.PenStyle.NoPen)
    p.drawRoundedRect(QtCore.QRectF(0, 0, size, size), size * 0.12, size * 0.12)
    ring = QtGui.QColor(167, 139, 250)
    p.setBrush(ring)
    cx = cy = size * 0.5
    r = size * 0.32
    p.drawEllipse(QtCore.QPointF(cx, cy), r, r)
    cut = QtGui.QColor(10, 16, 28)
    p.setBrush(cut)
    p.drawEllipse(QtCore.QPointF(cx + r * 0.35, cy), r * 0.92, r * 0.92)
    p.end()
    return QtGui.QIcon(pix)


# ===================== Waveform Widget =====================
class WaveformWidget(QtWidgets.QWidget):
    """Mini waveform/histogram visualization for audio clips."""

    def __init__(self, audio_path: str, parent=None):
        super().__init__(parent)
        self.audio_path = audio_path
        self.samples = self._load_samples()
        self.setMinimumHeight(32)
        self.setMinimumWidth(120)

    def _load_samples(self) -> list:
        """Load and downsample audio for visualization."""
        try:
            import soundfile as sf

            data, rate = sf.read(self.audio_path)
            if len(data.shape) > 1:
                data = data[:, 0]  # mono
            # Downsample to ~60 points for visualization
            num_bars = 60
            chunk_size = max(1, len(data) // num_bars)
            samples = []
            for i in range(0, len(data), chunk_size):
                chunk = data[i : i + chunk_size]
                if len(chunk) > 0:
                    # RMS of chunk
                    rms = float(np.sqrt(np.mean(np.square(chunk))))
                    samples.append(rms)
            if samples:
                max_val = max(samples) if max(samples) > 0 else 1
                samples = [s / max_val for s in samples]
            return samples[:num_bars]
        except Exception:
            pass
        try:
            import wave

            with wave.open(self.audio_path, "rb") as wf:
                frames = wf.readframes(wf.getnframes())
                data = (
                    np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
                )
                num_bars = 60
                chunk_size = max(1, len(data) // num_bars)
                samples = []
                for i in range(0, len(data), chunk_size):
                    chunk = data[i : i + chunk_size]
                    if len(chunk) > 0:
                        rms = float(np.sqrt(np.mean(np.square(chunk))))
                        samples.append(rms)
                if samples:
                    max_val = max(samples) if max(samples) > 0 else 1
                    samples = [s / max_val for s in samples]
                return samples[:num_bars]
        except Exception:
            return []

    def paintEvent(self, event):
        if not self.samples:
            return
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        bar_count = len(self.samples)
        bar_width = max(2, (w - bar_count) / bar_count)
        spacing = 1

        # Gradient colors for bars
        accent = QtGui.QColor("#6366F1")
        accent2 = QtGui.QColor("#4F46E5")
        highlight = QtGui.QColor("#818CF8")

        for i, amp in enumerate(self.samples):
            bar_height = max(2, int(amp * (h - 4)))
            x = int(i * (bar_width + spacing))
            y = (h - bar_height) // 2

            # Create gradient for each bar
            grad = QtGui.QLinearGradient(x, y, x, y + bar_height)
            grad.setColorAt(0, highlight)
            grad.setColorAt(0.5, accent)
            grad.setColorAt(1, accent2)

            painter.setBrush(grad)
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.drawRoundedRect(
                QtCore.QRectF(x, y, bar_width, bar_height), bar_width / 2, bar_width / 2
            )

        painter.end()


# ===================== translations =====================
T = {
    "en": {
        "title": "Lino-ST",
        "tab_home": "Home",
        "tab_hist": "History",
        "tab_about": "About",
        "tab_settings": "Settings",
        "start": "Start",
        "stop": "Stop",
        "date": "Date",
        "time": "Time",
        "length": "Length",
        "playstop": "Play/Stop",
        "delete": "Delete",
        "sensitivity": "Microphone Sensitivity",
        "maxlen": "Max clip length",
        "language": "Language",
        "help": "Help",
        "about": "About",
        "license": "License",
        "day": "Day",
        "sleep_duration": "Sleep Duration",
        "days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "date_format": "Date Format",
        "date_format_eu": "EU (DD.MM.YYYY)",
        "date_format_us": "US (MM/DD/YYYY)",
        "time_format": "Time Format",
        "time_format_24": "24h (14:30)",
        "time_format_12": "12h (2:30 PM)",
        "audio_format": "Audio Format",
        "audio_ogg": "OGG Vorbis (smaller files, recommended)",
        "audio_wav": "WAV (uncompressed, larger files)",
        "help_text": "LINO-ST - SLEEP TRACKER\n\nHOW TO USE:\n\n1) Start = arm mic. Speak/clap to test.\n\n2) Auto-record saves clips only while level is above sensitivity.\n\n3) Sliders:\n   • Microphone Sensitivity: right = more sensitive, left = less.\n   • Max clip length: hard stop clip at this time (0 = unlimited).\n\n4) List below: Play/Stop to preview, Delete to remove.\n\n5) History shows past sleep sessions.\n\n6) Settings: Configure audio format (OGG/WAV), date/time format.\n\n\nHISTORY:\n- Day: day name.\n- Date: recording date.\n- Start/End: session times.\n- Sleep Duration: total hours/minutes (HH:MM).",
        "about_text": "<b>Lino-ST — Your Desktop Sleep Tracker</b><br><br>Version {version}<br>Created by Nele<br>License: MIT<br><br><b>Features</b><br>• Start/Stop microphone monitoring<br>• Auto-record when sound detected<br>• Live microphone meter<br>• Per-clip list with Play/Stop and Delete<br>• Language switcher (EN/HR/DE)<br>• Sleep session history<br>• Export recordings to ZIP<br>• Audio format selection (OGG/WAV)<br>• Modern dark UI with glossy effects<br>• EU/US date format support",
    },
    "hr": {
        "title": "Lino-ST",
        "tab_home": "Home",
        "tab_hist": "Povijest",
        "tab_about": "O aplikaciji",
        "tab_settings": "Postavke",
        "start": "Start",
        "stop": "Stop",
        "date": "Datum",
        "time": "Vrijeme",
        "length": "Dužina",
        "playstop": "Play/Stop",
        "delete": "Obriši",
        "sensitivity": "Osjetljivost mikrofona",
        "maxlen": "Maksimalna dužina klipa",
        "language": "Jezik",
        "help": "Pomoć",
        "about": "O aplikaciji",
        "license": "Licenca",
        "day": "Dan",
        "sleep_duration": "Trajanje sna",
        "days": ["Pon", "Uto", "Sri", "Čet", "Pet", "Sub", "Ned"],
        "date_format": "Format datuma",
        "date_format_eu": "EU (DD.MM.YYYY)",
        "date_format_us": "US (MM/DD/YYYY)",
        "time_format": "Format vremena",
        "time_format_24": "24h (14:30)",
        "time_format_12": "12h (2:30 PM)",
        "audio_format": "Audio format",
        "audio_ogg": "OGG Vorbis (manje datoteke, preporučeno)",
        "audio_wav": "WAV (nekomprimirano, veće datoteke)",
        "help_text": "LINO-ST - PRAĆENJE SPAVANJA\n\nKAKO KORISTITI:\n\n1) Start = aktiviraj mikrofon. Govori/pljeskaj za test.\n\n2) Automatski snima samo dok je razina iznad osjetljivosti.\n\n3) Klizači:\n   • Osjetljivost mikrofona: desno = osjetljivije, lijevo = manje.\n   • Maks. dužina klipa: automatski prekini nakon ovog vremena (0 = neograničeno).\n\n4) Lista ispod: Play/Stop za pregled, Obriši za brisanje.\n\n5) Povijest prikazuje prošle sesije spavanja.\n\n6) Postavke: Konfiguriraj audio format (OGG/WAV), format datuma/vremena.\n\n\nPOVIJEST:\n- Dan: naziv dana.\n- Datum: datum snimanja.\n- Početak/Kraj: vrijeme sesije.\n- Trajanje sna: ukupno sati/minuta (HH:MM).",
        "about_text": "<b>Lino-ST — Your Desktop Sleep Tracker</b><br><br>Verzija {version}<br>Autor: Nele<br>Licenca: MIT<br><br><b>Značajke</b><br>• Start/Stop praćenja mikrofona<br>• Automatsko snimanje kad se detektira zvuk<br>• Prikaz razine mikrofona uživo<br>• Lista snimki s Play/Stop i Obriši<br>• Odabir jezika (EN/HR/DE)<br>• Povijest sesija spavanja<br>• Export snimaka u ZIP<br>• Odabir audio formata (OGG/WAV)<br>• Moderni tamni UI sa glossy efektima<br>• EU/US format datuma",
    },
    "de": {
        "title": "Lino-ST",
        "tab_home": "Home",
        "tab_hist": "Verlauf",
        "tab_about": "Über",
        "tab_settings": "Einstellungen",
        "start": "Start",
        "stop": "Stop",
        "date": "Datum",
        "time": "Zeit",
        "length": "Länge",
        "playstop": "Play/Stop",
        "delete": "Löschen",
        "sensitivity": "Mikrofon-Empfindlichkeit",
        "maxlen": "Maximale Clip-Länge",
        "language": "Sprache",
        "help": "Hilfe",
        "about": "Über",
        "license": "Lizenz",
        "day": "Tag",
        "sleep_duration": "Schlafdauer",
        "days": ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"],
        "date_format": "Datumsformat",
        "date_format_eu": "EU (TT.MM.JJJJ)",
        "date_format_us": "US (MM/TT/JJJJ)",
        "time_format": "Zeitformat",
        "time_format_24": "24h (14:30)",
        "time_format_12": "12h (2:30 PM)",
        "audio_format": "Audio-Format",
        "audio_ogg": "OGG Vorbis (kleinere Dateien, empfohlen)",
        "audio_wav": "WAV (unkomprimiert, größere Dateien)",
        "help_text": "LINO-ST - SCHLAF-TRACKER\n\nANLEITUNG:\n\n1) Start = Mikrofon aktivieren. Sprechen/Klatschen zum Testen.\n\n2) Automatische Aufnahme nur wenn Pegel über Empfindlichkeit.\n\n3) Regler:\n   • Mikrofon-Empfindlichkeit: rechts = empfindlicher, links = weniger.\n   • Max. Clip-Länge: Aufnahme nach dieser Zeit stoppen (0 = unbegrenzt).\n\n4) Liste unten: Play/Stop zur Vorschau, Löschen zum Entfernen.\n\n5) Verlauf zeigt vergangene Schlafsitzungen.\n\n6) Einstellungen: Audio-Format (OGG/WAV), Datum/Zeit-Format konfigurieren.\n\n\nVERLAUF:\n- Tag: Wochentag.\n- Datum: Aufnahmedatum.\n- Start/Ende: Sitzungszeiten.\n- Schlafdauer: Gesamtstunden/Minuten (HH:MM).",
        "about_text": "<b>Lino-ST — Your Desktop Sleep Tracker</b><br><br>Version {version}<br>Erstellt von Nele<br>Lizenz: MIT<br><br><b>Funktionen</b><br>• Start/Stop Mikrofonüberwachung<br>• Automatische Aufnahme bei Geräusch<br>• Live-Mikrofonpegel<br>• Clip-Liste mit Play/Stop und Löschen<br>• Sprachwechsel (EN/HR/DE)<br>• Schlaf-Sitzungsverlauf<br>• Export der Aufnahmen als ZIP<br>• Audio-Format-Auswahl (OGG/WAV)<br>• Moderne dunkle UI mit Glanz-Effekten<br>• EU/US Datumsformat",
    },
}


# ===================== main window =====================


class SleepTracker(QtWidgets.QWidget):
    RATE = 44100
    CH = 1
    EPS = 1e-8
    ARM_MS = 120
    HANG_MS = 400
    PREROLL_MS = 250
    BLOCK = 1024
    EMA_ALPHA = 0.4

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("root")
        self.lang = "en"
        self.date_format = "eu"  # "eu" = DD.MM.YYYY, "us" = MM/DD/YYYY
        self.time_format = "24"  # "24" = 24h, "12" = 12h AM/PM
        self.audio_format = (
            "ogg"  # "ogg" = OGG Vorbis (smaller), "wav" = WAV (uncompressed)
        )
        self.theme_palette: typing.Optional[dict] = None

        # audio state
        self.stream: typing.Optional[sd.InputStream] = None
        self.q: "queue.Queue[np.ndarray]" = queue.Queue()
        self.monitoring: bool = False
        self.threshold_db: int = -45  # Will be set by slider
        self._sens_pct: int = 62  # ~62% = -45dB (default)
        self.max_len_s: int = 30  # seconds (0 = unlimited)
        self.capture_samples: int = 0
        self.smooth_db: float = -90.0

        # segmentation
        self.capturing: bool = False
        self.capture_frames: list[np.ndarray] = []
        self.above_ms: float = 0.0
        self.below_ms: float = 0.0
        self.preroll = collections.deque(
            maxlen=int(self.PREROLL_MS / 1000 * self.RATE / self.BLOCK + 4)
        )

        # storage
        self.out_dir = os.path.join(APP_DIR, "recordings")
        os.makedirs(self.out_dir, exist_ok=True)
        cfg_dir = os.path.join(os.path.expanduser("~"), ".config", "Lino-ST")
        os.makedirs(cfg_dir, exist_ok=True)
        self.sessions_file = os.path.join(cfg_dir, "sessions.json")
        legacy = os.path.join(APP_DIR, "sessions.json")
        try:
            if os.path.exists(legacy) and not os.path.exists(self.sessions_file):
                import shutil as _sh

                _sh.copy2(legacy, self.sessions_file)
        except Exception:
            pass
        self.sessions = self._load_sessions()
        self.session_start: typing.Optional[QtCore.QDateTime] = None

        # playback state
        self.current_play: typing.Optional[tuple] = None  # (weakref(btn), path)
        self.player = QMediaPlayer(self)
        self.audio_out = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_out)
        self.audio_out.setVolume(1.0)
        self.player.playbackStateChanged.connect(self._on_player_state)

        # ui
        self._build_ui()
        self.setWindowIcon(icon_app(64))

        self.apply_theme()
        self._load_existing_recordings()
        self._wire_timers()

        # System tray icon
        self.tray = QtWidgets.QSystemTrayIcon(icon_app(32), self)
        menu = QtWidgets.QMenu()
        actShow = menu.addAction("Show App")
        actExit = menu.addAction("Exit")
        actShow.triggered.connect(self._tray_show)
        actExit.triggered.connect(self._tray_exit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self._tray_show()
            if reason
            in (
                QtWidgets.QSystemTrayIcon.ActivationReason.Trigger,
                QtWidgets.QSystemTrayIcon.ActivationReason.DoubleClick,
            )
            else None
        )
        self.tray.setToolTip("Lino-ST — Your Desktop Sleep Tracker")
        self.tray.show()

    # ---- UI ----
    def _build_ui(self) -> None:
        self.setWindowTitle(T[self.lang]["title"])
        self.resize(800, 800)
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(10)

        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel(T[self.lang]["title"])
        title.setStyleSheet("font-size:20px; font-weight:600;")
        header.addWidget(title)
        header.addStretch(1)
        outer.addLayout(header)

        self.tabs = QtWidgets.QTabWidget()
        outer.addWidget(self.tabs)

        # -- Home tab --
        home = QtWidgets.QWidget()
        g = QtWidgets.QGridLayout(home)
        g.setContentsMargins(0, 0, 0, 0)
        g.setVerticalSpacing(10)

        self.card = QtWidgets.QFrame()
        self.card.setObjectName("card")
        self.card.setProperty("class", "card")
        cg = QtWidgets.QGridLayout(self.card)
        cg.setContentsMargins(16, 16, 16, 16)
        cg.setVerticalSpacing(10)

        self.btnStart = QtWidgets.QPushButton(T[self.lang]["start"])
        self.btnStart.setProperty("variant", "pill")
        self.btnStart.setIcon(icon_play(22))
        self.btnStart.setIconSize(QtCore.QSize(22, 22))
        self.btnStart.clicked.connect(self._toggle_monitor)
        cg.addWidget(self.btnStart, 0, 0, 1, 2)

        micRow = QtWidgets.QHBoxLayout()
        micIcon = QtWidgets.QLabel()
        micIcon.setPixmap(icon_mic(18).pixmap(18, 18))
        micRow.addWidget(micIcon)
        self.levelBar = QtWidgets.QProgressBar()
        self.levelBar.setFormat("%p%")
        self.lblDb = QtWidgets.QLabel("-inf dB")
        self.lblDb.setProperty("class", "badge")
        micRow.addWidget(self.levelBar, 1)
        micRow.addWidget(self.lblDb)
        cg.addLayout(micRow, 1, 0, 1, 2)

        settingsBox = QtWidgets.QFrame()
        settingsBox.setObjectName("card")
        settingsBox.setProperty("class", "card")
        s = QtWidgets.QGridLayout(settingsBox)
        s.setContentsMargins(12, 12, 12, 12)
        s.setVerticalSpacing(16)

        # Sensitivity: 0-100%, maps to threshold -20dB (0%) to -60dB (100%)
        self._sens_pct = self._threshold_to_pct(self.threshold_db)
        self.lblSens = QtWidgets.QLabel(
            f"{T[self.lang]['sensitivity']} ({self._sens_pct}%)"
        )
        self.sens = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.sens.setRange(0, 100)
        self.sens.setValue(self._sens_pct)
        self.sens.setToolTip("Left = less sensitive; Right = more sensitive")
        self.sens.valueChanged.connect(self._sens_changed)
        s.addWidget(self.lblSens, 0, 0)
        s.addWidget(self.sens, 0, 1)

        self.lblMax = QtWidgets.QLabel(f"{T[self.lang]['maxlen']} ({self.max_len_s} s)")
        self.maxlen = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.maxlen.setRange(0, 60)
        self.maxlen.setValue(self.max_len_s)
        self.maxlen.setToolTip("0 = unlimited")
        self.maxlen.valueChanged.connect(self._maxlen_changed)
        s.addWidget(self.lblMax, 1, 0)
        s.addWidget(self.maxlen, 1, 1)

        cg.addWidget(settingsBox, 2, 0, 1, 2)

        # recordings table in card
        self.recCard = QtWidgets.QFrame()
        self.recCard.setObjectName("tableCard")
        rv = QtWidgets.QVBoxLayout(self.recCard)
        rv.setContentsMargins(8, 8, 8, 8)
        rv.setSpacing(6)
        # Columns: Date | Time | Length | Play | Waveform | Delete
        self.table = QtWidgets.QTableWidget(0, 6)
        self.table.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.table.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.table.setVerticalScrollMode(
            QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self.table.setHorizontalScrollMode(
            QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(True)
        self.table.setHorizontalHeaderLabels(
            [
                T[self.lang]["date"],
                T[self.lang]["time"],
                T[self.lang]["length"],
                T[self.lang]["playstop"],
                "Waveform",
                T[self.lang]["delete"],
            ]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            4, QtWidgets.QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            5, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(48)
        self.table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        rv.addWidget(self.table)

        cg.addWidget(self.recCard, 3, 0, 1, 2)

        g.addWidget(self.card, 0, 0, 1, 1)
        g.addWidget(self.recCard, 1, 0, 1, 1)
        self.tabs.addTab(home, T[self.lang]["tab_home"])

        # -- History tab --
        hist = QtWidgets.QWidget()
        hv = QtWidgets.QVBoxLayout(hist)
        hv.setSpacing(10)
        self.histCard = QtWidgets.QFrame()
        self.histCard.setObjectName("tableCard")
        hv2 = QtWidgets.QVBoxLayout(self.histCard)
        hv2.setContentsMargins(8, 8, 8, 8)
        hv2.setSpacing(6)
        self.sessionTable = QtWidgets.QTableWidget(0, 5)
        self.sessionTable.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.sessionTable.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.sessionTable.setVerticalScrollMode(
            QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self.sessionTable.setHorizontalScrollMode(
            QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self.sessionTable.setAlternatingRowColors(True)
        self.sessionTable.setShowGrid(True)
        self.sessionTable.setHorizontalHeaderLabels(
            [
                T[self.lang]["day"],
                T[self.lang]["date"],
                "Start",
                "End",
                T[self.lang]["sleep_duration"],
            ]
        )
        self.sessionTable.horizontalHeader().setStretchLastSection(True)
        self.sessionTable.verticalHeader().setVisible(False)
        self.sessionTable.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.sessionTable.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        hv2.addWidget(self.sessionTable)
        hv.addWidget(self.histCard)
        self.tabs.addTab(hist, T[self.lang]["tab_hist"])

        # -- Settings tab --
        settings = QtWidgets.QWidget()
        sv = QtWidgets.QVBoxLayout(settings)
        sv.setSpacing(10)
        settingsCard = QtWidgets.QFrame()
        settingsCard.setObjectName("card")
        settingsCard.setProperty("class", "card")
        sc = QtWidgets.QVBoxLayout(settingsCard)
        sc.setContentsMargins(16, 16, 16, 16)
        sc.setSpacing(16)

        # Language setting
        langRow = QtWidgets.QHBoxLayout()
        self.lblLang = QtWidgets.QLabel(T[self.lang]["language"] + ":")
        self.langCombo = QtWidgets.QComboBox()
        self.langCombo.addItems(["English", "Hrvatski", "Deutsch"])
        self.langCombo.currentIndexChanged.connect(self._lang_changed)
        langRow.addWidget(self.lblLang)
        langRow.addWidget(self.langCombo)
        langRow.addStretch(1)
        sc.addLayout(langRow)

        # Date format setting
        dateRow = QtWidgets.QHBoxLayout()
        self.lblDateFmt = QtWidgets.QLabel(T[self.lang]["date_format"] + ":")
        self.dateFormatCombo = QtWidgets.QComboBox()
        self.dateFormatCombo.addItems(
            [T[self.lang]["date_format_eu"], T[self.lang]["date_format_us"]]
        )
        self.dateFormatCombo.currentIndexChanged.connect(self._date_format_changed)
        dateRow.addWidget(self.lblDateFmt)
        dateRow.addWidget(self.dateFormatCombo)
        dateRow.addStretch(1)
        sc.addLayout(dateRow)

        # Time format setting
        timeRow = QtWidgets.QHBoxLayout()
        self.lblTimeFmt = QtWidgets.QLabel(T[self.lang]["time_format"] + ":")
        self.timeFormatCombo = QtWidgets.QComboBox()
        self.timeFormatCombo.addItems(
            [T[self.lang]["time_format_24"], T[self.lang]["time_format_12"]]
        )
        self.timeFormatCombo.currentIndexChanged.connect(self._time_format_changed)
        timeRow.addWidget(self.lblTimeFmt)
        timeRow.addWidget(self.timeFormatCombo)
        timeRow.addStretch(1)
        sc.addLayout(timeRow)

        # Audio format setting
        audioRow = QtWidgets.QHBoxLayout()
        self.lblAudioFmt = QtWidgets.QLabel(T[self.lang]["audio_format"] + ":")
        self.audioFormatCombo = QtWidgets.QComboBox()
        self.audioFormatCombo.addItems(
            [T[self.lang]["audio_ogg"], T[self.lang]["audio_wav"]]
        )
        # Set current selection based on self.audio_format
        self.audioFormatCombo.setCurrentIndex(0 if self.audio_format == "ogg" else 1)
        self.audioFormatCombo.currentIndexChanged.connect(self._audio_format_changed)
        audioRow.addWidget(self.lblAudioFmt)
        audioRow.addWidget(self.audioFormatCombo)
        audioRow.addStretch(1)
        sc.addLayout(audioRow)

        # Action buttons row (Delete All, Export ZIP)
        btnRow = QtWidgets.QHBoxLayout()
        btnRow.addStretch(1)
        self.btnDeleteAll = QtWidgets.QPushButton("Delete All")
        self.btnDeleteAll.setProperty("variant", "ghost")
        self.btnDeleteAll.setIcon(icon_trash(16))
        self.btnDeleteAll.clicked.connect(self._delete_all_recordings)
        btnRow.addWidget(self.btnDeleteAll)
        self.btnExportZip = QtWidgets.QPushButton("Export ZIP")
        self.btnExportZip.setProperty("variant", "ghost")
        self.btnExportZip.clicked.connect(self._export_recordings_zip)
        btnRow.addWidget(self.btnExportZip)
        sc.addLayout(btnRow)

        sc.addStretch(1)
        sv.addWidget(settingsCard)
        sv.addStretch(1)
        self.tabs.addTab(settings, T[self.lang]["tab_settings"])

        # -- About tab --
        about = QtWidgets.QWidget()
        av = QtWidgets.QVBoxLayout(about)
        av.setSpacing(10)
        aboutCard = QtWidgets.QFrame()
        aboutCard.setObjectName("card")
        aboutCard.setProperty("class", "card")
        ac = QtWidgets.QVBoxLayout(aboutCard)
        ac.setContentsMargins(16, 16, 16, 16)
        self.aboutLabel = QtWidgets.QLabel(
            T[self.lang]["about_text"].format(version=VERSION)
        )
        self.aboutLabel.setWordWrap(True)
        self.aboutLabel.setTextFormat(QtCore.Qt.TextFormat.RichText)

        # Add image to the right of text
        aboutContent = QtWidgets.QHBoxLayout()
        aboutContent.addWidget(self.aboutLabel, 1)  # Text takes 1/3 space

        # Add image
        imageLabel = QtWidgets.QLabel()
        image_path = os.path.join(APP_DIR, "image.png")
        if os.path.exists(image_path):
            # Load original image with transparency
            pixmap = QtGui.QPixmap(image_path)

            # Scale to larger size (zoom in) - crop 20px from edges
            # Calculate crop area (20px margin from each side)
            original_size = pixmap.size()
            crop_rect = QtCore.QRect(
                20, 20, original_size.width() - 40, original_size.height() - 40
            )

            # Crop: image to remove 20px border
            if crop_rect.isValid() and crop_rect.width() > 0 and crop_rect.height() > 0:
                cropped_pixmap = pixmap.copy(crop_rect)
            else:
                cropped_pixmap = pixmap

            # Scale the cropped image to larger size for zoom effect
            # Use even larger dimensions for better visibility
            scaled_pixmap = cropped_pixmap.scaled(
                450,
                350,  # Even larger size for better zoom effect
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )

            # Crop the image to remove 20px border
            if crop_rect.isValid() and crop_rect.width() > 0 and crop_rect.height() > 0:
                cropped_pixmap = pixmap.copy(crop_rect)
            else:
                cropped_pixmap = pixmap

            # Scale the cropped image to larger size for zoom effect
            # Use larger dimensions for better visibility
            scaled_pixmap = cropped_pixmap.scaled(
                400,
                320,  # Much larger size for zoom effect
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )

            imageLabel.setPixmap(scaled_pixmap)
            imageLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

            # Apply style to ensure transparent background and no borders
            imageLabel.setStyleSheet("""
                QLabel {
                    background: transparent;
                    border: none;
                    padding: 10px;
                    margin: 0px;
                }
            """)

            # Ensure: label doesn't add any background
            imageLabel.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
            imageLabel.setAttribute(QtCore.Qt.WidgetAttribute.WA_NoSystemBackground)
        aboutContent.addWidget(imageLabel, 0)  # Image takes remaining space
        ac.addLayout(aboutContent)
        ac.addSpacing(16)
        # Help and License buttons
        aboutBtnRow = QtWidgets.QHBoxLayout()
        self.btnHelp = QtWidgets.QPushButton(T[self.lang]["help"])
        self.btnHelp.setProperty("variant", "ghost")
        self.btnHelp.clicked.connect(self._show_help_dialog)
        aboutBtnRow.addWidget(self.btnHelp)
        self.btnLicense = QtWidgets.QPushButton(T[self.lang]["license"])
        self.btnLicense.setProperty("variant", "ghost")
        self.btnLicense.clicked.connect(self._show_license_dialog)
        aboutBtnRow.addWidget(self.btnLicense)
        aboutBtnRow.addStretch(1)
        ac.addLayout(aboutBtnRow)
        ac.addStretch(1)
        av.addWidget(aboutCard)
        av.addStretch(1)
        self.tabs.addTab(about, T[self.lang]["tab_about"])

        self._apply_header_styles()
        self._refresh_history()

    # ---- i18n/theme ----

    def _lang_changed(self, idx: int) -> None:
        self.lang = ["en", "hr", "de"][idx]
        self.setWindowTitle(T[self.lang]["title"])
        self.tabs.setTabText(0, T[self.lang]["tab_home"])
        self.tabs.setTabText(1, T[self.lang]["tab_hist"])
        self.tabs.setTabText(2, T[self.lang]["tab_settings"])
        self.tabs.setTabText(3, T[self.lang]["tab_about"])
        self.btnStart.setText(
            T[self.lang]["stop"] if self.monitoring else T[self.lang]["start"]
        )
        self.lblSens.setText(f"{T[self.lang]['sensitivity']} ({self._sens_pct}%)")
        self.lblMax.setText(
            f"{T[self.lang]['maxlen']} ({self.max_len_s if self.max_len_s > 0 else '∞'} s)"
        )
        self.lblLang.setText(T[self.lang]["language"] + ":")
        self.lblDateFmt.setText(T[self.lang]["date_format"] + ":")
        self.lblTimeFmt.setText(T[self.lang]["time_format"] + ":")
        # Update date format combo items
        self.dateFormatCombo.blockSignals(True)
        cur_date_idx = self.dateFormatCombo.currentIndex()
        self.dateFormatCombo.clear()
        self.dateFormatCombo.addItems(
            [T[self.lang]["date_format_eu"], T[self.lang]["date_format_us"]]
        )
        self.dateFormatCombo.setCurrentIndex(cur_date_idx)
        self.dateFormatCombo.blockSignals(False)
        # Update time format combo items
        self.timeFormatCombo.blockSignals(True)
        cur_time_idx = self.timeFormatCombo.currentIndex()
        self.timeFormatCombo.clear()
        self.timeFormatCombo.addItems(
            [T[self.lang]["time_format_24"], T[self.lang]["time_format_12"]]
        )
        self.timeFormatCombo.setCurrentIndex(cur_time_idx)
        self.timeFormatCombo.blockSignals(False)
        # Update audio format combo items
        self.audioFormatCombo.blockSignals(True)
        cur_audio_idx = self.audioFormatCombo.currentIndex()
        self.audioFormatCombo.clear()
        self.audioFormatCombo.addItems(
            [T[self.lang]["audio_ogg"], T[self.lang]["audio_wav"]]
        )
        self.audioFormatCombo.setCurrentIndex(cur_audio_idx)
        self.audioFormatCombo.blockSignals(False)
        # Update about text
        self.aboutLabel.setText(T[self.lang]["about_text"].format(version=VERSION))
        # Update table headers
        self.table.setHorizontalHeaderLabels(
            [
                T[self.lang]["date"],
                T[self.lang]["time"],
                T[self.lang]["length"],
                T[self.lang]["playstop"],
                "Waveform",
                T[self.lang]["delete"],
            ]
        )
        self.sessionTable.setHorizontalHeaderLabels(
            [
                T[self.lang]["day"],
                T[self.lang]["date"],
                "Start",
                "End",
                T[self.lang]["sleep_duration"],
            ]
        )
        self._apply_header_styles()
        self._refresh_history()
        self._refresh_recordings_table()

    def apply_theme(self) -> None:
        self.theme_palette = THEME_PALETTE
        QtWidgets.QApplication.setStyle("Fusion")
        app = QtWidgets.QApplication.instance()
        if app:
            app.setStyleSheet(qss_for(self.theme_palette))
        self._refresh_icons()
        self._apply_header_styles()

    def _refresh_icons(self) -> None:
        col = self.theme_palette["fg"] if self.theme_palette else "#fff"
        self.btnStart.setIcon(
            icon_stop(22, col) if self.monitoring else icon_play(22, col)
        )

    def _apply_header_styles(self) -> None:
        if not self.theme_palette:
            return
        pal = self.theme_palette
        header_style = (
            f"QHeaderView::section {{"
            f"background: rgba(255,255,255,0.08);"
            f"color: {pal['fg']};"
            f"border: 0;"
            f"border-bottom: 1px solid {pal['border']};"
            f"padding: 8px 10px; }}"
        )
        for t in (self.table, self.sessionTable):
            try:
                t.horizontalHeader().setStyleSheet(header_style)
            except Exception:
                pass

    def _on_player_state(self, state) -> None:
        try:
            if state == QMediaPlayer.PlaybackState.StoppedState and self.current_play:
                btn_ref, _path = self.current_play
                btn = btn_ref() if callable(btn_ref) else None
                if btn:
                    btn.setIcon(
                        icon_play(
                            18,
                            self.theme_palette["fg"] if self.theme_palette else "#fff",
                        )
                    )
                    setattr(btn, "_is_playing", False)
                self.current_play = None
        except Exception:
            pass

    # ---- settings ----
    def _pct_to_threshold(self, pct: int) -> int:
        """Convert sensitivity percentage (0-100) to dB threshold (-20 to -60)."""
        # 0% -> -20dB (least sensitive), 100% -> -60dB (most sensitive)
        return -20 - int(pct * 0.4)

    def _threshold_to_pct(self, db: int) -> int:
        """Convert dB threshold (-20 to -60) to sensitivity percentage (0-100)."""
        # -20dB -> 0%, -60dB -> 100%
        return int((-20 - db) / 0.4)

    def _sens_changed(self, v: int) -> None:
        self._sens_pct = v
        self.threshold_db = self._pct_to_threshold(v)
        self.lblSens.setText(f"{T[self.lang]['sensitivity']} ({v}%)")

    def _maxlen_changed(self, v: int) -> None:
        self.max_len_s = v
        if v <= 0:
            self.lblMax.setText(f"{T[self.lang]['maxlen']} (∞)")
        else:
            self.lblMax.setText(f"{T[self.lang]['maxlen']} ({v} s)")

    def _date_format_changed(self, idx: int) -> None:
        self.date_format = ["eu", "us"][idx]
        self._refresh_history()
        self._refresh_recordings_table()

    def _time_format_changed(self, idx: int) -> None:
        self.time_format = ["24", "12"][idx]
        self._refresh_history()
        self._refresh_recordings_table()

    def _audio_format_changed(self, idx: int) -> None:
        self.audio_format = ["ogg", "wav"][idx]

    def _format_date(self, dt: datetime.datetime) -> str:
        """Format date according to user preference."""
        if self.date_format == "us":
            return dt.strftime("%m/%d/%Y")
        else:
            return dt.strftime("%d.%m.%Y")

    def _format_time(self, dt: datetime.datetime) -> str:
        """Format time according to user preference."""
        if self.time_format == "12":
            return dt.strftime("%I:%M %p")
        else:
            return dt.strftime("%H:%M")

    def _format_datetime(self, dt: datetime.datetime) -> tuple:
        """Format datetime into (date_str, time_str) according to user preferences."""
        return (self._format_date(dt), self._format_time(dt))

    def _load_license_text(self) -> str:
        """Return hardcoded license text."""
        return """MIT License

Copyright (c) 2024-2025 Nele

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE."""

    def _show_help_dialog(self) -> None:
        """Show help dialog with usage instructions."""
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(T[self.lang]["help"])
        dialog.setMinimumSize(500, 400)
        layout = QtWidgets.QVBoxLayout(dialog)

        text = QtWidgets.QTextEdit()
        text.setPlainText(T[self.lang]["help_text"])
        text.setReadOnly(True)
        layout.addWidget(text)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Close
        )
        buttons.rejected.connect(dialog.close)
        layout.addWidget(buttons)

        dialog.exec()

    def _show_license_dialog(self) -> None:
        """Show license dialog."""
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(T[self.lang]["license"])
        dialog.setMinimumSize(500, 400)
        layout = QtWidgets.QVBoxLayout(dialog)

        text = QtWidgets.QTextEdit()
        text.setPlainText(self._load_license_text())
        text.setReadOnly(True)
        layout.addWidget(text)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Close
        )
        buttons.rejected.connect(dialog.close)
        layout.addWidget(buttons)

        dialog.exec()

    # ---- timers & audio ----
    def _wire_timers(self) -> None:
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self._drain_audio)
        self.timer.start()

    def _toggle_monitor(self) -> None:
        if not self.monitoring:
            try:
                self.stream = sd.InputStream(
                    samplerate=self.RATE,
                    channels=self.CH,
                    callback=self._cb,
                    blocksize=self.BLOCK,
                )
                self.stream.start()
                self.monitoring = True
                self.session_start = QtCore.QDateTime.currentDateTime()
                self.btnStart.setText(T[self.lang]["stop"])
                self._refresh_icons()
                self.above_ms = self.below_ms = 0.0
                self.capturing = False
                self.capture_frames.clear()
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Audio error", str(e))
        else:
            if self.stream:
                self.stream.stop()
                self.stream.close()
                self.stream = None
            self.monitoring = False
            self._finalize_clip(force=True)
            self.btnStart.setText(T[self.lang]["start"])
            self._refresh_icons()
            if self.session_start:
                end = QtCore.QDateTime.currentDateTime()
                dur = int(self.session_start.msecsTo(end) / 1000)
                self._save_session(self.session_start, end, dur)
                self.session_start = None
                self._refresh_history()

    def _cb(self, indata, frames, time, status) -> None:
        if status:
            pass
        self.q.put(indata.copy())

    def _drain_audio(self) -> None:
        while not self.q.empty():
            block = self.q.get()
            block_ms = len(block) / self.RATE * 1000.0
            rms = float(np.sqrt(np.mean(np.square(block)) + self.EPS))
            inst_db = 20.0 * np.log10(rms + self.EPS)
            self.smooth_db = (
                self.EMA_ALPHA * inst_db + (1.0 - self.EMA_ALPHA) * self.smooth_db
            )
            self.lblDb.setText(f"{inst_db:0.1f} dB")
            self.levelBar.setValue(
                max(0, min(100, int((inst_db + 60) * (100.0 / 60.0))))
            )

            if not self.monitoring:
                continue

            start_th = self.threshold_db
            stop_th = self.threshold_db - 6.0  # hystereza
            above = self.smooth_db >= start_th
            self.preroll.append(block)

            if above:
                self.above_ms += block_ms
                self.below_ms = 0.0
            else:
                self.below_ms += block_ms
                self.above_ms = 0.0

            if not self.capturing and self.above_ms >= self.ARM_MS:
                self._start_capture()

            if self.capturing:
                self.capture_frames.append(block)
                try:
                    self.capture_samples += block.shape[0]
                except Exception:
                    pass
                hit_hysteresis = (
                    self.smooth_db < stop_th and self.below_ms >= self.HANG_MS
                )
                hit_max = (
                    self.max_len_s > 0
                    and (self.capture_samples / self.RATE) >= self.max_len_s
                )
                if hit_hysteresis or hit_max:
                    self._finalize_clip()

    def _start_capture(self) -> None:
        self.capturing = True
        self.capture_frames = list(self.preroll)
        try:
            self.capture_samples = sum(b.shape[0] for b in self.capture_frames)
        except Exception:
            self.capture_samples = 0
        self.preroll.clear()

    def _finalize_clip(self, force: bool = False) -> None:
        if not self.capturing and not force:
            return
        frames = self.capture_frames if self.capturing else []
        self.capturing = False
        self.capture_frames = []
        self.above_ms = self.below_ms = 0.0
        if not frames:
            return
        data = np.concatenate(frames, axis=0)
        dur = data.shape[0] / self.RATE
        # Use user-selected audio format
        if self.audio_format == "ogg":
            try:
                import soundfile as sf

                fname = datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".ogg"
                path = os.path.join(self.out_dir, fname)
                sf.write(
                    path,
                    data.astype("float32"),
                    self.RATE,
                    format="OGG",
                    subtype="VORBIS",
                )
            except Exception:
                # Fallback to WAV if soundfile fails
                import wave as _w

                data16 = np.clip(data, -1.0, 1.0)
                data16 = (data16 * 32767.0).astype(np.int16)
                fname = datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".wav"
                path = os.path.join(self.out_dir, fname)
                with _w.open(path, "wb") as wf:
                    wf.setnchannels(self.CH)
                    wf.setsampwidth(2)
                    wf.setframerate(self.RATE)
                    wf.writeframes(data16.tobytes())
        else:  # wav format
            import wave as _w

            data16 = np.clip(data, -1.0, 1.0)
            data16 = (data16 * 32767.0).astype(np.int16)
            fname = datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".wav"
            path = os.path.join(self.out_dir, fname)
            with _w.open(path, "wb") as wf:
                wf.setnchannels(self.CH)
                wf.setsampwidth(2)
                wf.setframerate(self.RATE)
                wf.writeframes(data16.tobytes())
        self._add_row(path, dur)
        self.capture_samples = 0

    # ---- playback helpers ----
    def _stop_current(self) -> None:
        if not self.current_play:
            try:
                self.player.stop()
            except Exception:
                pass
            return
        try:
            btn_ref, _path = self.current_play
        except Exception:
            self.current_play = None
            try:
                self.player.stop()
            except Exception:
                pass
            return
        try:
            self.player.stop()
        except Exception:
            pass
        btn = btn_ref() if callable(btn_ref) else None
        if btn:
            try:
                btn.setIcon(
                    icon_play(
                        18, self.theme_palette["fg"] if self.theme_palette else "#fff"
                    )
                )
                setattr(btn, "_is_playing", False)
            except Exception:
                pass
        self.current_play = None

    # ---- recordings table ops ----
    def _load_existing_recordings(self) -> None:
        """Load existing recordings from the recordings directory on startup."""
        if not os.path.isdir(self.out_dir):
            return
        # Store recording data for refresh
        if not hasattr(self, "_recordings_data"):
            self._recordings_data = []
        files = []
        for fname in os.listdir(self.out_dir):
            if fname.lower().endswith((".wav", ".ogg", ".mp3", ".flac")):
                fpath = os.path.join(self.out_dir, fname)
                files.append((fname, fpath))
        # Sort by filename (which contains timestamp)
        files.sort(key=lambda x: x[0])
        for fname, fpath in files:
            # Get file duration
            dur = self._get_audio_duration(fpath)
            # Parse timestamp from filename (format: YYYYMMDD_HHMMSS)
            try:
                base = os.path.splitext(fname)[0]
                dt = datetime.datetime.strptime(base, "%Y%m%d_%H%M%S")
            except ValueError:
                # Fallback to file modification time
                mtime = os.path.getmtime(fpath)
                dt = datetime.datetime.fromtimestamp(mtime)
            self._recordings_data.append((fpath, dur, dt))
            self._add_row_with_datetime(fpath, dur, dt)

    def _get_audio_duration(self, path: str) -> float:
        """Get duration of audio file in seconds."""
        try:
            import soundfile as sf

            info = sf.info(path)
            return info.duration
        except Exception:
            pass
        try:
            import wave

            with wave.open(path, "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                return frames / rate if rate > 0 else 0.0
        except Exception:
            return 0.0

    def _add_row_with_datetime(
        self, path: str, dur: float, dt: datetime.datetime
    ) -> None:
        """Add a row to the recordings table with a datetime object."""
        row = self.table.rowCount()
        self.table.insertRow(row)
        date_str, time_str = self._format_datetime(dt)
        date_item = QtWidgets.QTableWidgetItem(date_str)
        date_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, 0, date_item)

        time_item = QtWidgets.QTableWidgetItem(time_str)
        time_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, 1, time_item)

        length_item = QtWidgets.QTableWidgetItem(f"{dur:.1f}s")
        length_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, 2, length_item)
        fg = self.theme_palette["fg"] if self.theme_palette else "#fff"

        # Play button (column 3)
        btnPlay = QtWidgets.QPushButton()
        btnPlay.setIcon(icon_play(18, fg))
        btnPlay.setProperty("variant", "ghost")
        btnPlay.clicked.connect(lambda _, p=path, b=btnPlay: self._playstop(p, b))
        self.table.setCellWidget(row, 3, btnPlay)

        # Waveform widget (column 4)
        waveform = WaveformWidget(path)
        self.table.setCellWidget(row, 4, waveform)

        # Delete button (column 5)
        btnDel = QtWidgets.QPushButton()
        btnDel.setIcon(icon_trash(16, fg))
        btnDel.setProperty("variant", "ghost")
        btnDel.clicked.connect(lambda _, b=btnDel, p=path: self._delete_btn(b, p))
        self.table.setCellWidget(row, 5, btnDel)

    def _add_row(self, path: str, dur: float) -> None:
        """Add a new recording row (for live recordings)."""
        dt = datetime.datetime.now()
        # Store for refresh
        if not hasattr(self, "_recordings_data"):
            self._recordings_data = []
        self._recordings_data.append((path, dur, dt))
        self._add_row_with_datetime(path, dur, dt)

    def _refresh_recordings_table(self) -> None:
        """Refresh the recordings table with current date/time format."""
        if not hasattr(self, "_recordings_data"):
            return
        # Save current data
        data = self._recordings_data[:]
        # Clear table
        self.table.setRowCount(0)
        self._recordings_data = []
        # Re-add all rows
        for path, dur, dt in data:
            if os.path.exists(path):
                self._recordings_data.append((path, dur, dt))
                self._add_row_with_datetime(path, dur, dt)

    def _playstop(self, path: str, btn: QtWidgets.QPushButton) -> None:
        # toggle ako je isti fajl i već svira
        if (
            getattr(btn, "_is_playing", False)
            and self.current_play
            and self.current_play[1] == path
            and self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        ):
            self._stop_current()
            return

        # stop bilo što što već svira
        self._stop_current()
        try:
            url = QtCore.QUrl.fromLocalFile(path)
            self.player.setSource(url)
            self.player.play()
            btn.setIcon(
                icon_stop(
                    18, self.theme_palette["fg"] if self.theme_palette else "#fff"
                )
            )
            btn._is_playing = True
            self.current_play = (weakref.ref(btn), path)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Play error", str(e))
            self._stop_current()

    def _delete_btn(self, btn: QtWidgets.QPushButton, path: str) -> None:
        # pronađi red gdje je ovaj gumb (red se može pomaknuti nakon brisanja)
        row = -1
        try:
            for r in range(self.table.rowCount()):
                if self.table.cellWidget(r, 5) is btn:  # Delete is column 5
                    row = r
                    break
        except Exception:
            row = -1
        if row == -1:
            # fallback – bar obriši datoteku
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception as e:
                QtWidgets.QMessageBox.warning(
                    self, "Delete", f"Cannot delete file:\n{e}"
                )
            return
        self._delete(path, row)

    def _delete(self, path: str, row: int) -> None:
        self._stop_current()
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Delete", f"Cannot delete file:\n{e}")
        self.table.removeRow(row)
        # Remove from recordings data
        if hasattr(self, "_recordings_data"):
            self._recordings_data = [
                (p, d, t) for p, d, t in self._recordings_data if p != path
            ]

    def _delete_all_recordings(self) -> None:
        """Delete all recordings after confirmation."""
        if not hasattr(self, "_recordings_data") or not self._recordings_data:
            QtWidgets.QMessageBox.information(
                self, "Delete All", "No recordings to delete."
            )
            return
        count = len(self._recordings_data)
        reply = QtWidgets.QMessageBox.question(
            self,
            "Delete All",
            f"Are you sure you want to delete all {count} recording(s)?\nThis cannot be undone.",
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self._stop_current()
        errors = []
        for path, _, _ in self._recordings_data[:]:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception as e:
                errors.append(f"{os.path.basename(path)}: {e}")
        self.table.setRowCount(0)
        self._recordings_data = []
        if errors:
            QtWidgets.QMessageBox.warning(
                self,
                "Delete All",
                f"Some files could not be deleted:\n" + "\n".join(errors[:5]),
            )

    def _export_recordings_zip(self) -> None:
        """Export all recordings to a ZIP file."""
        import zipfile

        if not hasattr(self, "_recordings_data") or not self._recordings_data:
            QtWidgets.QMessageBox.information(
                self, "Export", "No recordings to export."
            )
            return
        # Ask for save location
        default_name = datetime.datetime.now().strftime("recordings_%Y%m%d_%H%M%S.zip")
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export Recordings", default_name, "ZIP Files (*.zip)"
        )
        if not path:
            return
        try:
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
                for fpath, _, _ in self._recordings_data:
                    if os.path.exists(fpath):
                        zf.write(fpath, os.path.basename(fpath))
            QtWidgets.QMessageBox.information(
                self,
                "Export",
                f"Exported {len(self._recordings_data)} recording(s) to:\n{path}",
            )
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Export", f"Export failed:\n{e}")

    # ---- sessions/history ----
    def _load_sessions(self) -> list:
        if not os.path.exists(self.sessions_file):
            return []
        try:
            with open(self.sessions_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save_session(
        self, start_dt: QtCore.QDateTime, end_dt: QtCore.QDateTime, dur_s: int
    ) -> None:
        rec = {
            "start": start_dt.toString(QtCore.Qt.DateFormat.ISODate),
            "end": end_dt.toString(QtCore.Qt.DateFormat.ISODate),
            "duration_s": dur_s,
        }
        self.sessions.append(rec)
        try:
            with open(self.sessions_file, "w", encoding="utf-8") as f:
                json.dump(self.sessions, f, ensure_ascii=False, indent=2)
        except Exception as e:
            QtWidgets.QMessageBox.warning(
                self, "Save session", f"Cannot save session log:\n{e}"
            )

    def _refresh_history(self) -> None:
        if not hasattr(self, "sessionTable"):
            return
        self.sessionTable.setRowCount(0)
        days = T[self.lang].get(
            "days", ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        )
        for rec in self.sessions:
            try:
                s = datetime.datetime.fromisoformat(rec["start"])
                e = datetime.datetime.fromisoformat(rec["end"])
            except Exception:
                continue
            dur = int(rec.get("duration_s", int((e - s).total_seconds())))
            r = self.sessionTable.rowCount()
            self.sessionTable.insertRow(r)
            day_name = days[s.weekday()] if 0 <= s.weekday() < 7 else ""
            day_item = QtWidgets.QTableWidgetItem(day_name)
            day_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.sessionTable.setItem(r, 0, day_item)

            date_item = QtWidgets.QTableWidgetItem(self._format_date(s))
            date_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.sessionTable.setItem(r, 1, date_item)

            start_item = QtWidgets.QTableWidgetItem(self._format_time(s))
            start_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.sessionTable.setItem(r, 2, start_item)

            end_item = QtWidgets.QTableWidgetItem(self._format_time(e))
            end_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.sessionTable.setItem(r, 3, end_item)

            duration_item = QtWidgets.QTableWidgetItem(
                f"{dur // 3600:02d}:{(dur % 3600) // 60:02d}"
            )
            duration_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.sessionTable.setItem(r, 4, duration_item)

    # ---- tray helpers ----
    def _tray_show(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _tray_exit(self) -> None:
        try:
            if self.stream:
                self.stream.stop()
                self.stream.close()
        except Exception:
            pass
        try:
            self.player.stop()
        except Exception:
            pass
        QtWidgets.QApplication.quit()

    def closeEvent(self, e: QtGui.QCloseEvent) -> None:
        # Hide to tray; “Exit” iz tray menija za pravo gašenje
        if hasattr(self, "tray") and self.tray.isVisible():
            e.ignore()
            self.hide()
        else:
            super().closeEvent(e)


# ===================== boot =====================
def main() -> None:
    # upozorenje ako PortAudio nije spreman
    try:
        test = sd.InputStream(samplerate=44100, channels=1, blocksize=256)
        test.close()
    except Exception:
        d = detect_distro()
        print("[audio] PortAudio missing/misconfigured. Distro:", d)
        print(system_install_cmd(d))
        print("Or run this script with --setup (needs sudo).")

    # stišaj QtMultimedia/FFmpeg log spam
    try:
        os.environ["QT_LOGGING_RULES"] = (
            "qt.multimedia.ffmpeg.debug=false;qt.multimedia.ffmpeg.mediasource.debug=false;"
            "qt.multimedia.ffmpeg.muxer.debug=false;qt.multimedia.ffmpeg.demuxer.debug=false"
        )
    except Exception:
        pass

    app = QtWidgets.QApplication(sys.argv)
    w = SleepTracker()
    w.apply_theme()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
