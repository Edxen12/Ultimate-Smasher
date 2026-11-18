"""Tests for save_data. Uses a copy of a real save if SMASH_TEST_SAVE is set,
otherwise a synthetic zero-filled file of the right size."""
import itertools
import os
import shutil
import tempfile
import unittest

import save_data as sd


class SaveDataTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        slot0 = os.path.join(self.tmp, "save", "0", "save_data")
        slot1 = os.path.join(self.tmp, "save", "1", "save_data")
        os.makedirs(slot0)
        os.makedirs(slot1)
        self.path = os.path.join(slot0, "system_data.bin")
        self.other = os.path.join(slot1, "system_data.bin")
        src = os.environ.get("SMASH_TEST_SAVE")
        for p in (self.path, self.other):
            if src:
                shutil.copy(src, p)
            else:
                with open(p, "wb") as f:
                    f.write(bytes(sd.SAVE_SIZE))
        self.backups = os.path.join(self.tmp, "backups")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_rejects_wrong_size_or_missing(self):
        bad = os.path.join(self.tmp, "bad.bin")
        with open(bad, "wb") as f:
            f.write(b"\0" * 10)
        with self.assertRaises(sd.InvalidSave):
            sd.SaveFile(bad)
        with self.assertRaises(sd.InvalidSave):
            sd.SaveFile(os.path.join(self.tmp, "missing.bin"))

    def test_roundtrip_fields_and_dirty(self):
        s = sd.SaveFile(self.path)
        self.assertFalse(s.dirty)
        for f in sd.CURRENCIES + sd.ITEMS:
            s.set_value(f, f.maximum)
            self.assertEqual(s.value(f), f.maximum, f.key)
        self.assertTrue(s.dirty)
        s.set_value(sd.HAMMERS, 5000)  # clamped
        self.assertEqual(s.value(sd.HAMMERS), 99)
        s.set_value(sd.GOLD, 1234)
        self.assertEqual(s.get(sd.GOLD_OBTAINED, 4), 1234)
        self.assertEqual(s.get(sd.GOLD_SPENT, 4), 0)

    def test_fields_do_not_overlap(self):
        spans = sorted((f.offset, f.offset + f.size) for f in sd.CURRENCIES + sd.ITEMS)
        for (_, a1), (b0, _) in itertools.pairwise(spans):
            self.assertLessEqual(a1, b0)

    def test_fighters(self):
        s = sd.SaveFile(self.path)
        self.assertEqual(len(sd.FIGHTERS), 71)
        for i in range(71):
            s.set_fighter(i, True)
        self.assertEqual(s.fighters_unlocked(), 71)
        s.set_fighter(70, False)
        self.assertEqual(s.data[0x540170], 0)  # Incineroar slot
        self.assertEqual(s.fighters_unlocked(), 70)

    def test_bulk_unlocks(self):
        s = sd.SaveFile(self.path)
        s.unlock_milestones()
        s.unlock_mii_clothes()
        on, total = s.milestones_progress()
        self.assertEqual(on, total)
        on, total = s.mii_clothes_progress()
        self.assertEqual(on, total)
        self.assertEqual(len(s.data), sd.SAVE_SIZE)

    def test_stats_validate_before_writing(self):
        s = sd.SaveFile(self.path)
        offs = [o for _, o in sd.STATS["Combined"]]
        before = bytes(s.data)
        with self.assertRaises(ValueError):
            s.set_stats({offs[0]: 5, offs[1]: sd.STAT_MAX + 1})
        self.assertEqual(bytes(s.data), before)  # nothing half-written
        s.set_stats({offs[0]: 42})
        self.assertEqual(s.get(offs[0], 4), 42)

    def test_language(self):
        s = sd.SaveFile(self.path)
        s.language = 3
        self.assertEqual(s.language, 3)
        with self.assertRaises(ValueError):
            s.language = 99

    def test_save_backs_up_and_mirrors(self):
        s = sd.SaveFile(self.path)
        original = bytes(s.data)
        s.set_value(sd.TICKETS, 77)
        dest = s.save(self.backups)
        self.assertFalse(s.dirty)
        for p in (self.path, self.other):
            with open(p, "rb") as f:
                self.assertEqual(f.read(), bytes(s.data))
        files = sorted(os.listdir(dest))
        self.assertEqual(files, ["slot0_system_data.bin", "slot1_system_data.bin"])
        with open(os.path.join(dest, files[0]), "rb") as f:
            self.assertEqual(f.read(), original)
        self.assertEqual(sd.SaveFile(self.path).value(sd.TICKETS), 77)
        leftovers = [x for x in os.listdir(os.path.dirname(self.path)) if x.startswith(".smasher-")]
        self.assertEqual(leftovers, [])

    def test_save_keeps_file_permissions(self):
        os.chmod(self.path, 0o644)
        s = sd.SaveFile(self.path)
        s.set_value(sd.TICKETS, 3)
        s.save(self.backups)
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o644)

    def test_backup_listing_and_prune(self):
        for _ in range(4):
            sd.make_backup([self.path], self.backups)
        self.assertEqual(len(sd.list_backups(self.backups)), 4)
        sd.prune_backups(self.backups, keep=2)
        self.assertEqual(len(sd.list_backups(self.backups)), 2)

    def test_restore_bytes(self):
        s = sd.SaveFile(self.path)
        raw = bytearray(s.data)
        raw[0x5506CC] = 9
        s.load_bytes(bytes(raw))
        self.assertTrue(s.dirty)
        self.assertEqual(s.value(sd.TICKETS), 9)
        with self.assertRaises(sd.InvalidSave):
            s.load_bytes(b"x")


if __name__ == "__main__":
    unittest.main()
