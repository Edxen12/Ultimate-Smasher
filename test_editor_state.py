import os
import tempfile
import unittest

import save_data as sd
from editor_state import Change, Store


class EditorStateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "system_data.bin")
        with open(self.path, "wb") as f:
            f.write(bytes(sd.SAVE_SIZE))
        self.store = Store()
        self.store.load(self.path)

    def test_transaction_undo_redo_preserves_all_bytes(self):
        s = self.store
        before = bytes(s.save.data)
        s.edit(lambda save: save.set_value(sd.GOLD, 1234), "Gold")
        after = bytes(s.save.data)
        self.assertTrue(s.dirty)
        self.assertEqual(s.undo(), "Gold")
        self.assertEqual(bytes(s.save.data), before)
        self.assertFalse(s.dirty)
        self.assertEqual(s.redo(), "Gold")
        self.assertEqual(bytes(s.save.data), after)
        self.assertTrue(s.dirty)

    def test_bulk_is_one_step_and_new_edit_clears_redo(self):
        s = self.store
        s.edit(lambda save: [save.set_value(f, f.maximum) for f in sd.ITEMS], "Max items")
        self.assertEqual(len(s._undo), 1)
        s.undo()
        s.edit(lambda save: save.set_value(sd.TICKETS, 3))
        self.assertFalse(s.can_redo)

    def test_noop_and_failed_transaction_leave_no_history(self):
        s = self.store
        self.assertFalse(s.edit(lambda save: None))
        before = bytes(s.save.data)

        def fail(save):
            save.set_value(sd.TICKETS, 5)
            raise ValueError("interrupted")
        with self.assertRaises(ValueError):
            s.edit(fail)
        self.assertEqual(bytes(s.save.data), before)
        self.assertFalse(s.dirty)
        self.assertFalse(s.can_undo)

    def test_saved_baseline_survives_history_and_failed_open(self):
        s = self.store
        s.edit(lambda save: save.set_value(sd.TICKETS, 7))
        s.save.save(backup_dir=os.path.join(self.tmp.name, "backups"))
        s._emit()
        self.assertFalse(s.dirty)
        self.assertEqual(s.pending_changes(), ())
        s.undo(); self.assertTrue(s.dirty)
        self.assertEqual(s.pending_changes(), (Change("General", "Tickets", "7", "0"),))
        s.redo(); self.assertFalse(s.dirty)
        self.assertEqual(s.pending_changes(), ())
        with self.assertRaises(sd.InvalidSave):
            s.load(os.path.join(self.tmp.name, "missing"))
        self.assertTrue(s.can_undo)
        s.load(self.path)
        self.assertFalse(s.can_undo)

    def test_busy_blocks_mutation_and_history(self):
        s = self.store
        s.edit(lambda save: save.set_value(sd.TICKETS, 3))
        s.set_busy(True)
        self.assertFalse(s.can_undo)
        with self.assertRaises(RuntimeError):
            s.edit(lambda save: save.set_value(sd.TICKETS, 4))
        with self.assertRaises(RuntimeError):
            s.load(self.path)
        s.set_busy(False)
        self.assertTrue(s.can_undo)

    def test_install_keeps_current_file_during_disk_work_and_clears_history(self):
        s = self.store
        current = s.save
        s.edit(lambda save: save.set_value(sd.TICKETS, 3))
        s.edit(lambda save: save.set_value(sd.TICKETS, 4))
        s.undo()
        candidate = sd.SaveFile(self.path)

        s.set_busy(True)
        with self.assertRaises(RuntimeError):
            s.install(candidate)
        self.assertIs(s.save, current)
        self.assertEqual(s.save.value(sd.TICKETS), 3)

        s.set_busy(False)
        s.install(candidate)
        self.assertIs(s.save, candidate)
        self.assertFalse(s.dirty)
        self.assertFalse(s.can_undo)
        self.assertFalse(s.can_redo)

    def test_change_summary_groups_edits_and_derived_records(self):
        s = self.store
        item = sd.ITEMS[0]
        stat, offset = sd.STATS["Combined"][0]

        def update(save):
            save.set_value(sd.GOLD, 1200)
            save.language = 1
            save.set_value(item, 10)
            save.set_fighter(0, True)
            save.set_stats({offset: 20})

        s.edit(update)
        self.assertEqual(s.pending_changes(), (
            Change("General", "Gold", "0", "1,200"),
            Change("General", "Game language", sd.LANGUAGES[0], sd.LANGUAGES[1]),
            Change("General", "Gold earned (record)", "0", "1,200"),
            Change("Items", item.name, "0", "10"),
            Change("Fighters", sd.FIGHTERS[0][0], "Locked", "Unlocked"),
            Change("Stats", f"Combined · {stat}", "0", "20"),
        ))

    def test_change_summary_detects_different_flags_even_when_totals_match(self):
        with open(self.path, "r+b") as stream:
            stream.seek(sd.MILESTONES[0])
            stream.write(b"\x01")
            stream.seek(sd.MII_CLOTHES[0][0])
            stream.write(b"\x01")
        self.store.load(self.path)

        def update(save):
            save.set(sd.MILESTONES[0], 2)
            save.set(sd.MII_CLOTHES[0][0], 0)
            save.set(sd.MII_CLOTHES[1][0], 1)

        self.store.edit(update)
        self.assertEqual(self.store.pending_changes(), (
            Change("General", "Milestones", "1/384 flags set", "1/384 flags set (+1, −1)"),
            Change("General", "Mii Clothes", "1/176 flags set", "1/176 flags set (+1, −1)"),
        ))

    def test_change_summary_reports_edits_outside_known_fields(self):
        self.assertEqual(Store().pending_changes(), ())
        s = self.store
        backup = bytearray(s.save.clean)
        backup[sd.fighter_offset(0) + 1] = 1
        backup[-1] = 7
        s.edit(lambda save: save.load_bytes(backup))
        self.assertEqual(s.pending_changes(), (
            Change("Other", "Data outside the editable fields", "Saved bytes", "Different bytes"),
        ))
        s.undo()
        self.assertEqual(s.pending_changes(), ())

    def test_history_is_bounded(self):
        s = self.store
        s.HISTORY_COUNT = 3
        for value in range(1, 8):
            s.edit(lambda save, value=value: save.set_value(sd.TICKETS, value))
        self.assertEqual(len(s._undo), 3)
        self.assertLess(sum(edit.size for edit in s._undo), 100)


if __name__ == "__main__":
    unittest.main()
