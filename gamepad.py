"""Translate Linux evdev and Windows XInput controllers into editor controls."""
import os
import re
import struct
import sys
from dataclasses import dataclass, field

if sys.platform.startswith("linux"):
    import fcntl
else:
    fcntl = None

from PyQt5 import sip
from PyQt5.QtCore import QEvent, QObject, QSocketNotifier, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QKeyEvent
from PyQt5.QtWidgets import QApplication, QCheckBox, QComboBox

EV_SYN, EV_KEY, EV_ABS = 0, 1, 3
SYN_REPORT, SYN_DROPPED = 0, 3
STICK_AXES = (0, 1)
HAT_AXES = (16, 17)
BTN_DPAD_UP, BTN_DPAD_DOWN, BTN_DPAD_LEFT, BTN_DPAD_RIGHT = range(0x220, 0x224)
DPAD_BUTTONS = {BTN_DPAD_UP, BTN_DPAD_DOWN, BTN_DPAD_LEFT, BTN_DPAD_RIGHT}
KEY_A, KEY_Z = 30, 44
BTN_SOUTH = 0x130
KEY_WORD_BITS = struct.calcsize("L") * 8
EVENT = struct.Struct("llHHi")
BUTTONS = {
    BTN_SOUTH: (Qt.Key_Return, Qt.NoModifier),  # Cross / A
    305: (Qt.Key_Escape, Qt.NoModifier),     # BTN_EAST: Circle / B
    315: (Qt.Key_S, Qt.ControlModifier),     # Options / Start: save
    314: (Qt.Key_F1, Qt.NoModifier),         # Share / Select: help
}
SECTION_BUTTONS = {310: -1, 311: 1}          # L1 / R1
ABSINFO = struct.Struct("6i")  # value, min, max, fuzz, flat, resolution
XINPUT_DPAD = {
    0x0001: BTN_DPAD_UP, 0x0002: BTN_DPAD_DOWN,
    0x0004: BTN_DPAD_LEFT, 0x0008: BTN_DPAD_RIGHT,
}
XINPUT_BUTTONS = {0x0010: 315, 0x0020: 314, 0x0100: 310, 0x0200: 311, 0x1000: BTN_SOUTH, 0x2000: 305}


def open_xinput():
    """Return a state reader backed by the Windows system DLL."""
    import ctypes

    class State(ctypes.Structure):
        _fields_ = [
            ("packet", ctypes.c_uint32), ("buttons", ctypes.c_uint16),
            ("left_trigger", ctypes.c_ubyte), ("right_trigger", ctypes.c_ubyte),
            ("left_x", ctypes.c_int16), ("left_y", ctypes.c_int16),
            ("right_x", ctypes.c_int16), ("right_y", ctypes.c_int16),
        ]

    for dll in ("xinput1_4", "xinput9_1_0"):
        try:
            get_state = ctypes.WinDLL(dll, winmode=0x800).XInputGetState  # Search System32 only.
        except (OSError, AttributeError):
            continue
        get_state.argtypes = (ctypes.c_uint32, ctypes.POINTER(State))
        get_state.restype = ctypes.c_uint32
        break
    else:
        return None

    def read(slot):
        state = State()
        if get_state(slot, ctypes.byref(state)) != 0:
            return None
        return state.buttons, state.left_x, -1 - state.left_y

    return read


def axis_range(fd, code):
    """(min, max) of an axis via EVIOCGABS; PS4 pads report 0..255, Xbox -32768..32767."""
    req = (2 << 30) | (ABSINFO.size << 16) | (ord("E") << 8) | (0x40 + code)
    try:
        _, lo, hi, *_ = ABSINFO.unpack(fcntl.ioctl(fd, req, bytes(ABSINFO.size)))
    except OSError:
        return 0, 255
    return (lo, hi) if hi > lo else (0, 255)


DIRS = {"left": Qt.Key_Left, "right": Qt.Key_Right, "up": Qt.Key_Up, "down": Qt.Key_Down}


def has_gamepad_keys(block):
    match = re.search(r"^B: KEY=([a-fA-F0-9 ]+)$", block, re.MULTILINE)
    if match is None:
        return False
    # /proc prints hexadecimal native words in descending bit order.
    bitmap = [int(word, 16) for word in reversed(match.group(1).split())]

    def supports(key):
        word, bit = divmod(key, KEY_WORD_BITS)
        return word < len(bitmap) and bool(bitmap[word] & (1 << bit))

    # Virtual keyboards may advertise the gamepad button codes as well.
    if supports(KEY_A) and supports(KEY_Z):
        return False
    return any(supports(key) for key in DPAD_BUTTONS | {BTN_SOUTH})


@dataclass(eq=False)
class Device:
    fd: int | None
    notifier: QSocketNotifier | None
    ranges: dict
    axes: dict = field(default_factory=lambda: dict.fromkeys(STICK_AXES + HAT_AXES, 0))
    dpad: set = field(default_factory=set)
    lost_sync: bool = False
    xinput_state: tuple[int, int, int] | None = None

    def reset_axes(self):
        self.axes = dict.fromkeys(self.axes, 0)
        self.dpad.clear()

    def set_axis(self, code, value):
        if code in STICK_AXES:
            lo, hi = self.ranges[code]
            value = 2 * (value - lo) / (hi - lo) - 1
        self.axes[code] = value

    def direction(self):
        hx, hy = (self.axes[axis] for axis in HAT_AXES)
        if self.dpad:
            hx = (BTN_DPAD_RIGHT in self.dpad) - (BTN_DPAD_LEFT in self.dpad)
            hy = (BTN_DPAD_DOWN in self.dpad) - (BTN_DPAD_UP in self.dpad)
        if hx:
            return "left" if hx < 0 else "right"
        if hy:
            return "up" if hy < 0 else "down"
        x, y = (self.axes[axis] for axis in STICK_AXES)
        if max(abs(x), abs(y)) < 0.62:
            return None
        if abs(x) > abs(y):
            return "left" if x < 0 else "right"
        return "up" if y < 0 else "down"


class Gamepad(QObject):
    connected_changed = pyqtSignal(bool)
    section_step = pyqtSignal(int)

    def __init__(self, window):
        super().__init__(window)
        self.win = window
        self.devs = {}          # path -> Device
        self.held = None        # (device, Qt key)
        self.repeat = QTimer(self)
        self.repeat.timeout.connect(self._repeat)
        self.scanner = QTimer(self)
        self.xinput = None
        self.win.installEventFilter(self)
        self.win.destroyed.connect(self.close_devices)
        if fcntl is not None:
            self.scanner.timeout.connect(self.scan)
            self.scanner.start(2000)
            self.scan()
        elif sys.platform == "win32":
            self.xinput = open_xinput()
            if self.xinput is not None:
                self.scanner.timeout.connect(self.poll_xinput)
                self.scanner.start(350)
                self.poll_xinput()

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
        paths = set()
        for b in blocks:
            m = re.search(r"^H: Handlers=(.*)$", b, re.MULTILINE)
            if not m or not (re.search(r"\bjs\d+\b", m.group(1)) or has_gamepad_keys(b)):
                continue
            ev = re.search(r"\bevent\d+", m.group(1))
            if not ev:
                continue
            paths.add("/dev/input/" + ev.group(0))
        before = self.connected
        for path in self.devs.keys() - paths:
            self.close_device(path)
        for path in sorted(paths - self.devs.keys()):
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            except OSError:
                continue
            ranges = {axis: axis_range(fd, axis) for axis in STICK_AXES}
            n = QSocketNotifier(fd, QSocketNotifier.Read, self)
            n.activated.connect(lambda _fd, p=path: self.read(p))
            self.devs[path] = Device(fd, n, ranges)
        if self.connected != before:
            self.connected_changed.emit(self.connected)

    def drop(self, path):
        self.close_device(path)
        if not self.connected:
            self.connected_changed.emit(False)

    def close_device(self, path):
        device = self.devs.pop(path)
        if device.notifier is not None:
            device.notifier.setEnabled(False)
            device.notifier.deleteLater()
            try:
                os.close(device.fd)
            except OSError:
                pass
        self.release_device(device)

    def close_devices(self):
        for path in list(self.devs):
            self.close_device(path)

    def read(self, path):
        device = self.devs.get(path)
        if device is None:
            return
        try:
            data = os.read(device.fd, EVENT.size * 64)
        except BlockingIOError:
            return
        except OSError:
            self.drop(path)
            return
        if not data:
            self.drop(path)
            return
        for i in range(0, len(data) - EVENT.size + 1, EVENT.size):
            _, _, typ, code, val = EVENT.unpack_from(data, i)
            self.handle(device, typ, code, val)

    def poll_xinput(self):
        before = self.connected
        for slot in range(4):
            sample = self.xinput(slot)
            device = self.devs.get(slot)
            if sample is None:
                if device is not None:
                    self.close_device(slot)
            elif device is None:
                ranges = dict.fromkeys(STICK_AXES, (-32768, 32767))
                self.devs[slot] = Device(None, None, ranges, xinput_state=sample)
            else:
                self.handle_xinput(device, sample)
        interval = 24 if self.connected else 350
        if self.scanner.interval() != interval:
            self.scanner.setInterval(interval)
        if self.connected != before:
            self.connected_changed.emit(self.connected)

    def handle_xinput(self, device, sample):
        old_buttons, old_x, old_y = device.xinput_state
        device.xinput_state = sample
        if (old_buttons, old_x, old_y) == sample or not self.can_send():
            return
        buttons, x, y = sample
        previous = device.direction()
        device.dpad = {key for mask, key in XINPUT_DPAD.items() if buttons & mask}
        device.set_axis(0, x)
        device.set_axis(1, y)
        self.update_direction(device, previous)
        pressed = buttons & ~old_buttons
        for mask, key in XINPUT_BUTTONS.items():
            if pressed & mask:
                self.handle(device, EV_KEY, key, 1)

    # ----------------------------------------------------------- events --
    def eventFilter(self, obj, event):
        typ = event.type()
        if typ in (QEvent.WindowDeactivate, QEvent.Hide) or (typ == QEvent.EnabledChange and not self.can_send()):
            self.stop_repeat()
            for device in self.devs.values():
                device.reset_axes()
        return False

    def can_send(self):
        return self.receiver() is not None

    def receiver(self):
        if sip.isdeleted(self.win) or not self.win.isVisible():
            return None
        active = QApplication.activeWindow()
        if active is None or not self.owns(active):
            return None
        surface = QApplication.activePopupWidget() or QApplication.activeModalWidget() or self.win
        if not self.owns(surface) or not surface.isVisible() or not surface.isEnabled():
            return None
        return surface.focusWidget() or surface

    def owns(self, widget):
        # Qt's isAncestorOf stops at a dialog or popup's window boundary.
        while widget is not None:
            if widget is self.win:
                return True
            widget = widget.parentWidget()
        return False

    def handle(self, device, typ, code, val):
        if typ == EV_SYN:
            if code == SYN_DROPPED:
                device.lost_sync = True
                device.reset_axes()
                self.release_device(device)
            elif code == SYN_REPORT:
                device.lost_sync = False
            return
        if device.lost_sync or not self.can_send():
            return
        if typ == EV_KEY and code in DPAD_BUTTONS:
            if val in (0, 1):
                previous = device.direction()
                if val:
                    device.dpad.add(code)
                else:
                    device.dpad.discard(code)
                self.update_direction(device, previous)
        elif typ == EV_KEY and val == 1:
            if code in SECTION_BUTTONS:
                if QApplication.activePopupWidget() is None and QApplication.activeModalWidget() is None:
                    self.section_step.emit(SECTION_BUTTONS[code])
            elif code in BUTTONS:
                self.send(*BUTTONS[code])
        elif typ == EV_ABS and code in device.axes:
            self.handle_axis(device, code, val)

    def handle_axis(self, device, code, val):
        previous = device.direction()
        device.set_axis(code, val)
        self.update_direction(device, previous)

    def update_direction(self, device, previous):
        direction = device.direction()
        if direction == previous:
            return
        if direction is None:
            self.release_device(device)
        else:
            key = DIRS[direction]
            self.held = (device, key)
            self.repeat.start(380)
            self.send(key)

    def release_device(self, device):
        if self.held is not None and self.held[0] is device:
            self.stop_repeat()

    def _repeat(self):
        if self.held is None or not self.can_send():
            self.stop_repeat()
            return
        self.repeat.setInterval(110)
        self.send(self.held[1])

    def stop_repeat(self):
        self.held = None
        self.repeat.stop()

    def send(self, key, mod=Qt.NoModifier):
        target = self.receiver()
        if target is None:
            return
        if key == Qt.Key_Return and isinstance(target, (QCheckBox, QComboBox)):
            key = Qt.Key_Space
        QApplication.sendEvent(target, QKeyEvent(QEvent.KeyPress, key, mod))
        if not sip.isdeleted(target):
            QApplication.sendEvent(target, QKeyEvent(QEvent.KeyRelease, key, mod))
