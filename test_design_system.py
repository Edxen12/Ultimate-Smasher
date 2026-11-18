"""Exercise Qt animation lifetime in subprocesses, without owning the UI suite's app."""
import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path


class DesignSystemTest(unittest.TestCase):
    def run_qt(self, script):
        preamble = """
import design_system as ds
from PyQt5.QtCore import QObject, QVariantAnimation
from PyQt5.QtWidgets import QApplication
from PyQt5.QtTest import QTest
import smash_ui as ui
app = QApplication([])
ds.settings.set_reduced_motion(False, persist=False)
"""
        result = subprocess.run(
            [sys.executable, "-c", textwrap.dedent(preamble) + textwrap.dedent(script)],
            cwd=Path(__file__).resolve().parent,
            env=dict(os.environ, QT_QPA_PLATFORM="offscreen", SMASHER_MUTE="1", SMASHER_REDUCE_MOTION="0"),
            capture_output=True, text=True, timeout=15, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_replacing_tween_cancels_its_delayed_start(self):
        self.run_qt("""
owner = QObject()
values = []
ui.tween(owner, 'value', 0, 1, 20, lambda v: values.append(('old', v)), delay=80)
ui.tween(owner, 'value', 0, 2, 20, lambda v: values.append(('new', v)))
QTest.qWait(150)
assert values[-1] == ('new', 2.0), values
assert all(name != 'old' for name, _ in values), values
assert len(owner.findChildren(QVariantAnimation)) == 1
""")

    def test_repeated_tweens_do_not_accumulate_qt_objects(self):
        self.run_qt("""
owner = QObject()
for i in range(80):
    ui.tween(owner, 'hover', 0, 1, 20, lambda _: None, delay=50)
QTest.qWait(100)
assert len(owner.findChildren(QVariantAnimation)) == 1
""")

    def test_reducing_motion_completes_active_and_delayed_work_once(self):
        self.run_qt("""
owner = QObject()
values, completed = {}, []
ui.tween(owner, 'active', 0, 1, 1000, lambda v: values.update(active=v),
         done=lambda: completed.append('active'))
ui.tween(owner, 'delayed', 0, 9, 1000, lambda v: values.update(delayed=v),
         done=lambda: completed.append('delayed'), delay=60)
QTest.qWait(20)
ds.settings.set_reduced_motion(True, persist=False)
assert values == {'active': 1.0, 'delayed': 9.0}, values
QTest.qWait(120)
assert sorted(completed) == ['active', 'delayed'], completed
assert all(a.state() == QVariantAnimation.Stopped for a in owner.findChildren(QVariantAnimation))
ui.tween(owner, 'pulse', 0, 1, 1000, lambda v: values.update(pulse=v), loops=-1)
assert values['pulse'] == 1.0
assert owner._tweens['pulse'].state() == QVariantAnimation.Stopped
""")

    def test_typography_and_native_control_styles_use_shared_tokens(self):
        self.run_qt("""
assert ui.label_font(16).family() == ds.tokens.type.functional
assert ui.heavy_italic(28).family() == ds.tokens.type.display
assert ui.game_font(22).family() == ds.tokens.type.functional
style = ds.stylesheet()
assert style.startswith('* {')
assert ds.tokens.colors.yellow in style
assert 'QLineEdit:disabled' in style and 'QComboBox:focus' in style
app.setStyleSheet(style)
""")


if __name__ == "__main__":
    unittest.main()
