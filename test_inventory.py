"""Inventory legibility and keyboard scrolling on native Qt widgets."""
import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path


class InventoryTest(unittest.TestCase):
    def test_responsive_names_keyboard_scroll_and_edit_state(self):
        script = """
import os
import tempfile
from PyQt5.QtCore import QPoint, QRectF, Qt
from PyQt5.QtGui import QFontMetricsF
from PyQt5.QtTest import QTest
import save_data as sd
import smash_ui as ui

with tempfile.TemporaryDirectory() as directory:
    path = os.path.join(directory, 'system_data.bin')
    with open(path, 'wb') as stream:
        stream.write(bytes(sd.SAVE_SIZE))
    app, window = ui.main(['test', path])
    for _ in range(200):
        if not window.store.busy:
            break
        QTest.qWait(10)
    assert window.store.loaded
    window.setMinimumSize(0, 0)
    for width, height in ((1040, 590), (960, 540), (800, 600), (1920, 1080)):
        window.resize(width, height)
        window.open_section('ITEMS')
        QTest.qWait(30)
        page = window.pages[window.current]
        for tile in page.btns:
            assert tile.width() >= 108, (width, tile.width())
            bounds = QFontMetricsF(ui.label_font(12, ui.QFont.Bold)).boundingRect(
                QRectF(0, 0, tile.width() - 20, 34), Qt.AlignCenter | Qt.TextWordWrap, tile.field.name)
            assert bounds.height() <= 35, (tile.field.name, bounds.height())
        last = page.btns[-1]
        last.clearFocus()
        last.setFocus()
        QTest.qWait(20)
        top = last.mapTo(page.scroll.viewport(), QPoint(0, 0))
        bottom = last.mapTo(page.scroll.viewport(), last.rect().bottomRight())
        assert page.scroll.viewport().rect().contains(top), (width, top)
        assert page.scroll.viewport().rect().contains(bottom), (width, bottom)
        assert page.current is last.field
        scroll_position = page.scroll.verticalScrollBar().value()
        page.set_amount(page.current, width % page.current.maximum)
        QTest.qWait(20)
        assert page.scroll.verticalScrollBar().value() == scroll_position
        assert page.current is last.field
        if width == 960:
            assert window.selection_cursor.target is last
            assert window.selection_cursor.target_rect() is not None
            page.scroll.verticalScrollBar().setValue(0)
            QTest.qWait(20)
            assert window.selection_cursor.target_rect() is None
            assert window.selection_cursor.cur.isNull()
            page.scroll.ensureWidgetVisible(last, 6, 6)
            QTest.qWait(20)
            assert window.selection_cursor.target_rect() is not None
            assert not window.selection_cursor.cur.isNull()
    window.force_close = True
    window.close()
"""
        result = subprocess.run(
            [sys.executable, "-c", textwrap.dedent(script)],
            cwd=Path(__file__).resolve().parent,
            env=dict(os.environ, QT_QPA_PLATFORM="offscreen", SMASHER_MUTE="1", SMASHER_REDUCE_MOTION="1"),
            text=True, capture_output=True, check=False, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
