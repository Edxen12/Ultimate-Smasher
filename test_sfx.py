import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

import sfx


class SoundEffectsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QApplication.instance() or QApplication([])

    def test_missing_or_truncated_sounds_are_generated_in_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            checkout_sounds = base / "checkout" / "sounds"
            with patch.object(sfx, "DIR", checkout_sounds), patch.dict(os.environ, XDG_CACHE_HOME=str(base)):
                destination = sfx.ensure_files()
                self.assertFalse(checkout_sounds.exists())
                self.assertEqual(destination, base / "ultimate-smasher" / "sounds" / sfx.VERSION)
                self.assertTrue(all(sfx.valid_wav(destination / f"{name}.wav") for name in sfx.SOUNDS))
                wave = destination / "move.wav"
                wave.write_bytes(wave.read_bytes()[:64])
                self.assertFalse(sfx.valid_wav(wave))
                sfx.ensure_files()
                self.assertTrue(sfx.valid_wav(wave))

    def test_mute_skips_sound_initialization(self):
        with (
            patch.dict(os.environ, SMASHER_MUTE="1"),
            patch.object(sfx.shutil, "which", return_value="/usr/bin/pw-play"),
            patch.object(sfx, "ensure_files") as prepare,
        ):
            player = sfx.Player()
            player.play("move")
        prepare.assert_not_called()
        self.assertFalse(player.procs)

    def test_qt_reaps_finished_playback_without_another_sound(self):
        command = shutil.which("true")
        self.assertIsNotNone(command)
        with (
            patch.dict(os.environ, SMASHER_MUTE=""),
            patch.object(sfx.shutil, "which", return_value=command),
            patch.object(sfx, "ensure_files", return_value=Path(sfx.DIR)),
        ):
            player = sfx.Player()
            self.addCleanup(player.close)
            for _ in range(player.MAX_PROCESSES + 1):
                player.play("move", min_gap=0)
            self.assertEqual(len(player.procs), player.MAX_PROCESSES)
            for _ in range(100):
                if not player.procs:
                    break
                QTest.qWait(10)
            self.assertFalse(player.procs)


if __name__ == "__main__":
    unittest.main()
