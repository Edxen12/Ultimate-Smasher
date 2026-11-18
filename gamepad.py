"""Read game controllers straight from /dev/input (no extra packages) and turn
them into key presses: D-pad/left stick = arrows, Cross/A = Enter, Circle/B = Esc,
L1/R1 = Q/E, Options/Start = Ctrl+S, Share/Select = F1."""
import fcntl
import os
import re
import struct

from PyQt5.QtCore import QEvent, QObject, QSocketNotifier, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QKeyEvent
from PyQt5.QtWidgets import QApplication

EV_KEY, EV_ABS = 1, 3
EVENT = struct.Struct("llHHi")
BUTTONS = {
    304: (Qt.Key_Return, Qt.NoModifier),     # BTN_SOUTH: Cross / A
    305: (Qt.Key_Escape, Qt.NoModifier),     # BTN_EAST: Circle / B
    310: (Qt.Key_Q, Qt.NoModifier),          # L1
    311: (Qt.Key_E, Qt.NoModifier),          # R1
    315: (Qt.Key_S, Qt.ControlModifier),     # Options / Start: save
    314: (Qt.Key_F1, Qt.NoModifier),         # Share / Select: help
}
ABSINFO = struct.Struct("6i")  # value, min, max, fuzz, flat, resolution


def axis_range(fd, code):
    """(min, max) of an axis via EVIOCGABS; PS4 pads report 0..255, Xbox -32768..32767."""
    req = (2 << 30) | (ABSINFO.size << 16) | (ord("E") << 8) | (0x40 + code)
    try:
        _, lo, hi, *_ = ABSINFO.unpack(fcntl.ioctl(fd, req, bytes(ABSINFO.size)))
    except OSError:
        return 0, 255
    return (lo, hi) if hi > lo else (0, 255)


DIRS = {"left": Qt.Key_Left, "right": Qt.Key_Right, "up": Qt.Key_Up, "down": Qt.Key_Down}


class Gamepad(QObject):
    connected_changed = pyqtSignal(bool)

    def __init__(self, window):
        super().__init__(window)
        self.win = window
        self.devs = {}          # path -> (fd, notifier)
        self.hat = {16: 0, 17: 0}
        self.stick = {0: 0.0, 1: 0.0}   # normalised -1..1
        self.ranges = {}                  # fd -> {axis: (min, max)}
        self.held = None
        self.repeat = QTimer(self)
        self.repeat.timeout.connect(self._repeat)
        self.scanner = QTimer(self)
        self.scanner.timeout.connect(self.scan)
        self.scanner.start(2000)
        self.scan()

    @property
    def connected(self):
        return bool(self.devs)

    # ---------------------------------------------------------- devices --
    def scan(self):
        try:
            with open("/proc/bus/input/devices") as f:
                blocks = f.read().split("\n\n")
        except OSError:
            return
        before = self.connected
        for b in blocks:
            m = re.search(r"^H: Handlers=(.*)$", b, re.MULTILINE)
            if not m or not re.search(r"\bjs\d+", m.group(1)):
                continue
            ev = re.search(r"\bevent\d+", m.group(1))
            if not ev:
                continue
            path = "/dev/input/" + ev.group(0)
            if path in self.devs:
                continue
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            except OSError:
                continue
            self.ranges[fd] = {a: axis_range(fd, a) for a in self.stick}
            n = QSocketNotifier(fd, QSocketNotifier.Read, self)
            n.activated.connect(lambda _fd, p=path: self.read(p))
            self.devs[path] = (fd, n)
        if self.connected != before:
            self.connected_changed.emit(self.connected)

    def drop(self, path):
        fd, n = self.devs.pop(path)
        self.ranges.pop(fd, None)
        n.setEnabled(False)
        n.deleteLater()
        try:
            os.close(fd)
        except OSError:
            pass
        self.stop_repeat()
        self.connected_changed.emit(self.connected)

    def read(self, path):
        fd, _ = self.devs.get(path, (None, None))
        if fd is None:
            return
        try:
            data = os.read(fd, EVENT.size * 64)
        except BlockingIOError:
            return
        except OSError:
            self.drop(path)
            return
        for i in range(0, len(data) - EVENT.size + 1, EVENT.size):
            _, _, typ, code, val = EVENT.unpack_from(data, i)
            self.handle(typ, code, val, fd)

    # ----------------------------------------------------------- events --
    def handle(self, typ, code, val, fd=None):
        if not self.win.isActiveWindow():
            self.stop_repeat()
            return
        if typ == EV_KEY and val == 1 and code in BUTTONS:
            self.send(*BUTTONS[code])
        elif typ == EV_ABS and code in self.hat:
            self.hat[code] = val
            self.update_direction()
        elif typ == EV_ABS and code in self.stick:
            lo, hi = self.ranges.get(fd, {}).get(code, (0, 255))
            self.stick[code] = (2 * (val - lo) / (hi - lo)) - 1
            self.update_direction()

    def direction(self):
        hx, hy = self.hat[16], self.hat[17]
        if hx or hy:
            return "left" if hx < 0 else "right" if hx > 0 else "up" if hy < 0 else "down"
        x, y = self.stick[0], self.stick[1]
        if max(abs(x), abs(y)) < 0.62:
            return None
        if abs(x) > abs(y):
            return "left" if x < 0 else "right"
        return "up" if y < 0 else "down"

    def update_direction(self):
        d = self.direction()
        if d == self.held:
            return
        self.stop_repeat()
        if d:
            self.held = d
            self.send(DIRS[d])
            self.repeat.start(380)

    def _repeat(self):
        if self.held:
            self.repeat.setInterval(110)
            self.send(DIRS[self.held])

    def stop_repeat(self):
        self.held = None
        self.repeat.stop()

    def send(self, key, mod=Qt.NoModifier):
        target = QApplication.focusWidget() or self.win
        for t in (QEvent.KeyPress, QEvent.KeyRelease):
            QApplication.sendEvent(target, QKeyEvent(t, key, mod))
