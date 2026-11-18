"""Headless smoke test of the interface: walks every section and the main flows
on a temporary copy of a save (synthetic unless SMASH_TEST_SAVE is set)."""
import os
import shutil
import tempfile
import unittest

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["SMASHER_MUTE"] = "1"

from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest

import gamepad
import save_data as sd
import smash_ui


def pump(ms=60):
    QTest.qWait(ms)


class UiSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.slot0 = os.path.join(cls.tmp, "0", "save_data")
        cls.slot1 = os.path.join(cls.tmp, "1", "save_data")
        os.makedirs(cls.slot0); os.makedirs(cls.slot1)
        cls.path = os.path.join(cls.slot0, "system_data.bin")
        src = os.environ.get("SMASH_TEST_SAVE")
        for d in (cls.slot0, cls.slot1):
            dst = os.path.join(d, "system_data.bin")
            if src:
                shutil.copy(src, dst)
            else:
                with open(dst, "wb") as f:
                    f.write(bytes(sd.SAVE_SIZE))
        sd.BACKUP_DIR = os.path.join(cls.tmp, "backups")
        sd.ryujinx_running = lambda: False
        cls.app, cls.win = smash_ui.main(["x", cls.path])
        pump(300)

    @classmethod
    def tearDownClass(cls):
        cls.win.force_close = True
        cls.win.close()
        shutil.rmtree(cls.tmp)

    def overlays(self):
        return [c for c in self.win.children() if isinstance(c, smash_ui.Overlay) and not c.closing]

    def test_1_every_section_opens(self):
        for name, *_ in smash_ui.SECTIONS:
            self.win.open_section(name)
            pump()
            self.assertTrue(self.win.pages[self.win.current].isVisible(), name)
            self.win.cycle(1); pump()
        self.win.show_hub(); pump()

    def test_2_edit_restore_and_save(self):
        w, s = self.win, self.win.store.save
        w.open_section("CHARACTERS"); pump()
        w.pages[w.current].set_all(True); pump()
        self.assertEqual(s.fighters_unlocked(), 71)
        w.open_section("ITEMS"); pump()
        w.pages[w.current].max_all()
        w.open_section("STATS"); pump()
        stats = w.pages[w.current]
        row = stats.scroll.widget().findChildren(smash_ui.StatRow)[0]
        row.edit.setFocus(); QTest.keyClicks(row.edit, "4242"); pump()
        row.edit.selectAll(); QTest.keyClicks(row.edit, "4242")
        QTest.keyClick(w, Qt.Key_S, Qt.ControlModifier); pump(200)  # save while still typing
        self.assertEqual(sd.SaveFile(self.path).get(row.off, 4), 4242)
        self.assertFalse(w.store.dirty)
        with open(os.path.join(self.slot1, "system_data.bin"), "rb") as f:
            self.assertEqual(f.read(), bytes(s.data))
        # loading the backup made before that save must refresh the visible stats
        w.open_section("BACKUPS"); pump()
        bp = w.pages[w.current]
        bp.list.setCurrentRow(0)
        bp.restore(); pump(100)
        self.overlays()[-1].accept(); pump(300)
        self.assertTrue(w.store.dirty)
        w.open_section("STATS"); pump()
        row = w.pages[w.current].scroll.widget().findChildren(smash_ui.StatRow)[0]
        self.assertEqual(row.edit.text(), str(s.get(row.off, 4)))
        self.assertNotEqual(row.edit.text(), "4242")

    def test_3_number_overlay(self):
        w = self.win
        w.open_section("GENERAL"); pump()
        page = w.pages[w.current]
        page.edit_number(sd.TICKETS, page.by_field["tickets"]); pump(100)
        ov = self.overlays()[-1]
        ov.set_to(55); ov.accept(); pump(300)
        self.assertEqual(w.store.save.value(sd.TICKETS), 55)
        self.assertEqual(self.overlays(), [])

    def test_4_invalid_file_at_start_shows_error(self):
        bad = os.path.join(self.tmp, "bad.bin")
        with open(bad, "wb") as f:
            f.write(b"nope")
        original_globals = smash_ui.STATUS, smash_ui.CURSOR, smash_ui.PAD
        win = smash_ui.MainWindow(bad)
        try:
            pump(800)  # the error toast fires after 600 ms
            self.assertFalse(win.store.loaded)
            self.assertIn("Not a Smash Ultimate", win.toast_w.text)
        finally:
            smash_ui.STATUS, smash_ui.CURSOR, smash_ui.PAD = original_globals
            win.deleteLater()
            pump()

    def test_5_gamepad_axis_normalisation(self):
        pad = smash_ui.PAD
        pad.ranges[-1] = {0: (-32768, 32767), 1: (-32768, 32767)}
        pad.handle(gamepad.EV_ABS, 0, 0, -1); pad.handle(gamepad.EV_ABS, 1, 0, -1)
        self.assertIsNone(pad.direction())          # Xbox-style stick at rest
        pad.stick[0] = -1.0
        self.assertEqual(pad.direction(), "left")
        pad.stick = {0: 0.0, 1: 0.0}; pad.stop_repeat()

    def test_6_default_is_compact_desktop_window(self):
        self.assertFalse(self.win.isFullScreen())
        self.assertEqual((self.win.width(), self.win.height()), (1040, 590))
        self.assertFalse(self.win.windowFlags() & Qt.FramelessWindowHint)

    def test_7_roster_preview_does_not_edit_save(self):
        w = self.win
        w.open_section("CHARACTERS"); pump(400)
        page = w.pages[w.current]
        before = bytes(w.store.save.data)
        # Keyboard focus and mouse hover both update the lower fighter card.
        page.tiles[64].setFocus(Qt.TabFocusReason); pump(100)
        self.assertEqual(page.selected_idx, 64)
        QTest.mouseMove(page.tiles[0], page.tiles[0].rect().center()); pump(100)
        self.assertEqual(page.selected_idx, 0)
        self.assertEqual(bytes(w.store.save.data), before)
        for tile in page.tiles:
            self.assertTrue(page.rect().contains(tile.geometry()))
            self.assertLess(tile.geometry().bottom(), page.bar_y)
        self.assertTrue(page.rect().contains(page.unlock_all.geometry()))
        self.assertTrue(page.rect().contains(page.lock_all.geometry()))
        w.show_hub(); pump()

    def test_8_menu_tiles_open_real_sections(self):

        import hub_geometry as hg
        w = self.win
        for name in ("CHARACTERS", "ITEMS", "GENERAL", "BACKUPS", "STATS"):
            w.show_hub(); pump(350)
            pos = hg.tile_center(name, w.hub.width(), w.hub.height()).toPoint()
            self.assertEqual(w.hub.tile_at(pos), name)
            QTest.mouseClick(w.hub, Qt.LeftButton, pos=pos); pump(400)
            self.assertEqual(smash_ui.SECTIONS[w.current][0], name)
            self.assertTrue(smash_ui.STATUS.isVisible())
        w.show_hub(); pump(350)
        disc = hg.transform(w.hub.width(), w.hub.height()).map(hg.DISC_C).toPoint()
        self.assertIsNone(w.hub.tile_at(disc))
        self.assertFalse(smash_ui.STATUS.isVisible())
        # Rail help icon is a real action.
        rect = hg.transform(w.hub.width(), w.hub.height()).mapRect(hg.rail_items(len(smash_ui.RAIL))[3])
        QTest.mouseClick(w.hub, Qt.LeftButton, pos=rect.center().toPoint()); pump(450)
        self.assertIsInstance(self.overlays()[-1], smash_ui.HelpOverlay)
        self.overlays()[-1].close_overlay(); pump(250)

    def test_11_items_inventory_detail_and_plus_minus(self):
        w = self.win
        w.open_section("ITEMS"); pump()
        page = w.pages[w.current]
        f = next(x for x in smash_ui.sd.ITEMS if x.key == "rematch")
        page.by_key["rematch"].setFocus(); pump()
        self.assertIs(page.current, f)
        page.set_amount(f, 5); pump()
        QTest.keyClick(page.by_key["rematch"], Qt.Key_Plus); pump()
        self.assertEqual(page.save.value(f), 6)
        QTest.mouseClick(page.minus, Qt.LeftButton); pump()
        self.assertEqual(page.save.value(f), 5)
        QTest.mouseClick(page.maxone, Qt.LeftButton); pump()
        self.assertEqual(page.save.value(f), f.maximum)
        page.set_amount(f, f.maximum + 50)
        self.assertEqual(page.save.value(f), f.maximum)
        w.show_hub(); pump()

    def test_12_every_fighter_has_series_and_stock_art(self):
        for name, img in smash_ui.sd.FIGHTERS:
            self.assertFalse(smash_ui.series_mark(img).isNull(), name)
            self.assertFalse(smash_ui.pixmap(f"stock/{img}.png").isNull(), name)
            self.assertFalse(smash_ui.pixmap(f"portraits/{img}.png").isNull(), name)
            self.assertFalse(smash_ui.pixmap(f"renders/{img}.png").isNull(), name)

    def test_10_portraits_never_overscaled(self):
        from PyQt5.QtCore import QRectF, QSize
        r = smash_ui.fit_pixmap_rect(QSize(94, 62), QRectF(0, 0, 600, 400))
        self.assertLessEqual(r.width(), 94 * 1.6 + 0.01)
        self.assertAlmostEqual(r.width() / r.height(), 94 / 62, places=2)

    def test_9_menu_paints_at_any_size_and_without_art(self):
        from PyQt5.QtGui import QFontDatabase, QPixmap
        fams = QFontDatabase().families()
        self.assertIn("Nunito", fams)
        self.assertIn("Barlow Condensed", fams)
        hub = self.win.hub
        self.assertGreaterEqual(hub.art.width(), 400)
        self.win.show_hub(); pump(200)
        for size in ((1040, 590), (1280, 1024), (1920, 1080), (3840, 2160)):
            hub.resize(*size)
            self.assertFalse(hub.grab().isNull())
        art, hub.art = hub.art, QPixmap()
        try:
            self.assertFalse(hub.grab().isNull())
        finally:
            hub.art = art
            hub.setGeometry(0, 0, self.win.width(), self.win.height())


if __name__ == "__main__":
    unittest.main()
