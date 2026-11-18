"""Backup UI safety checks in isolated Qt processes and temporary files."""
import os
import subprocess
import sys
import textwrap
import unittest

PRELUDE = """
import os, tempfile
from unittest.mock import patch
from PyQt5.QtCore import QCoreApplication, QEvent, Qt
from PyQt5.QtTest import QTest
import save_data as sd
import smash_ui as ui
tmp = tempfile.TemporaryDirectory()
path = os.path.join(tmp.name, 'system_data.bin')
with open(path, 'wb') as stream:
    stream.write(bytes(sd.SAVE_SIZE))
sd.BACKUP_DIR = os.path.join(tmp.name, 'backups')
app, win = ui.main(['test', path])
def wait_for_idle():
    for _ in range(200):
        if not win.store.busy:
            break
        QTest.qWait(10)
    assert not win.store.busy
wait_for_idle()
win.open_section('BACKUPS')
QTest.qWait(50)
page = win.pages[win.current]
def overlays():
    return [item for item in win.children() if isinstance(item, ui.Overlay) and not item.closing]
def confirm_load():
    page.restore()
    QTest.qWait(20)
    overlays()[-1].btns[0].click()
    wait_for_idle()
"""


class BackupUiTest(unittest.TestCase):
    def run_ui(self, body):
        script = PRELUDE + textwrap.dedent(body) + textwrap.dedent("""
            for overlay in overlays():
                overlay.close_overlay()
            win.force_close = True
            assert win.close()
            win.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            tmp.cleanup()
        """)
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", SMASHER_MUTE="1", SMASHER_REDUCE_MOTION="1")
        result = subprocess.run([sys.executable, "-c", script], env=env, text=True, capture_output=True, timeout=30, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_empty_state_metadata_and_selection(self):
        self.run_ui("""
            assert not page.restore_btn.isEnabled()
            sd.make_backup([path])
            page.refresh()
            assert page.restore_btn.isEnabled()
            chosen = page.list.currentItem().data(Qt.UserRole)
            assert path in page.list.currentItem().toolTip()
            assert '1 file' in page.list.currentItem().text()
            sd.make_backup([path])
            page.refresh()
            assert page.list.currentItem().data(Qt.UserRole) == chosen
        """)

    def test_restore_is_undoable_and_does_not_write_disk(self):
        self.run_ui("""
            sd.make_backup([path])
            win.store.edit(lambda save: save.set_value(sd.TICKETS, 7))
            before = bytes(win.store.save.data)
            page.refresh()
            confirm_load()
            assert win.store.save.value(sd.TICKETS) == 0
            assert win.store.undo_label == 'Restore backup'
            win.store.undo()
            assert bytes(win.store.save.data) == before
            assert sd.SaveFile(path).value(sd.TICKETS) == 0
        """)

    def test_damaged_backup_is_rejected_without_changing_editor(self):
        self.run_ui("""
            sd.make_backup([path])
            page.refresh()
            backup = page.list.currentItem().data(Qt.UserRole)
            with open(backup, 'r+b') as stream:
                stream.seek(900)
                stream.write(b'x')
            before = bytes(win.store.save.data)
            confirm_load()
            assert bytes(win.store.save.data) == before
            assert overlays()[-1].title == 'Backup could not be loaded'
            assert not win.store.can_undo
        """)

    def test_disk_errors_are_reported_without_success(self):
        self.run_ui("""
            with patch.object(sd, 'list_backups', side_effect=PermissionError('denied')):
                with patch.object(win, 'toast') as toast:
                    page.refresh()
                    assert 'COULD' in toast.call_args.args[0]
                    assert toast.call_args.args[1] == 'error'
            assert not page.restore_btn.isEnabled()
            with patch.object(sd, 'make_backup', side_effect=OSError('disk full')):
                with patch.object(win, 'toast') as toast:
                    page.backup_now()
                    for _ in range(100):
                        if not win.store.busy:
                            break
                        QTest.qWait(10)
                    assert not any('BACKUP CREATED' in str(call) for call in toast.call_args_list)
            assert overlays()[-1].title == 'Backup failed'
            overlays()[-1].close_overlay()
            QTest.qWait(50)
            with patch.object(ui.QDesktopServices, 'openUrl', return_value=False):
                page.open_folder()
            assert overlays()[-1].title == 'Folder could not be opened'
        """)

    def test_manual_backup_stays_available_when_retention_fails(self):
        self.run_ui("""
            with patch.object(sd, 'prune_backups', side_effect=PermissionError('denied')):
                page.backup_now()
                for _ in range(100):
                    if not win.store.busy:
                        break
                    QTest.qWait(10)
            assert not win.store.busy
            assert not overlays()
            assert 'BACKUP CREATED' in win.toast_w.text
            assert page.restore_btn.isEnabled()
            assert len(sd.list_backups()) == 1
        """)

    def test_filter_current_source_and_warn_on_foreign_backup(self):
        self.run_ui("""
            foreign = os.path.join(tmp.name, 'another.bin')
            with open(foreign, 'wb') as stream:
                stream.write(bytes(sd.SAVE_SIZE))
            sd.make_backup([path])
            sd.make_backup([foreign])
            page.refresh()
            assert page.list.count() == 2
            foreign_row = next(i for i in range(2) if page.list.item(i).data(Qt.UserRole + 1) == foreign)
            page.list.setCurrentRow(foreign_row)
            page.restore()
            assert 'different save path' in overlays()[-1].findChild(ui.QTextBrowser).toPlainText()
            overlays()[-1].close_overlay()
            page.filter_source.setChecked(True)
            assert page.list.count() == 1
            assert page.list.currentItem().data(Qt.UserRole + 1) == path
            page.list.setFocus()
            QTest.keyClick(page.list, Qt.Key_Right)
            assert app.focusWidget() is page.restore_btn
        """)


if __name__ == "__main__":
    unittest.main()
