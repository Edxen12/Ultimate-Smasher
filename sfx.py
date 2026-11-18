"""Original UI sound effects, synthesised in pure Python and played with pw-play/paplay."""
import math
import os
import random
import shutil
import struct
import tempfile
import time
import wave
from pathlib import Path

from PyQt5.QtCore import QCoreApplication, QProcess

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


def _write(target, samples):
    with wave.open(target, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(RATE)
        audio.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, s)) * 32767)) for s in samples))


def valid_wav(path):
    try:
        with wave.open(str(path), "rb") as audio:
            frames = audio.getnframes()
            return (
                audio.getnchannels() == 1 and audio.getsampwidth() == 2 and audio.getframerate() == RATE
                and 0 < frames <= RATE * 2 and len(audio.readframes(frames)) == 2 * frames
            )
    except (OSError, wave.Error, EOFError):
        return False


def ensure_files():
    bundled = Path(DIR)
    try:
        if (bundled / ".version").read_text() == VERSION and all(
            valid_wav(bundled / f"{name}.wav") for name in SOUNDS
        ):
            return bundled
    except (OSError, UnicodeError):
        pass
    cache = Path(os.environ.get("XDG_CACHE_HOME", ""))
    if not cache.is_absolute():
        cache = Path.home() / ".cache"
    directory = cache / "ultimate-smasher" / "sounds" / VERSION
    directory.mkdir(parents=True, exist_ok=True)
    for name, make in SOUNDS.items():
        path = directory / f"{name}.wav"
        if valid_wav(path):
            continue
        with tempfile.NamedTemporaryFile(dir=directory, prefix=".sound-", delete=False) as stream:
            temp = Path(stream.name)
            try:
                _write(stream, make())
                stream.close()
                temp.replace(path)
            finally:
                temp.unlink(missing_ok=True)
    return directory


class Player:
    MAX_PROCESSES = 6

    def __init__(self):
        self.cmd = shutil.which("pw-play") or shutil.which("paplay")
        self.muted = bool(os.environ.get("SMASHER_MUTE")) or self.cmd is None
        self.last = {}
        self.procs = set()
        self.directory = None
        app = QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.close)

    def play(self, name, min_gap=0.035):
        if self.muted or name not in SOUNDS or len(self.procs) >= self.MAX_PROCESSES:
            return
        now = time.monotonic()
        if now - self.last.get(name, float("-inf")) < min_gap:
            return
        if self.directory is None:
            try:
                self.directory = ensure_files()
            except OSError:
                self.cmd = None
                self.muted = True
                return
        process = QProcess()
        discard = QProcess.nullDevice()
        process.setStandardOutputFile(discard)
        process.setStandardErrorFile(discard)
        process.finished.connect(lambda *_: self.reap(process))
        process.errorOccurred.connect(lambda error: self.failed(process, error))
        self.procs.add(process)
        self.last[name] = now
        process.start(self.cmd, [str(self.directory / f"{name}.wav")])

    def reap(self, process):
        self.procs.discard(process)
        process.deleteLater()

    def failed(self, process, error):
        if error == QProcess.FailedToStart:
            self.reap(process)
            self.muted = True
            self.cmd = None

    def stop(self):
        for process in tuple(self.procs):
            process.kill()

    def close(self):
        self.stop()
        for process in tuple(self.procs):
            process.waitForFinished(250)

    def toggle(self):
        if self.cmd:
            self.muted = not self.muted
            if self.muted:
                self.stop()
        return not self.muted
