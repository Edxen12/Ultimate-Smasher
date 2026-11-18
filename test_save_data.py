"""Tests for save_data. Uses a copy of a real save if SMASH_TEST_SAVE is set,
otherwise a synthetic zero-filled file of the right size."""
import itertools
import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

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

    def test_export_preserves_edits_original_and_baseline_after_disk_conflict(self):
        s = sd.SaveFile(self.path)
        original = s.clean
        s.set_value(sd.TICKETS, (s.value(sd.TICKETS) + 1) % 99)
        with open(self.path, "r+b") as stream:
            stream.write(b"external")
        external = sd._read_disk(self.path)
        with self.assertRaises(sd.SaveConflict):
            s.save(self.backups)
        dest = os.path.join(self.tmp, "edited.bin")
        self.assertEqual(s.export_copy(dest), dest)
        self.assertEqual(sd._read_disk(dest), bytes(s.data))
        self.assertEqual(sd._read_disk(self.path), external)
        self.assertEqual(sd._read_disk(self.other), original)
        self.assertEqual(s.clean, original)
        self.assertEqual(s.path, self.path)
        self.assertTrue(s.dirty)
        self.assertFalse(os.path.exists(self.backups))

    def test_export_refuses_destination_created_during_publication(self):
        s = sd.SaveFile(self.path)
        dest = os.path.join(self.tmp, "edited.bin")
        publish = sd._publish_new

        def create_competing_file(temporary, path):
            with open(path, "xb") as stream:
                stream.write(b"competing file")
            publish(temporary, path)

        with patch.object(sd, "_publish_new", side_effect=create_competing_file), self.assertRaises(FileExistsError):
            s.export_copy(dest)
        with open(dest, "rb") as stream:
            self.assertEqual(stream.read(), b"competing file")
        self.assertFalse(any(name.startswith(".smasher-") for name in os.listdir(self.tmp)))

    def test_export_uses_safe_link_when_renameat2_is_unavailable(self):
        s = sd.SaveFile(self.path)
        dest = os.path.join(self.tmp, "edited.bin")
        with patch.object(sd.ctypes, "CDLL", return_value=object()):
            self.assertEqual(s.export_copy(dest), dest)
            with self.assertRaises(FileExistsError):
                s.export_copy(dest)
        self.assertEqual(sd._read_disk(dest), bytes(s.data))
        self.assertFalse(any(name.startswith(".smasher-") for name in os.listdir(self.tmp)))

    def test_export_reports_copy_path_when_directory_sync_fails(self):
        s = sd.SaveFile(self.path)
        dest = os.path.join(self.tmp, "edited.bin")
        with (
            patch.object(sd, "_sync_directory", side_effect=OSError("sync failed")),
            self.assertRaisesRegex(sd.CopyPublishedError, "copy was created") as error,
        ):
            s.export_copy(dest)
        self.assertEqual(error.exception.filename, dest)
        self.assertEqual(sd._read_disk(dest), bytes(s.data))

    def test_export_rejects_existing_names_and_missing_live_slots(self):
        s = sd.SaveFile(self.path)
        original = sd._read_disk(self.path)
        dest = os.path.join(self.tmp, "edited.bin")
        dangling = os.path.join(self.tmp, "missing.bin")
        os.symlink(dangling, dest)
        with self.assertRaises(FileExistsError):
            s.export_copy(dest)
        self.assertTrue(os.path.islink(dest))
        self.assertFalse(os.path.exists(dangling))
        with self.assertRaises(FileExistsError):
            s.export_copy(self.path)
        self.assertEqual(sd._read_disk(self.path), original)
        os.unlink(self.other)
        with self.assertRaises(FileExistsError):
            s.export_copy(self.other)
        self.assertFalse(os.path.exists(self.other))

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
        files = sorted(x for x in os.listdir(dest) if x.endswith("system_data.bin"))
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

    def test_read_permission_and_truncation_are_invalid_save(self):
        with patch("builtins.open", side_effect=PermissionError("permission denied")), self.assertRaises(sd.InvalidSave):
            sd.SaveFile(self.path)
        with patch.object(sd, "_read_disk", return_value=b"short"), self.assertRaises(sd.InvalidSave):
            sd.SaveFile(self.path)

    def test_invalid_offsets_and_fighter_indices_preserve_bytes(self):
        s = sd.SaveFile(self.path)
        before = bytes(s.data)
        for index in (-1, len(sd.FIGHTERS), "Mario"):
            with self.assertRaises(ValueError):
                s.set_fighter(index, True)
        for off, size in ((-1, 1), (sd.SAVE_SIZE, 1), (sd.SAVE_SIZE - 1, 4), (0, 3)):
            with self.assertRaises(ValueError):
                s.set(off, 1, size)
            with self.assertRaises(ValueError):
                s.get(off, size)
        self.assertEqual(bytes(s.data), before)

    def test_stats_unknown_destination_does_not_partially_write(self):
        s = sd.SaveFile(self.path)
        before = bytes(s.data)
        off = sd.STATS["Combined"][0][1]
        with self.assertRaises(ValueError):
            s.set_stats({off: 42, 0: 5})
        self.assertEqual(bytes(s.data), before)

    def test_roundtrip_preserves_every_unknown_byte(self):
        original = (bytes(range(256)) * (sd.SAVE_SIZE // 256 + 1))[:sd.SAVE_SIZE]
        for path in (self.path, self.other):
            with open(path, "wb") as stream:
                stream.write(original)
        s = sd.SaveFile(self.path)
        s.save(self.backups)
        with open(self.path, "rb") as stream:
            self.assertEqual(stream.read(), original)
        s.set_value(sd.TICKETS, 23)
        expected = bytearray(original)
        expected[sd.TICKETS.offset] = 23
        s.save(self.backups)
        for path in (self.path, self.other):
            with open(path, "rb") as stream:
                self.assertEqual(stream.read(), bytes(expected))

    def test_save_rejects_external_changes_in_either_slot(self):
        for changed_path in (self.path, self.other):
            s = sd.SaveFile(self.path)
            s.set_value(sd.TICKETS, 29)
            with open(changed_path, "r+b") as stream:
                stream.seek(123)
                stream.write(b"external")
            with open(changed_path, "rb") as stream:
                external = stream.read()
            with self.assertRaises(sd.SaveConflict):
                s.save(self.backups)
            self.assertTrue(s.dirty)
            with open(changed_path, "rb") as stream:
                self.assertEqual(stream.read(), external)
            # Reset to the original snapshot for the next independent conflict.
            with open(changed_path, "wb") as stream:
                stream.write(s._disk_snapshots[changed_path])
        self.assertFalse(os.path.exists(self.backups))

    def test_distinct_mirror_baseline_is_supported(self):
        with open(self.other, "r+b") as stream:
            stream.seek(123); stream.write(b"different slot")
        s = sd.SaveFile(self.path)
        s.set_value(sd.TICKETS, 27)
        s.save(self.backups)
        with open(self.other, "rb") as stream:
            self.assertEqual(stream.read(), bytes(s.data))

    def test_backup_metadata_and_hidden_staging(self):
        dest = sd.make_backup([self.path, self.other], self.backups)
        detail = sd.backup_details(dest)
        self.assertEqual(len(detail["files"]), 2)
        self.assertEqual(detail["files"][0]["source"], self.path)
        self.assertEqual(detail["files"][0]["size"], sd.SAVE_SIZE)
        self.assertEqual(len(detail["files"][0]["sha256"]), 64)
        stage = os.path.join(self.backups, ".smasher-backup-incomplete")
        os.makedirs(stage)
        shutil.copy2(self.path, os.path.join(stage, "system_data.bin"))
        self.assertEqual(len(sd.list_backups(self.backups)), 1)

    def test_failed_backup_never_publishes_or_prunes(self):
        dest = sd.make_backup([self.path], self.backups)
        copy = sd.shutil.copy2
        count = 0

        def fail_second(source, target):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError("disk full")
            return copy(source, target)
        with patch.object(sd.shutil, "copy2", side_effect=fail_second), patch.object(sd, "prune_backups") as prune:
            with self.assertRaises(OSError):
                sd.make_backup([self.path, self.other], self.backups)
            prune.assert_not_called()
        self.assertEqual([d for d, _, _ in sd.list_backups(self.backups)], [dest])
        self.assertEqual(len(os.listdir(self.backups)), 1)

    def test_second_slot_failure_rolls_back_and_keeps_backup(self):
        s = sd.SaveFile(self.path)
        original = bytes(s.data)
        s.set_value(sd.TICKETS, 19)
        atomic_write = sd._atomic_write

        def fail_mirror(path, payload, **kwargs):
            if path == self.other:
                raise PermissionError("mirror is read only")
            atomic_write(path, payload, **kwargs)
        with patch.object(sd, "_atomic_write", side_effect=fail_mirror), patch.object(sd, "prune_backups") as prune:
            with self.assertRaisesRegex(OSError, "Original files restored.*Backup:"):
                s.save(self.backups)
            prune.assert_not_called()
        self.assertTrue(s.dirty)
        self.assertEqual(s.clean, original)
        for path in (self.path, self.other):
            with open(path, "rb") as stream:
                self.assertEqual(stream.read(), original)
        self.assertEqual(len(sd.list_backups(self.backups)), 1)

    def test_rollback_failure_is_explicit_and_remains_dirty(self):
        s = sd.SaveFile(self.path)
        s.set_value(sd.TICKETS, 18)
        atomic_write = sd._atomic_write
        calls = 0

        def fail_after_first(path, payload, **kwargs):
            nonlocal calls
            calls += 1
            if calls > 1:
                raise OSError("disk disconnected")
            atomic_write(path, payload, **kwargs)
        with patch.object(sd, "_atomic_write", side_effect=fail_after_first), self.assertRaisesRegex(OSError, "Recovery incomplete.*Backup:"):
            s.save(self.backups)
        self.assertTrue(s.dirty)
        self.assertEqual(len(sd.list_backups(self.backups)), 1)

    def test_atomic_write_failure_keeps_original_and_closes_fd(self):
        with open(self.path, "rb") as stream:
            original = stream.read()
        descriptors = len(os.listdir("/proc/self/fd"))
        with patch.object(sd.os, "fchmod", side_effect=PermissionError("permission denied")), self.assertRaises(PermissionError):
            sd._atomic_write(self.path, b"new data")
        self.assertEqual(len(os.listdir("/proc/self/fd")), descriptors)
        with open(self.path, "rb") as stream:
            self.assertEqual(stream.read(), original)
        self.assertFalse(any(name.startswith(".smasher-") for name in os.listdir(os.path.dirname(self.path))))

    def test_retention_failure_does_not_turn_completed_save_into_failure(self):
        s = sd.SaveFile(self.path)
        s.set_value(sd.TICKETS, 17)
        with patch.object(sd, "prune_backups", side_effect=PermissionError("old backup denied")):
            dest = s.save(self.backups)
        self.assertFalse(s.dirty)
        self.assertTrue(os.path.isdir(dest))
        self.assertIn("could not be pruned", s.backup_warning)

    def test_change_during_backup_is_not_overwritten(self):
        s = sd.SaveFile(self.path)
        s.set_value(sd.TICKETS, 16)
        make_backup = sd.make_backup

        def backup_then_external_write(*args, **kwargs):
            dest = make_backup(*args, **kwargs)
            with open(self.path, "r+b") as stream:
                stream.seek(123); stream.write(b"external")
            return dest
        with patch.object(sd, "make_backup", side_effect=backup_then_external_write), self.assertRaises(sd.SaveConflict):
            s.save(self.backups)
        with open(self.path, "rb") as stream:
            self.assertEqual(stream.read()[123:131], b"external")
        self.assertTrue(s.dirty)
        self.assertEqual(len(sd.list_backups(self.backups)), 1)

    def test_failure_after_replace_rolls_back_failed_target_too(self):
        s = sd.SaveFile(self.path)
        original = bytes(s.data)
        s.set_value(sd.TICKETS, 15)
        atomic_write = sd._atomic_write
        calls = 0

        def write_then_fail(path, payload, **kwargs):
            nonlocal calls
            calls += 1
            atomic_write(path, payload, **kwargs)
            if calls == 1:
                raise OSError("directory sync failed after replace")
        with patch.object(sd, "_atomic_write", side_effect=write_then_fail), self.assertRaisesRegex(OSError, "Original files restored"):
            s.save(self.backups)
        with open(self.path, "rb") as stream:
            self.assertEqual(stream.read(), original)
        self.assertTrue(s.dirty)

    def test_failed_backup_never_changes_save_files(self):
        s = sd.SaveFile(self.path)
        original = bytes(s.data)
        s.set_value(sd.TICKETS, 14)
        with patch.object(sd.shutil, "copy2", side_effect=OSError("disk full")), self.assertRaises(OSError):
            s.save(self.backups)
        for path in (self.path, self.other):
            with open(path, "rb") as stream:
                self.assertEqual(stream.read(), original)
        self.assertTrue(s.dirty)
        self.assertEqual(sd.list_backups(self.backups), [])

    def test_late_mirror_change_is_preserved_and_first_slot_is_rolled_back(self):
        s = sd.SaveFile(self.path)
        original = bytes(s.data)
        s.set_value(sd.TICKETS, 31)
        atomic_write = sd._atomic_write

        def write_then_change_mirror(path, payload, **kwargs):
            atomic_write(path, payload, **kwargs)
            if path == self.path and payload != original:
                with open(self.other, "r+b") as stream:
                    stream.seek(123)
                    stream.write(b"external")

        with (patch.object(sd, "_atomic_write", side_effect=write_then_change_mirror),
              self.assertRaisesRegex(sd.SaveConflict, "Editor writes rolled back")):
            s.save(self.backups)
        self.assertTrue(s.dirty)
        self.assertEqual(sd._read_disk(self.path), original)
        self.assertEqual(sd._read_disk(self.other)[123:131], b"external")

    def test_first_slot_changed_after_write_is_not_overwritten_by_recovery(self):
        s = sd.SaveFile(self.path)
        original = bytes(s.data)
        s.set_value(sd.TICKETS, 32)
        atomic_write = sd._atomic_write

        def write_then_change_first(path, payload, **kwargs):
            atomic_write(path, payload, **kwargs)
            if path == self.other and payload != original:
                with open(self.path, "r+b") as stream:
                    stream.seek(123)
                    stream.write(b"external")

        with (patch.object(sd, "_atomic_write", side_effect=write_then_change_first),
              self.assertRaisesRegex(sd.SaveConflict, "Recovery incomplete")):
            s.save(self.backups)
        self.assertTrue(s.dirty)
        self.assertEqual(sd._read_disk(self.path)[123:131], b"external")
        self.assertEqual(sd._read_disk(self.other), original)

    def test_backup_prefers_the_slot_used_as_primary(self):
        with open(self.other, "r+b") as stream:
            stream.write(b"slot1")
        dest = sd.make_backup([self.other, self.path], self.backups)
        _, restore_path, _ = sd.list_backups(self.backups)[0]
        self.assertEqual(restore_path, os.path.join(dest, "slot1_system_data.bin"))
        self.assertTrue(sd.read_backup(restore_path).startswith(b"slot1"))

    def test_bad_metadata_cannot_bypass_digest_check(self):
        dest = sd.make_backup([self.path], self.backups)
        _, restore_path, _ = sd.list_backups(self.backups)[0]
        metadata = os.path.join(dest, "metadata.json")
        with open(metadata, "w", encoding="utf-8") as stream:
            stream.write("{broken")
        with self.assertRaisesRegex(sd.InvalidSave, "metadata is damaged"):
            sd.read_backup(restore_path)
        with open(metadata, "w", encoding="utf-8") as stream:
            json.dump({"files": []}, stream)
        with self.assertRaisesRegex(sd.InvalidSave, "recorded size or SHA-256"):
            sd.read_backup(restore_path)
        os.unlink(metadata)
        self.assertEqual(sd.read_backup(restore_path), sd._read_disk(self.path))

    def test_manual_backup_rejects_truncated_slot_without_publishing(self):
        os.truncate(self.other, 2)
        with self.assertRaisesRegex(sd.InvalidSave, "unsupported save size"):
            sd.make_backup([self.path, self.other], self.backups)
        self.assertEqual(sd.list_backups(self.backups), [])

    def test_save_through_symlink_updates_the_target_and_keeps_the_link(self):
        link = os.path.join(self.tmp, "alias.bin")
        os.symlink(self.path, link)
        s = sd.SaveFile(link)
        s.set_value(sd.TICKETS, 33)
        s.save(self.backups)
        self.assertTrue(os.path.islink(link))
        self.assertEqual(sd.SaveFile(self.path).value(sd.TICKETS), 33)
        self.assertEqual(sd.SaveFile(self.other).value(sd.TICKETS), 33)

    def test_retention_skips_unmanaged_folders(self):
        dest = sd.make_backup([self.path], self.backups)
        user_folder = os.path.join(self.backups, "manual")
        os.makedirs(user_folder)
        shutil.copy2(self.path, os.path.join(user_folder, "system_data.bin"))
        sd.prune_backups(self.backups, keep=0)
        self.assertFalse(os.path.exists(dest))
        self.assertTrue(os.path.isdir(user_folder))


class DefaultSavePathTest(unittest.TestCase):
    def test_prefers_historical_then_legacy_and_native_locations(self):
        with tempfile.TemporaryDirectory() as home:
            suffix = "Ryujinx/bis/user/save/0000000000000001/0/save_data/system_data.bin"
            historical = os.path.join(home, ".var/app/io.github.ryubing.Ryujinx/config", suffix)
            legacy = os.path.join(home, ".var/app/org.ryujinx.Ryujinx/config", suffix)
            config = os.path.join(home, "custom-config")
            native = os.path.join(config, suffix)
            with (
                patch.dict(os.environ, {"HOME": home, "XDG_CONFIG_HOME": config}),
                patch.object(sd, "RYUJINX_SAVE", historical),
            ):
                for path in (historical, legacy, native):
                    os.makedirs(os.path.dirname(path))
                    with open(path, "wb") as stream:
                        stream.truncate(sd.SAVE_SIZE)
                self.assertEqual(sd.default_save_path(), historical)
                os.truncate(historical, 1)
                self.assertEqual(sd.default_save_path(), legacy)
                os.truncate(legacy, 1)
                self.assertEqual(sd.default_save_path(), native)

    def test_ignores_slot_one_and_relative_xdg_config(self):
        with tempfile.TemporaryDirectory() as home:
            root = os.path.join(home, ".config/Ryujinx/bis/user/save/0000000000000001")
            primary, mirror = (os.path.join(root, str(slot), "save_data/system_data.bin") for slot in (0, 1))
            os.makedirs(os.path.dirname(mirror))
            with open(mirror, "wb") as stream:
                stream.truncate(sd.SAVE_SIZE)
            with (
                patch.dict(os.environ, {"HOME": home, "XDG_CONFIG_HOME": "relative"}),
                patch.object(sd, "RYUJINX_SAVE", os.path.join(home, "missing.bin")),
            ):
                self.assertEqual(sd.default_save_path(), "")
                os.makedirs(os.path.dirname(primary))
                os.rename(mirror, primary)
                self.assertEqual(sd.default_save_path(), primary)


if __name__ == "__main__":
    unittest.main()
