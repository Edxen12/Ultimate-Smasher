"""Original UI sound effects, synthesised in pure Python and played with pw-play/paplay."""
import math
import os
import random
import shutil
import struct
import subprocess
import time
import wave

RATE = 22050
DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sounds")
VERSION = "1"  # bump to regenerate the files


def _env(i, n, attack=0.004, release=None):
    t = i / RATE
    a = min(1.0, t / attack) if attack else 1.0
    r = 1.0 - i / n if release is None else math.exp(-t / release)
    return a * r


def _tone(freqs, dur, vol=0.35, shape="sine", release=None, sweep=None):
    """freqs: list of (start_s, freq). sweep: (f0, f1) overrides with a glide."""
    n = int(dur * RATE)
    out, phase = [], 0.0
    for i in range(n):
        t = i / RATE
        if sweep:
            f = sweep[0] + (sweep[1] - sweep[0]) * (i / n)
        else:
            f = [fr for st, fr in freqs if st <= t][-1]
        phase += 2 * math.pi * f / RATE
        if shape == "square":
            s = 0.6 if math.sin(phase) >= 0 else -0.6
        elif shape == "tri":
            s = 2 / math.pi * math.asin(math.sin(phase))
        else:
            s = math.sin(phase) + 0.25 * math.sin(2 * phase)
        out.append(s * vol * _env(i, n, release=release))
    return out


def _noise(dur, vol=0.25, lo=0.15):
    n = int(dur * RATE)
    rnd = random.Random(3)
    out, y = [], 0.0
    for i in range(n):
        k = lo + (1 - lo) * math.sin(math.pi * i / n)  # filter opens then closes
        y += k * (rnd.uniform(-1, 1) - y)
        out.append(y * vol * math.sin(math.pi * i / n))
    return out


def _mix(*parts):
    n = max(len(p) for p in parts)
    return [sum(p[i] for p in parts if i < len(p)) for i in range(n)]


SOUNDS = {
    "move": lambda: _tone([(0, 1760)], 0.035, 0.22, "tri", release=0.012),
    "select": lambda: _tone([(0, 988), (0.055, 1480)], 0.14, 0.3, "tri", release=0.06),
    "back": lambda: _tone([(0, 1175), (0.05, 740)], 0.12, 0.28, "tri", release=0.05),
    "tab": lambda: _mix(_noise(0.13, 0.22), _tone([(0, 1320)], 0.04, 0.12, "tri", release=0.015)),
    "unlock": lambda: _tone([], 0.11, 0.3, "tri", release=0.06, sweep=(700, 1500)),
    "lock": lambda: _tone([], 0.11, 0.3, "tri", release=0.06, sweep=(900, 380)),
    "save": lambda: _tone([(0, 784), (0.07, 988), (0.14, 1175), (0.21, 1568)], 0.42, 0.3, "tri", release=0.16),
    "error": lambda: _tone([(0, 196), (0.09, 147)], 0.2, 0.22, "square", release=0.09),
    "open": lambda: _mix(_noise(0.18, 0.18), _tone([], 0.16, 0.18, "tri", release=0.07, sweep=(500, 1100))),
}


def _write(path, samples):
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, s)) * 32767)) for s in samples))


def ensure_files():
    stamp = os.path.join(DIR, ".version")
    try:
        with open(stamp) as f:
            current = f.read()
        if current == VERSION and all(os.path.exists(os.path.join(DIR, k + ".wav")) for k in SOUNDS):
            return
    except OSError:
        pass
    os.makedirs(DIR, exist_ok=True)
    for name, make in SOUNDS.items():
        _write(os.path.join(DIR, name + ".wav"), make())
    with open(stamp, "w") as f:
        f.write(VERSION)


class Player:
    def __init__(self):
        self.cmd = shutil.which("pw-play") or shutil.which("paplay")
        self.muted = bool(os.environ.get("SMASHER_MUTE")) or self.cmd is None
        self.last = {}
        self.procs = []
        if self.cmd:
            try:
                ensure_files()
            except OSError:
                self.cmd = None
                self.muted = True

    def play(self, name, min_gap=0.035):
        if self.muted or name not in SOUNDS:
            return
        now = time.monotonic()
        if now - self.last.get(name, 0) < min_gap:
            return
        self.last[name] = now
        self.procs = [p for p in self.procs if p.poll() is None]
        if len(self.procs) > 6:
            return
        try:
            self.procs.append(subprocess.Popen([self.cmd, os.path.join(DIR, name + ".wav")],
                                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        except OSError:
            pass

    def toggle(self):
        if self.cmd:
            self.muted = not self.muted
        return not self.muted
