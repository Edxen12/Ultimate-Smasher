"""Editor transactions, change summaries and bounded history."""
from dataclasses import dataclass

from PyQt5.QtCore import QObject, pyqtSignal

import save_data as sd


@dataclass(frozen=True)
class Edit:
    label: str
    spans: tuple

    @property
    def size(self):
        return sum(len(before) + len(after) for _, before, after in self.spans)


@dataclass(frozen=True)
class Change:
    section: str
    name: str
    before: str
    after: str


def byte_delta(before, after):
    """Scan blocks in C, then inspect only changed blocks in Python."""
    spans = []
    for offset in range(0, len(before), 4096):
        old, new = before[offset:offset + 4096], after[offset:offset + 4096]
        if old == new:
            continue
        start, end = 0, len(old)
        while old[start] == new[start]:
            start += 1
        while old[end - 1] == new[end - 1]:
            end -= 1
        spans.append((offset + start, old[start:end], bytes(new[start:end])))
    return tuple(spans)


def _number(value):
    return f"{value:,}"


def _language(value):
    return sd.LANGUAGES[value] if value < len(sd.LANGUAGES) else f"Unknown ({value})"


def _fighter(value):
    if value in (0, 1):
        return ("Locked", "Unlocked")[value]
    return f"Locked (flag {value})"


def _other_bytes_changed(before, after, covered):
    end = 0
    for start, stop in sorted(covered):
        if before[end:start] != after[end:start]:
            return True
        end = max(end, stop)
    return before[end:] != after[end:]


class Store(QObject):
    changed = pyqtSignal()
    HISTORY_BYTES = 32 * 1024 * 1024
    HISTORY_COUNT = 100

    def __init__(self):
        super().__init__()
        self.save = None
        self._dirty = False
        self.busy = False
        self.operation = ""
        self._undo, self._redo = [], []

    @property
    def loaded(self):
        return self.save is not None

    @property
    def dirty(self):
        return self._dirty

    @property
    def can_undo(self):
        return bool(self._undo) and not self.busy

    @property
    def can_redo(self):
        return bool(self._redo) and not self.busy

    @property
    def undo_label(self):
        return self._undo[-1].label if self._undo else ""

    @property
    def redo_label(self):
        return self._redo[-1].label if self._redo else ""

    def _emit(self):
        self._dirty = self.loaded and self.save.dirty
        self.changed.emit()

    def load(self, path):
        if self.busy:
            raise RuntimeError("Wait for the disk operation to finish")
        self.install(sd.SaveFile(path))

    def install(self, candidate: sd.SaveFile):
        """Switch to a successfully opened save and reset its editing history."""
        if self.busy:
            raise RuntimeError("Wait for the disk operation to finish")
        self.save = candidate
        self._undo.clear()
        self._redo.clear()
        self._emit()

    def pending_changes(self) -> tuple[Change, ...]:
        """Describe known field changes against the last saved bytes."""
        if not self.loaded or not self.save.dirty:
            return ()

        before, after = self.save.clean, self.save.data
        changes = []
        covered = []

        def numeric(section, name, offset, size, format_value=_number):
            stop = offset + size
            covered.append((offset, stop))
            old, new = before[offset:stop], after[offset:stop]
            if old != new:
                changes.append(Change(section, name, format_value(int.from_bytes(old, "little")),
                                      format_value(int.from_bytes(new, "little"))))

        for field in sd.CURRENCIES:
            numeric("General", field.name, field.offset, field.size)
        numeric("General", "Game language", sd.LANGUAGE_OFFSET, 1, _language)
        for name, ranges in (("Milestones", [sd.MILESTONES]), ("Mii Clothes", sd.MII_CLOTHES)):
            covered.extend(ranges)
            old = b"".join(before[start:stop] for start, stop in ranges)
            new = b"".join(after[start:stop] for start, stop in ranges)
            if old != new:
                total = len(old) * 8
                old_count = sum(byte.bit_count() for byte in old)
                new_count = sum(byte.bit_count() for byte in new)
                added = sum((new_byte & ~old_byte).bit_count() for old_byte, new_byte in zip(old, new))
                removed = sum((old_byte & ~new_byte).bit_count() for old_byte, new_byte in zip(old, new))
                changes.append(Change("General", name, f"{old_count}/{total} flags set",
                                      f"{new_count}/{total} flags set (+{added}, −{removed})"))
        for name, offset in (("Gold earned (record)", sd.GOLD_OBTAINED), ("Gold spent (record)", sd.GOLD_SPENT),
                             ("SP earned (record)", sd.SP_OBTAINED)):
            numeric("General", name, offset, 4)
        for field in sd.ITEMS:
            numeric("Items", field.name, field.offset, field.size)
        for index, (name, _) in enumerate(sd.FIGHTERS):
            numeric("Fighters", name, sd.fighter_offset(index), 1, _fighter)
        for category, stats in sd.STATS.items():
            for name, offset in stats:
                numeric("Stats", f"{category} · {name}", offset, 4)
        if _other_bytes_changed(before, after, covered):
            changes.append(Change("Other", "Data outside the editable fields", "Saved bytes", "Different bytes"))
        return tuple(changes)

    def edit(self, fn, label="Edit save"):
        if not self.loaded or self.busy:
            raise RuntimeError("No editable save is available")
        before = bytes(self.save.data)
        try:
            fn(self.save)
            if len(self.save.data) != len(before):
                raise sd.InvalidSave("An edit changed the file size")
        except BaseException:
            self.save.data = bytearray(before)
            raise
        spans = byte_delta(before, self.save.data)
        if not spans:
            return False
        self._undo.append(Edit(label, spans))
        self._redo.clear()
        total = sum(edit.size for edit in self._undo)
        while len(self._undo) > 1 and (len(self._undo) > self.HISTORY_COUNT or total > self.HISTORY_BYTES):
            total -= self._undo.pop(0).size
        self._emit()
        return True

    def undo(self):
        if not self.can_undo:
            return None
        edit = self._undo.pop()
        for offset, before, _ in edit.spans:
            self.save.data[offset:offset + len(before)] = before
        self._redo.append(edit)
        self._emit()
        return edit.label

    def redo(self):
        if not self.can_redo:
            return None
        edit = self._redo.pop()
        for offset, _, after in edit.spans:
            self.save.data[offset:offset + len(after)] = after
        self._undo.append(edit)
        self._emit()
        return edit.label

    def set_busy(self, busy, operation="Saving"):
        self.busy = busy
        self.operation = operation if busy else ""
        self._emit()

    def write(self):
        dest = self.save.save()
        self._emit()
        return dest
