"""Headless smoke test of the interface: walks every section and the main flows
on a temporary copy of a save (synthetic unless SMASH_TEST_SAVE is set)."""
import os
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["SMASHER_MUTE"] = "1"

from PyQt5.QtCore import QSettings, Qt
from PyQt5.QtTest import QTest

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
        with patch.object(smash_ui.gamepad.Gamepad, "scan"):
            cls.app, cls.win = smash_ui.main(["x", cls.path])
        cls.initial_page_count = len(cls.win.pages)
        pump(300)

    @classmethod
    def tearDownClass(cls):
        cls.win.force_close = True
        cls.win.close()
        shutil.rmtree(cls.tmp)

    def overlays(self):
        return [c for c in self.win.children() if isinstance(c, smash_ui.Overlay) and not c.closing]

    def wait_for_idle(self):
        for _ in range(300):
            if not self.win.store.busy:
                break
            pump(10)
        self.assertFalse(self.win.store.busy)

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
        if self.overlays():
            self.overlays()[-1].btns[0].click(); pump(250)
        w.open_section("STATS"); pump()
        stats = w.pages[w.current]
        row = stats.scroll.widget().findChildren(smash_ui.StatRow)[0]
        row.edit.setFocus(); QTest.keyClicks(row.edit, "4242"); pump()
        row.edit.selectAll(); QTest.keyClicks(row.edit, "4242")
        QTest.keyClick(w, Qt.Key_S, Qt.ControlModifier); pump(200)  # save while still typing
        for _ in range(500):
            if not w.store.busy:
                break
            pump(10)
        self.assertFalse(w.store.busy)
        self.assertEqual(sd.SaveFile(self.path).get(row.off, 4), 4242)
        self.assertFalse(w.store.dirty)
        with open(os.path.join(self.slot1, "system_data.bin"), "rb") as f:
            self.assertEqual(f.read(), bytes(s.data))
        # loading the backup made before that save must refresh the visible stats
        w.open_section("BACKUPS"); pump()
        bp = w.pages[w.current]
        bp.list.setCurrentRow(0)
        bp.restore(); pump(100)
        self.overlays()[-1].btns[0].click(); pump(300)
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
        with patch.object(smash_ui.gamepad.Gamepad, "scan"):
            win = smash_ui.MainWindow(bad)
        try:
            pump(300)
            self.assertFalse(win.store.loaded)
            self.assertIn("Not a Smash Ultimate", win.toast_w.text)
        finally:
            win.deleteLater()
            pump()

    def test_6_default_is_compact_desktop_window(self):
        self.assertEqual(self.initial_page_count, 0)
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
        page.scroll.ensureWidgetVisible(page.tiles[0]); pump(100)
        QTest.mouseMove(page.tiles[0], page.tiles[0].rect().center()); pump(100)
        self.assertEqual(page.selected_idx, 0)
        self.assertEqual(bytes(w.store.save.data), before)
        for tile in page.tiles:
            self.assertTrue(page.roster_body.rect().contains(tile.geometry()))
            self.assertGreaterEqual(tile.width(), 100)
        self.assertTrue(page.rect().contains(page.scroll.geometry()))
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
            self.assertTrue(w.status.isVisible())
        w.show_hub(); pump(350)
        disc = hg.transform(w.hub.width(), w.hub.height()).map(hg.DISC_C).toPoint()
        self.assertIsNone(w.hub.tile_at(disc))
        self.assertFalse(w.status.isVisible())
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

    def test_12_roster_paints_without_optional_art(self):
        w = self.win
        with tempfile.TemporaryDirectory() as img, patch.object(smash_ui, "IMG", img), patch.object(smash_ui, "_PIX", {}):
            w.open_section("CHARACTERS")
            page = w.pages[w.current]
            with patch.multiple(page.tiles[0], src=smash_ui.QPixmap(), _gray={}):
                page.preview(0)
                self.assertFalse(page.tiles[0].grab().isNull())
                self.assertFalse(page.grab().isNull())
            w.show_hub()

    def test_13_rail_reachable_with_keys(self):
        w = self.win
        w.show_hub(); pump(300)
        hub = w.hub
        hub.set_hover("GENERAL")
        QTest.keyClick(hub, Qt.Key_Right); pump()
        self.assertEqual(hub.rail_hover, 1)
        self.assertIsNone(hub.hover)
        QTest.keyClick(hub, Qt.Key_Down); QTest.keyClick(hub, Qt.Key_Down); pump()
        self.assertEqual(hub.rail_hover, 3)
        QTest.keyClick(hub, Qt.Key_Return); pump(450)
        self.assertIsInstance(self.overlays()[-1], smash_ui.HelpOverlay)
        self.overlays()[-1].close_overlay(); pump(250)
        QTest.keyClick(hub, Qt.Key_Left); pump()
        self.assertIsNone(hub.rail_hover)
        self.assertEqual(hub.hover, "GENERAL")

    def test_14_dialog_tab_focus_stays_inside(self):
        w = self.win
        w.open_section("GENERAL"); pump(300)
        before = bytes(w.store.save.data)
        for overlay in (
            smash_ui.HelpOverlay(w),
            smash_ui.NumberOverlay(w, sd.TICKETS, w.store.save.value(sd.TICKETS), lambda _: None),
            smash_ui.ConfirmOverlay(w, "Test", "Choose an action", [
                ("OK", "", "yellow", None), ("CANCEL", "", "dark", None)]),
        ):
            overlay.open(); pump(450)
            for modifier in (Qt.NoModifier, Qt.ShiftModifier):
                for _ in range(18):
                    QTest.keyClick(self.app.focusWidget(), Qt.Key_Tab, modifier)
                    pump(5)
                    focus = self.app.focusWidget()
                    self.assertTrue(focus is overlay or overlay.isAncestorOf(focus))
            QTest.keyClick(self.app.focusWidget(), Qt.Key_Escape); pump(250)
        self.assertEqual(bytes(w.store.save.data), before)
        w.show_hub(); pump()

    def test_15_pending_stat_is_confirmed_before_close_or_open(self):
        w = self.win
        for action in ("close", "open"):
            w.store.load(self.path)
            w.open_section("STATS"); pump(350)
            page = w.pages[w.current]
            page.show_cat("Combined"); pump(300)
            row = page.scroll.widget().findChildren(smash_ui.StatRow)[0]
            row.edit.setFocus(); pump()
            row.edit.selectAll()
            value = (row.value + 1) % sd.STAT_MAX
            QTest.keyClicks(row.edit, str(value))
            self.assertFalse(w.store.dirty)
            with patch.object(smash_ui.QFileDialog, "getOpenFileName") as dialog:
                QTest.keyClick(row.edit, Qt.Key_Q if action == "close" else Qt.Key_O, Qt.ControlModifier)
                pump(450)
                dialog.assert_not_called()
            self.assertTrue(w.isVisible())
            self.assertTrue(w.store.dirty)
            self.assertEqual(w.store.save.get(row.off, 4), value)
            self.assertIn("●", w.windowTitle())
            self.assertIsInstance(self.overlays()[-1], smash_ui.ConfirmOverlay)
            self.overlays()[-1].close_overlay(); pump(250)
        w.store.load(self.path)
        self.assertNotIn("●", w.windowTitle())
        w.show_hub(); pump()

    def test_16_resize_reflows_every_section_and_keeps_data(self):
        w = self.win
        before = bytes(w.store.save.data)
        try:
            self.assertGreater(w.maximumWidth(), 1040)
            for size in ((1280, 720), (1600, 590), (1040, 900)):
                w.resize(*size); pump()
                for name, *_ in smash_ui.SECTIONS:
                    w.open_section(name); pump(260)
                    page = w.pages[w.current]
                    self.assertEqual(page.width(), size[0])
                    for button in page.findChildren(smash_ui.AnimButton):
                        self.assertTrue(button.parentWidget().rect().contains(button.geometry()), (size, name, button.title))
                    self.assertEqual(w.status.geometry().bottom(), w.height() - 1)
                w.show_hub(); pump(300)
                self.assertEqual(w.hub.geometry(), w.rect())
            self.assertEqual(bytes(w.store.save.data), before)
        finally:
            w.resize(1040, 590)
            w.show_hub(); pump(300)

    def test_17_fullscreen_restores_window_and_centers_dialog(self):
        w = self.win
        w.resize(1280, 720)
        w.open_section("STATS"); pump(300)
        row = w.pages[w.current].scroll.widget().findChildren(smash_ui.StatRow)[0]
        row.edit.setFocus(); pump()
        row.edit.selectAll(); QTest.keyClicks(row.edit, "123")
        try:
            QTest.keyClick(row.edit, Qt.Key_F11); pump(150)
            self.assertTrue(w.isFullScreen())
            self.assertEqual(row.edit.text(), "123")
            overlay = smash_ui.HelpOverlay(w).open(); pump(300)
            QTest.keyClick(self.app.focusWidget(), Qt.Key_F11); pump(150)
            self.assertFalse(w.isFullScreen())
            self.assertEqual((w.width(), w.height()), (1280, 720))
            self.assertEqual(overlay.geometry(), w.rect())
            self.assertEqual(overlay.card.x(), (w.width() - overlay.CARD_W) // 2)
            self.assertEqual(overlay.card.y(), (w.height() - overlay.CARD_H) // 2 + 10)
            overlay.close_overlay(); pump(250)
            w.showMaximized(); pump(150)
            w.toggle_fullscreen(); pump(150)
            self.assertTrue(w.isFullScreen())
            w.toggle_fullscreen(); pump(150)
            self.assertTrue(w.isMaximized())
            w.showNormal(); pump(150)
            w.show_hub(); pump(300)
            QTest.keyClick(w.hub, Qt.Key_F11); pump(150)
            QTest.keyClick(w.hub, Qt.Key_Escape); pump(150)
            self.assertFalse(w.isFullScreen())
            self.assertEqual(self.overlays(), [])
        finally:
            w.showNormal()
            w.resize(1040, 590)
            w.show_hub(); pump(300)

    def test_18_small_logical_screen_keeps_controls_inside(self):
        w = self.win
        try:
            for size in ((960, 540), (800, 450)):
                w.resize(*size); pump()
                self.assertEqual((w.width(), w.height()), size)
                for name, *_ in smash_ui.SECTIONS:
                    w.open_section(name); pump(260)
                    page = w.pages[w.current]
                    for button in page.findChildren(smash_ui.AnimButton):
                        self.assertTrue(button.parentWidget().rect().contains(button.geometry()), (size, name, button.title))
                overlay = smash_ui.HelpOverlay(w).open()
                pump(300)
                self.assertTrue(w.rect().contains(overlay.card.geometry()))
                overlay.close_overlay()
                pump(200)
        finally:
            w.resize(1040, 590)
            w.show_hub(); pump(300)

    def test_19_roster_search_filters_and_scrolling_do_not_edit(self):
        w = self.win
        w.open_section("CHARACTERS"); pump(300)
        page = w.pages[w.current]
        before = bytes(w.store.save.data)
        page.search.setText("samus"); pump()
        self.assertEqual(len(page.visible_tiles), 3)
        self.assertEqual([t.idx for t in page.visible_tiles], sorted(t.idx for t in page.visible_tiles))
        page.search.setFocus(); pump()
        QTest.mouseMove(page.visible_tiles[0], page.visible_tiles[0].rect().center()); pump()
        self.assertIs(self.app.focusWidget(), page.search)
        page.search.setText("no fighter has this name"); pump()
        self.assertEqual(page.visible_tiles, [])
        self.assertTrue(page.empty.isVisible())
        page.search.clear(); page.filter.setCurrentIndex(1); pump()
        self.assertTrue(all(not t.unlocked for t in page.visible_tiles))
        page.filter.setCurrentIndex(2); pump()
        self.assertTrue(all(t.unlocked for t in page.visible_tiles))
        page.filter.setCurrentIndex(0); pump()
        page.tiles[-1].setFocus(); pump()
        self.assertGreater(page.scroll.verticalScrollBar().value(), 0)
        self.assertEqual(bytes(w.store.save.data), before)
        w.show_hub(); pump()

    def test_20_bulk_items_confirm_scope_and_undo_redo(self):
        w = self.win
        w.store.load(self.path)
        w.open_section("ITEMS"); pump(300)
        page = w.pages[w.current]
        w.store.edit(lambda save: [save.set_value(f, 0) for f in sd.ITEMS], "Prepare inventory")
        before = bytes(w.store.save.data)
        page.max_all(); pump(300)
        overlay = self.overlays()[-1]
        self.assertEqual(overlay.default.text(), "CANCEL")
        overlay.accept(); pump(250)
        self.assertEqual(bytes(w.store.save.data), before)
        page.max_all(); pump(300)
        self.overlays()[-1].btns[0].click(); pump(250)
        after = bytes(w.store.save.data)
        self.assertTrue(all(page.amount(f) == f.maximum for f in sd.ITEMS))
        QTest.keyClick(w, Qt.Key_Z, Qt.ControlModifier); pump()
        self.assertEqual(bytes(w.store.save.data), before)
        QTest.keyClick(w, Qt.Key_Z, Qt.ControlModifier | Qt.ShiftModifier); pump()
        self.assertEqual(bytes(w.store.save.data), after)
        w.store.load(self.path); w.show_hub(); pump()

    def test_21_background_save_locks_edits_and_reports_failure(self):
        w = self.win
        w.store.load(self.path)
        w.store.edit(lambda save: save.set_value(sd.TICKETS, (save.value(sd.TICKETS) + 1) % 99), "Tickets")
        started, release = threading.Event(), threading.Event()
        original = sd.SaveFile.save
        callbacks = []

        def slow(save):
            started.set()
            if not release.wait(5):
                raise OSError("Test worker timed out")
            return original(save)

        with patch.object(sd.SaveFile, "save", slow):
            w._write(after=lambda: callbacks.append("saved"))
            try:
                for _ in range(100):
                    if started.is_set():
                        break
                    pump(10)
                self.assertTrue(started.is_set())
                self.assertTrue(w.store.busy)
                self.assertFalse(w.isEnabled())
                w.close()
                self.assertTrue(w.isVisible())
                with self.assertRaises(RuntimeError):
                    w.store.edit(lambda save: save.set_value(sd.TICKETS, 1))
                self.assertIsNone(w.store.undo())
            finally:
                release.set()
                for _ in range(500):
                    if not w.store.busy:
                        break
                    pump(10)
        self.assertFalse(w.store.busy)
        self.assertTrue(w.isEnabled())
        self.assertFalse(w.store.dirty)
        self.assertEqual(callbacks, ["saved"])
        w.store.undo(); self.assertTrue(w.store.dirty)
        w.store.redo(); self.assertFalse(w.store.dirty)
        w.store.edit(lambda save: save.set_value(sd.TICKETS, (save.value(sd.TICKETS) + 1) % 99))
        callbacks.clear()
        with patch.object(sd.SaveFile, "save", side_effect=PermissionError("Disk is read-only")):
            w._write(after=lambda: callbacks.append("saved"))
            for _ in range(500):
                if not w.store.busy:
                    break
                pump(10)
        self.assertTrue(w.isEnabled())
        self.assertTrue(w.store.dirty)
        self.assertTrue(w.store.can_undo)
        self.assertEqual(callbacks, [])
        pump(300)
        self.assertEqual(self.overlays()[-1].title, "Save failed")
        self.overlays()[-1].close_overlay(); pump(250)
        w.store.load(self.path); w.show_hub(); pump()

    def test_22_stat_locale_number_and_invalid_text(self):
        from PyQt5.QtCore import QLocale
        w = self.win
        w.open_section("STATS"); pump(300)
        row = w.pages[w.current].scroll.widget().findChildren(smash_ui.StatRow)[0]
        row.edit.validator().setLocale(QLocale.c())
        row.edit.setText("1,000")
        self.assertTrue(row.edit.hasAcceptableInput())
        row.commit()
        self.assertEqual(w.store.save.get(row.off, 4), 1000)
        before = bytes(w.store.save.data)
        row.edit.setText("not a number"); row.commit()
        self.assertEqual(bytes(w.store.save.data), before)
        self.assertEqual(row.edit.text(), "1000")
        w.store.load(self.path); w.show_hub(); pump()

    def test_23_arrow_navigation_and_undo_after_filtered_toggle(self):
        w = self.win
        w.store.load(self.path)
        w.open_section("CHARACTERS"); pump(300)
        page = w.pages[w.current]
        page.search.clear(); page.filter.setCurrentIndex(0)
        page.tiles[0].setFocus(); pump()
        QTest.keyClick(page.tiles[0], Qt.Key_Right); pump()
        self.assertIs(self.app.focusWidget(), page.tiles[1])
        QTest.keyClick(page.tiles[1], Qt.Key_Down); pump()
        self.assertIs(self.app.focusWidget(), page.tiles[1 + page.columns])
        page.set_all(False); pump()
        page.filter.setCurrentIndex(1); pump()
        page.tiles[0].setFocus(); pump()
        QTest.keyClick(page.tiles[0], Qt.Key_Return); pump()
        self.assertTrue(w.store.save.fighter_unlocked(0))
        self.assertNotIn(page.tiles[0], page.visible_tiles)
        QTest.keyClick(self.app.focusWidget(), Qt.Key_Z, Qt.ControlModifier); pump()
        self.assertFalse(w.store.save.fighter_unlocked(0))
        self.assertIn(page.tiles[0], page.visible_tiles)
        page.filter.setCurrentIndex(0)
        w.open_section("ITEMS"); pump(300)
        items = w.pages[w.current]
        items.btns[0].setFocus(); pump()
        QTest.keyClick(items.btns[0], Qt.Key_Right); pump()
        self.assertIs(self.app.focusWidget(), items.btns[1])
        QTest.keyClick(items.btns[1], Qt.Key_Down); pump()
        self.assertIsInstance(self.app.focusWidget(), smash_ui.ItemTile)
        self.assertIsNot(self.app.focusWidget(), items.btns[1])
        w.store.load(self.path); w.show_hub(); pump()

    def test_24_fast_navigation_keeps_modal_focus(self):
        w = self.win
        w.store.load(self.path)
        w.show_hub()
        w.hub.activate("ITEMS")
        QTest.keyClick(self.app.focusWidget(), Qt.Key_Escape)
        pump(250)
        self.assertIsNone(w.current)
        self.assertEqual(self.overlays(), [])
        w.store.edit(lambda save: save.set_value(sd.TICKETS, (save.value(sd.TICKETS) + 1) % 99))
        w.close()
        w.close()
        pump(300)
        self.assertEqual(len(self.overlays()), 1)
        dialog = self.overlays()[0]
        self.assertTrue(dialog.isAncestorOf(self.app.focusWidget()))
        dialog.close_overlay()
        pump(200)
        w.store.load(self.path)

    def test_25_section_shortcuts_and_toolbar_with_text_focus(self):
        w = self.win
        w.store.load(self.path)
        w.open_section("CHARACTERS")
        page = w.pages[w.current]
        page.search.clear()
        page.search.setFocus()
        QTest.keyClicks(page.search, "Peach")
        original = w.store.save.value(sd.TICKETS)
        w.store.edit(lambda save: save.set_value(sd.TICKETS, (original + 1) % 99))
        w.undo_btn.click()
        self.assertEqual(page.search.text(), "Peach")
        self.assertEqual(w.store.save.value(sd.TICKETS), original)
        QTest.keyClick(page.search, Qt.Key_PageDown, Qt.ControlModifier)
        self.assertEqual(smash_ui.SECTIONS[w.current][0], "STATS")
        stats = w.pages[w.current]
        row = stats.scroll.widget().findChildren(smash_ui.StatRow)[0]
        row.edit.setFocus()
        QTest.keyClick(row.edit, Qt.Key_E)
        self.assertEqual(smash_ui.SECTIONS[w.current][0], "BACKUPS")
        w.pad.section_step.emit(-1)
        self.assertEqual(smash_ui.SECTIONS[w.current][0], "STATS")
        overlay = smash_ui.HelpOverlay(w).open()
        pump(300)
        w.pad.section_step.emit(1)
        self.assertEqual(smash_ui.SECTIONS[w.current][0], "STATS")
        overlay.close_overlay()
        pump(200)
        page.search.clear()
        w.show_hub()

    def test_26_conflict_preserves_edits_and_exports_a_new_copy(self):
        w = self.win
        with tempfile.TemporaryDirectory(dir=self.tmp) as directory:
            source = os.path.join(directory, "original.bin")
            dest = os.path.join(directory, "exported.bin")
            shutil.copyfile(self.path, source)
            w.store.load(source)
            w.show_hub()
            original = w.store.save.value(sd.TICKETS)
            value = (original + 1) % 99
            w.store.edit(lambda save: save.set_value(sd.TICKETS, value))
            QTest.keyClick(w.hub, Qt.Key_I, Qt.ControlModifier)
            report = self.overlays()[-1]
            self.assertIsInstance(report, smash_ui.ChangesOverlay)
            details = report.findChild(smash_ui.QTextBrowser).toPlainText()
            self.assertIn(f"Tickets\n{original}\n{value}", details)
            report.close_overlay()
            with open(source, "r+b") as stream:
                old = stream.read(1)[0]
                stream.seek(0)
                stream.write(bytes([old ^ 1]))
            w.save_file()
            self.wait_for_idle()
            conflict = self.overlays()[-1]
            self.assertEqual(conflict.title, "Save changed on disk")
            with patch.object(smash_ui.QFileDialog, "getSaveFileName", return_value=(dest, "")):
                conflict.btns[0].click()
                self.wait_for_idle()
            self.assertTrue(w.store.dirty)
            self.assertTrue(w.store.can_undo)
            self.assertEqual(w.store.save.path, source)
            self.assertEqual(sd.SaveFile(source).value(sd.TICKETS), original)
            self.assertEqual(sd.SaveFile(dest).value(sd.TICKETS), value)
            w.store.load(self.path)
            w.show_hub()

    def test_27_background_open_records_only_success_and_preserves_failed_edits(self):
        w = self.win
        original_preferences = w.preferences
        self.addCleanup(setattr, w, "preferences", original_preferences)
        with tempfile.TemporaryDirectory(dir=self.tmp) as directory:
            w.preferences = QSettings(os.path.join(directory, "prefs.ini"), QSettings.IniFormat)
            good = os.path.join(directory, "copy.bin")
            bad = os.path.join(directory, "missing.bin")
            shutil.copyfile(self.path, good)
            w.store.load(self.path)
            w.show_hub()
            w.store.edit(lambda save: save.set_value(sd.TICKETS, (save.value(sd.TICKETS) + 1) % 99))
            previous = w.store.save
            started, release = threading.Event(), threading.Event()
            read = sd.SaveFile

            def pause_before_loading(path):
                started.set()
                if not release.wait(5):
                    raise OSError("Test worker timed out")
                return read(path)

            with patch.object(sd, "SaveFile", side_effect=pause_before_loading):
                w.load_path(bad, remember=True)
                try:
                    self.assertTrue(started.wait(2))
                    self.assertTrue(w.store.busy)
                    self.assertIs(w.store.save, previous)
                    self.assertTrue(w.isVisible())
                    self.assertFalse(w.isEnabled())
                finally:
                    release.set()
                    self.wait_for_idle()
            self.assertEqual(self.overlays()[-1].title, "Could not open save")
            self.assertIs(w.store.save, previous)
            self.assertTrue(w.store.can_undo)
            self.assertEqual(w.recent_files(), [])
            self.overlays()[-1].close_overlay()
            w.load_path(good, remember=True)
            self.wait_for_idle()
            self.assertEqual(w.recent_files(), [good])
            self.assertFalse(w.store.can_undo)
            QTest.keyClick(w.hub, Qt.Key_F, Qt.AltModifier)
            files = self.overlays()[-1]
            self.assertIsInstance(files, smash_ui.FilesOverlay)
            self.assertEqual(files.selected_path(), good)
            pump()
            QTest.keyClick(files.recent, Qt.Key_Right)
            self.assertIs(self.app.focusWidget(), files.buttons[1])
            QTest.keyClick(files.buttons[1], Qt.Key_Up)
            self.assertIs(self.app.focusWidget(), files.recent)
            files.close_overlay()
            pump(200)
            w.store.load(self.path)
            w.show_hub()

    def test_export_warns_when_the_copy_exists_but_directory_sync_failed(self):
        w = self.win
        w.store.load(self.path)
        w.show_hub()
        with tempfile.TemporaryDirectory(dir=self.tmp) as directory:
            dest = os.path.join(directory, "exported.bin")
            with (
                patch.object(smash_ui.QFileDialog, "getSaveFileName", return_value=(dest, "")),
                patch.object(sd, "_sync_directory", side_effect=OSError("sync failed")),
            ):
                w.export_copy()
                self.wait_for_idle()
            warning = self.overlays()[-1]
            self.addCleanup(warning.close_overlay)
            self.assertEqual(warning.title, "Copy created with a warning")
            self.assertEqual(sd.SaveFile(dest).clean, w.store.save.clean)

    def test_28_filter_records_and_fighters_without_changing_save(self):
        w = self.win
        w.store.load(self.path)
        w.open_section("STATS")
        stats = w.pages[w.current]
        stats.show_cat("Combined")
        stats.search.setText("POWER-ON")
        self.assertEqual([row.label for row in stats.rows if not row.isHidden()], ["Power-On Count"])
        stats.search.setText("Impossible search")
        self.assertFalse(stats.no_matches.isHidden())
        stats.search.clear()
        w.open_section("CHARACTERS")
        fighters = w.pages[w.current]
        fighters.filter.setCurrentIndex(0)
        fighters.search.setText("Pokemon Trainer")
        self.assertEqual([tile.title for tile in fighters.visible_tiles], ["Pokémon Trainer"])
        fighters.search.clear()
        fighters.filter.setCurrentIndex(3)
        self.assertEqual(fighters.visible_tiles, [])
        fighters.toggle(0)
        self.assertEqual(fighters.visible_tiles, [fighters.tiles[0]])
        w.store.undo()
        self.assertEqual(fighters.visible_tiles, [])
        self.assertFalse(w.store.dirty)
        fighters.filter.setCurrentIndex(0)
        w.show_hub()

    def test_29_number_overlay_requires_input_for_legacy_outlier(self):
        w = self.win
        w.store.load(self.path)
        w.show_hub()
        picked = []
        dialog = smash_ui.NumberOverlay(w, sd.TICKETS, 255, picked.append).open()
        dialog.accept()
        self.assertEqual(picked, [])
        dialog = smash_ui.NumberOverlay(w, sd.TICKETS, 255, picked.append).open()
        dialog.set_to(sd.TICKETS.maximum)
        dialog.accept()
        self.assertEqual(picked, [sd.TICKETS.maximum])
        pump(280)

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
        self.assertFalse(smash_ui.pixmap("ui/app.svg").isNull())
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
