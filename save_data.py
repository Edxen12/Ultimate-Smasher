"""Smash Bros. Ultimate system_data.bin model (no GUI code).

All offsets come from the original Ultimate Smasher (Ret-HZ, 2019); the fighter
table offsets were corrected locally (8-byte slots from 0x53FF40, official order).
"""
import ctypes
import errno
import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
import struct
import tempfile
import time
from contextlib import contextmanager, suppress
from dataclasses import dataclass

SAVE_SIZE = 5982968
_RYUJINX_PRIMARY_SAVE = "Ryujinx/bis/user/save/0000000000000001/0/save_data/system_data.bin"
RYUJINX_SAVE = os.path.join(
    os.path.expanduser("~/.var/app/io.github.ryubing.Ryujinx/config"), _RYUJINX_PRIMARY_SAVE)
BACKUP_DIR = os.path.expanduser("~/Games/Switch/smash-save-backups")
BACKUP_KEEP = 20
_BACKUP_NAME = re.compile(r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}(?:_\d+)?")
_BACKUP_FILES = {"system_data.bin", "slot0_system_data.bin", "slot1_system_data.bin"}
_UNCHECKED = object()
_AT_FDCWD = -100
_RENAME_NOREPLACE = 1

FMT = {1: "<B", 2: "<H", 4: "<I"}


class InvalidSave(Exception):
    pass


class SaveConflict(OSError):
    """The files on disk no longer match the versions opened by this editor."""


class CopyPublishedError(OSError):
    """An exported copy exists, but cleanup or directory synchronization failed."""


@dataclass(frozen=True)
class Field:
    key: str
    name: str
    offset: int
    size: int          # bytes: 1, 2 or 4
    maximum: int
    step: int = 1
    glyph: str = ""    # Font Awesome glyph
    desc: str = ""


# --- currencies -------------------------------------------------------------
GOLD = Field("gold", "Gold", 0x5506DC, 4, 9_999_999, 10_000, glyph="", desc="Gold for the shops")
SP = Field("sp", "SP", 0x4831E4, 4, 9_999_999, 10_000, glyph="SP", desc="Skill points for the Skill Tree")
HAMMERS = Field("hammers", "Hammers", 0x555E5C, 1, 99, 10, glyph="", desc="Hammers to open chests")
TICKETS = Field("tickets", "Tickets", 0x5506CC, 1, 99, 10, glyph="", desc="Classic Mode tickets")
CURRENCIES = [GOLD, SP, HAMMERS, TICKETS]

GOLD_OBTAINED, GOLD_SPENT, SP_OBTAINED = 0x540290, 0x540294, 0x540298

# --- items ------------------------------------------------------------------
def _item(key, name, off, size, maximum, desc):
    return Field(key, name, off, size, maximum, 10, desc=desc)


ITEMS = [
    _item("snack_s", "Snack (S)", 0x4831CE, 2, 999, "Small snacks: level up spirits"),
    _item("snack_m", "Snack (M)", 0x4831D0, 2, 999, "Medium snacks: level up spirits"),
    _item("snack_l", "Snack (L)", 0x4831D2, 2, 999, "Large snacks: level up spirits"),
    _item("shuffle_all", "Shuffle All", 0x4831C0, 1, 99, "Spirit Board: reshuffles every spirit"),
    _item("all_primaries", "All Primaries", 0x4831C1, 1, 99, "Spirit Board: only primary spirits"),
    _item("all_supports", "All Supports", 0x4831C2, 1, 99, "Spirit Board: only support spirits"),
    _item("filler", "Filler", 0x4831C3, 1, 99, "Spirit Board: fills empty slots"),
    _item("rematch", "Rematch", 0x4831C4, 1, 99, "Spirit Board: retry a lost battle"),
    _item("damage50", "Damage 50%", 0x4831C6, 1, 99, "Start the enemy at 50% damage"),
    _item("slow_fs", "Slow FS Charging", 0x4831C7, 1, 99, "Enemy Final Smash meter charges slower"),
    _item("weaken_minions", "Weaken Minions", 0x4831C8, 1, 99, "Enemy minions are weaker"),
    _item("health_drain", "Health Drain", 0x4831C9, 1, 99, "Enemy loses HP over time"),
    _item("disable_items", "Disable Items", 0x4831CA, 1, 99, "No items for the enemy"),
    _item("shield_spacer", "Shield Spacer", 0x4831CB, 1, 99, "Spirit Board: protects the shield"),
    _item("sluggish_shield", "Sluggish Shield", 0x4831CC, 1, 99, "Enemy shield moves slower"),
]

# --- language ---------------------------------------------------------------
LANGUAGE_OFFSET = 0x3C6098
LANGUAGES = ["日本語", "English", "Français", "Español", "Deutsch", "Italiano",
             "Nederlands", "Русский", "简体中文", "繁體中文", "한국어"]

# --- bulk unlocks -----------------------------------------------------------
MILESTONES = (0x555BB8, 0x555BE8)
MII_CLOTHES = [(0x20, 0x2A), (0x54, 0x60)]

# --- fighters (8-byte slots, byte 0 = unlocked) ----------------------------
FIGHTER_FIRST = 0x53FF40
FIGHTERS = [
    ("Mario", "mario"), ("Donkey Kong", "dk"), ("Link", "link"), ("Samus", "samus"),
    ("Dark Samus", "darksamus"), ("Yoshi", "yoshi"), ("Kirby", "kirby"), ("Fox", "fox"),
    ("Pikachu", "pikachu"), ("Luigi", "luigi"), ("Ness", "ness"), ("Captain Falcon", "captainfalcon"),
    ("Jigglypuff", "jigglypuff"), ("Peach", "peach"), ("Daisy", "daisy"), ("Bowser", "bowser"),
    ("Ice Climbers", "iceclimbers"), ("Sheik", "sheik"), ("Zelda", "zelda"), ("Dr. Mario", "drmario"),
    ("Pichu", "pichu"), ("Falco", "falco"), ("Marth", "marth"), ("Lucina", "lucina"),
    ("Young Link", "younglink"), ("Ganondorf", "ganondorf"), ("Mewtwo", "mewtwo"), ("Roy", "roy"),
    ("Chrom", "chrom"), ("Mr. Game & Watch", "mrgameandwatch"), ("Meta Knight", "metaknight"), ("Pit", "pit"),
    ("Dark Pit", "darkpit"), ("Zero Suit Samus", "zerosuitsamus"), ("Wario", "wario"), ("Snake", "snake"),
    ("Ike", "ike"), ("Pokémon Trainer", "pokemontrainer"), ("Diddy Kong", "diddykong"), ("Lucas", "lucas"),
    ("Sonic", "sonic"), ("King Dedede", "kingdedede"), ("Olimar", "olimar"), ("Lucario", "lucario"),
    ("R.O.B.", "rob"), ("Toon Link", "toonlink"), ("Wolf", "wolf"), ("Villager", "villager"),
    ("Mega Man", "megaman"), ("Wii Fit Trainer", "wiifittrainer"), ("Rosalina & Luma", "rosalinaandluma"),
    ("Little Mac", "littlemac"), ("Greninja", "greninja"), ("Palutena", "palutena"), ("PAC-MAN", "pacman"),
    ("Robin", "robin"), ("Shulk", "shulk"), ("Bowser Jr.", "bowserjr"), ("Duck Hunt Duo", "duckhuntduo"),
    ("Ryu", "ryu"), ("Ken", "ken"), ("Cloud", "cloud"), ("Corrin", "corrin"), ("Bayonetta", "bayonetta"),
    ("Inkling", "inkling"), ("Ridley", "ridley"), ("Simon", "simon"), ("Richter", "richter"),
    ("King K. Rool", "kingkrool"), ("Isabelle", "isabelle"), ("Incineroar", "incineroar"),
]


def fighter_offset(i):
    if not isinstance(i, int) or not 0 <= i < len(FIGHTERS):
        raise ValueError("Fighter index is outside the supported roster")
    return FIGHTER_FIRST + 8 * i


# --- stats (u32 each) -------------------------------------------------------
STAT_MAX = 999_999_999
STATS = {
    "Combined": [
        ("Power-On Count", 0x540258), ("Smash Bros. Powered Time Count", 0x54025C),
        ("Play Time (seconds)", 0x540260), ("Local Wireless Battles Fought", 0x540264),
        ("Time Battles Fought", 0x540268), ("Stock Battles Fought", 0x54026C),
        ("Stamina Battles Fought", 0x540270), ("Battles with 5+ People", 0x540274),
        ("Battles with 8 People", 0x540278), ("Vs. Play Contestants", 0x54027C),
        ("Battles Cut Short", 0x540280), ("Total Damage", 0x540284),
        ("KOs", 0x540288), ("Self-Destructs", 0x54028C)],
    "Smash": [
        ("Smash Play Time (seconds)", 0x54029C), ("Collective Smash Play Time (seconds)", 0x5402A0),
        ("Standard Smash Battles", 0x5402A4), ("Squad Strike Battles", 0x5402A8),
        ("Custom Smash Battles", 0x5402AC), ("Super Sudden Death Battles", 0x5402B0),
        ("Smashdown Battles", 0x5402B4), ("Tourney Battles", 0x5402B8)],
    "Spirits": [
        ("Spirits Summoned", 0x5402C0), ("Spirits Dismissed", 0x5402C4),
        ("Spirits Enhanced", 0x5402C8), ("Lv. 99 Spirits", 0x5402CC),
        ("Spirit Board Battles Won", 0x5402D0), ("Adventure Wins", 0x5402D4),
        ("Times Adventure Completed", 0x5402D8), ("Styles Mastered in the Dojo", 0x5402DC),
        ("Gym Training Time (seconds)", 0x5402E0), ("Spirit Exploration Time (seconds)", 0x5402E4)],
    "Games & More": [
        ("Classic Mode Clears", 0x5402E8), ("Bonus Game High Score", 0x5402F0),
        ("Credits High Score", 0x5402F4), ("Mii Fighters Customized", 0x5402FC)],
    "Vault": [
        ("Snapshots Taken", 0x54030C), ("Replays Recorded", 0x540310),
        ("Videos Created", 0x540314), ("Smash Tags Claimed", 0x540318)],
    "Online": [
        ("Online Play Time", 0x540320), ("Solo Quickplay Battles", 0x540324),
        ("Solo Quickplay Wins", 0x540328), ("Highest Global Smash Power", 0x54032C),
        ("Highest Total Global Smash Power", 0x540330), ("Co-op Quickplay Battles", 0x540334),
        ("Co-op Quickplay Wins", 0x540338), ("Elite Quickplay Battles", 0x54033C),
        ("Elite Quickplay Wins", 0x540340), ("Arena Battles", 0x540344)],
}


def default_save_path():
    native_config = os.environ.get("XDG_CONFIG_HOME", "")
    if not os.path.isabs(native_config):
        native_config = os.path.expanduser("~/.config")
    legacy_config = os.path.expanduser("~/.var/app/org.ryujinx.Ryujinx/config")
    candidates = (
        RYUJINX_SAVE,
        os.path.join(legacy_config, _RYUJINX_PRIMARY_SAVE),
        os.path.join(native_config, _RYUJINX_PRIMARY_SAVE),
    )
    for path in candidates:
        try:
            info = os.stat(path)
        except OSError:
            continue
        if stat.S_ISREG(info.st_mode) and info.st_size == SAVE_SIZE:
            return path
    return ""


def _slot(path):
    parts = os.path.abspath(path).split(os.sep)
    if len(parts) > 3 and parts[-2] == "save_data" and parts[-3] in ("0", "1"):
        return parts[-3]
    return None


def mirror_path(path):
    """Ryujinx keeps two commit slots (.../0/save_data and .../1/save_data)."""
    slot = _slot(path)
    if slot is not None:
        parts = os.path.abspath(path).split(os.sep)
        parts[-3] = "1" if slot == "0" else "0"
        other = os.sep.join(parts)
        if os.path.isdir(os.path.dirname(other)):
            return other
    return None


def ryujinx_running():
    me = os.getpid()
    for pid in os.listdir("/proc"):
        if not pid.isdigit() or int(pid) == me:
            continue
        try:
            with open(f"/proc/{pid}/comm") as f:
                comm = f.read().strip().lower()
        except OSError:
            continue
        if comm.startswith("ryujinx"):
            return True
    return False


def _sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _read_disk(path):
    """Read a bounded snapshot; None represents a missing commit slot."""
    def regular_file(name, flags):
        return os.open(name, flags | os.O_NONBLOCK | os.O_NOFOLLOW)

    try:
        with open(path, "rb", opener=regular_file) as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise OSError(f"Expected a regular save file: {path}")
            return stream.read(SAVE_SIZE + 1)
    except FileNotFoundError:
        return None


@contextmanager
def _lock_save_directory(path):
    directory = os.path.dirname(path)
    if _slot(path) is not None:
        directory = os.path.dirname(os.path.dirname(directory))
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def _publish_new(temporary, path):
    """Publish without replacing an existing entry. Return whether the temp still exists."""
    rename = getattr(ctypes.CDLL(None, use_errno=True), "renameat2", None)
    if rename is not None:
        # Linux supports this flag on filesystems that cannot create hard links.
        rename.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
        rename.restype = ctypes.c_int
        if rename(_AT_FDCWD, os.fsencode(temporary), _AT_FDCWD, os.fsencode(path), _RENAME_NOREPLACE) == 0:
            return False
        error = ctypes.get_errno()
        if error not in (errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP):
            raise OSError(error, os.strerror(error), path)
    try:
        os.link(temporary, path)
    except OSError as error:
        if error.errno in (errno.EPERM, errno.EOPNOTSUPP):
            raise OSError(error.errno, "The destination does not support safe creation of a new save copy", path) from error
        raise
    return True


def _atomic_write(path, data, *, expected=_UNCHECKED, new_file=False):
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".smasher-")
    try:
        try:
            stream = os.fdopen(fd, "wb")
        except BaseException:
            os.close(fd)
            raise
        with stream as f:
            if not new_file:
                try:
                    mode = os.stat(path).st_mode & 0o7777
                except FileNotFoundError:
                    mode = 0o644
                os.fchmod(f.fileno(), mode)
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if expected is not _UNCHECKED and _read_disk(path) != expected:
            raise SaveConflict(f"The save changed on disk while preparing to replace {path}.")
        if new_file:
            linked = _publish_new(tmp, path)
            try:
                if linked:
                    os.unlink(tmp)
                _sync_directory(directory)
            except OSError as error:
                raise CopyPublishedError(
                    error.errno,
                    f"The copy was created, but cleanup or directory synchronization failed: {error}. "
                    "Its durability is uncertain",
                    path,
                ) from error
        else:
            os.replace(tmp, path)
            _sync_directory(directory)
    except BaseException:
        with suppress(OSError):
            os.unlink(tmp)
        raise


class SaveFile:
    def __init__(self, path):
        path = os.path.realpath(path)
        try:
            raw = _read_disk(path)
            other = mirror_path(path)
            mirror = _read_disk(other) if other else None
        except OSError as e:
            raise InvalidSave(f"Can't read the file: {e.strerror or e}") from e
        if raw is None:
            raise InvalidSave("Can't read the file: file not found")
        if len(raw) != SAVE_SIZE:
            raise InvalidSave(f"Not a Smash Ultimate system_data.bin "
                              f"(size {len(raw):,} bytes, expected {SAVE_SIZE:,}).")
        if mirror is not None and len(mirror) != SAVE_SIZE:
            raise InvalidSave("The other Ryujinx slot has an unsupported size; check both save files first.")
        self.path = path
        self.data = bytearray(raw)
        self.clean = raw
        self._mirror = other
        self._disk_snapshots = {path: raw}
        if other:
            self._disk_snapshots[other] = mirror
        self.backup_warning = None

    # --- raw access -----------------------------------------------------
    def get(self, offset, size=1):
        self._validate_span(offset, size)
        return struct.unpack_from(FMT[size], self.data, offset)[0]

    def _validate_span(self, offset, size):
        if size not in FMT or not isinstance(offset, int) or not 0 <= offset <= len(self.data) - size:
            raise ValueError("Field offset or size is outside the save data")

    def set(self, offset, value, size=1):
        self._validate_span(offset, size)
        limit = (1 << (8 * size)) - 1
        if not 0 <= int(value) <= limit:
            raise ValueError(f"value {value} out of range 0..{limit}")
        struct.pack_into(FMT[size], self.data, offset, int(value))

    @property
    def dirty(self):
        return self.data != self.clean

    # --- fields ---------------------------------------------------------
    def value(self, field):
        return self.get(field.offset, field.size)

    def set_value(self, field, value):
        value = max(0, min(field.maximum, int(value)))
        self.set(field.offset, value, field.size)
        if field is GOLD:   # keep the records consistent with the wallet
            self.set(GOLD_OBTAINED, value, 4)
            self.set(GOLD_SPENT, 0, 4)
        elif field is SP:
            self.set(SP_OBTAINED, value, 4)

    @property
    def language(self):
        return self.get(LANGUAGE_OFFSET)

    @language.setter
    def language(self, idx):
        if not 0 <= idx < len(LANGUAGES):
            raise ValueError("unknown language")
        self.set(LANGUAGE_OFFSET, idx)

    def fighter_unlocked(self, i):
        return self.get(fighter_offset(i)) == 1

    def set_fighter(self, i, unlocked):
        self.set(fighter_offset(i), 1 if unlocked else 0)

    def fighters_unlocked(self):
        return sum(self.fighter_unlocked(i) for i in range(len(FIGHTERS)))

    def _bits(self, ranges):
        total = sum((b - a) * 8 for a, b in ranges)
        on = sum(x.bit_count() for a, b in ranges for x in self.data[a:b])
        return on, total

    def milestones_progress(self):
        return self._bits([MILESTONES])

    def mii_clothes_progress(self):
        return self._bits(MII_CLOTHES)

    def unlock_milestones(self):
        a, b = MILESTONES
        self.data[a:b] = b"\xff" * (b - a)

    def unlock_mii_clothes(self):
        for a, b in MII_CLOTHES:
            self.data[a:b] = b"\xff" * (b - a)

    def stats(self, category):
        return [(name, off, self.get(off, 4)) for name, off in STATS[category]]

    def set_stats(self, values):
        """values: {offset: int}; validated as a whole before writing anything."""
        known = {off for rows in STATS.values() for _, off in rows}
        for off, v in values.items():
            if off not in known:
                raise ValueError("Unknown statistic offset")
            if not isinstance(v, int) or not 0 <= v <= STAT_MAX:
                raise ValueError(f"{v} is out of range (0..{STAT_MAX:,})")
        for off, v in values.items():
            self.set(off, v, 4)

    def load_bytes(self, raw):
        """Replace the editor contents (e.g. from a backup); marks it dirty."""
        if len(raw) != SAVE_SIZE:
            raise InvalidSave("Backup has the wrong size.")
        self.data = bytearray(raw)

    # --- saving ---------------------------------------------------------
    def export_copy(self, path):
        """Publish the edited bytes at a new path without changing the open save."""
        payload = bytes(self.data)
        if len(payload) != SAVE_SIZE:
            raise InvalidSave("The edited data has an unsupported size")
        path = os.path.abspath(os.fsdecode(path))
        other = self._mirror or mirror_path(self.path)
        if os.path.realpath(path) in (self.path, other):
            raise FileExistsError(errno.EEXIST, "Choose a path outside the active save slots", path)
        _atomic_write(path, payload, new_file=True)
        return path

    def save(self, backup_dir=None):
        """Check disk snapshots, back up, then replace slots with rollback on failure.

        A group of filesystem replacements cannot be crash-atomic. The published
        backup remains available even when a write or rollback fails.
        """
        if len(self.data) != SAVE_SIZE:
            raise InvalidSave("The edited data has an unsupported size")
        with _lock_save_directory(self.path):
            return self._save_locked(backup_dir)

    def _save_locked(self, backup_dir):
        other = self._mirror or mirror_path(self.path)
        targets = [self.path] + ([other] if other else [])
        previous = {p: _read_disk(p) for p in targets}
        for path, raw in previous.items():
            if raw != self._disk_snapshots.get(path):
                raise SaveConflict("The save changed on disk. Reopen the file before saving; your edits remain in the editor.")
        backup = make_backup(targets, backup_dir, prune=False, _snapshots=previous)
        # Copying the backup takes time: detect writers before replacing anything.
        if any(_read_disk(path) != raw for path, raw in previous.items()):
            raise SaveConflict(f"The save changed while preparing the backup. Reopen the file. Backup: {backup}")
        payload = bytes(self.data)
        attempted = []
        try:
            for path in targets:
                attempted.append(path)
                try:
                    _atomic_write(path, payload, expected=previous[path])
                except SaveConflict:
                    attempted.pop()
                    raise
            if any(_read_disk(path) != payload for path in targets):
                raise SaveConflict("At least one save slot changed during the write.")
        except OSError as error:
            failed = []
            for path in reversed(attempted):
                try:
                    current = _read_disk(path)
                    if current == previous[path]:
                        continue
                    if current != payload:
                        raise OSError("file changed during recovery")
                    if previous[path] is None:
                        os.unlink(path)
                        _sync_directory(os.path.dirname(path))
                    else:
                        _atomic_write(path, previous[path], expected=payload)
                except OSError as recovery_error:
                    failed.append(f"{path}: {recovery_error}")
            conflict = isinstance(error, SaveConflict)
            recovery = "Editor writes rolled back." if conflict else "Original files restored."
            if failed:
                recovery = "Recovery incomplete: " + "; ".join(failed)
            error_type = SaveConflict if conflict else OSError
            raise error_type(f"Save failed: {str(error).rstrip('.')}. {recovery} "
                             f"Your edits are still pending. Backup: {backup}") from error
        self.clean = payload
        self._disk_snapshots = {p: payload for p in targets}
        self._mirror = other
        self.backup_warning = None
        try:
            prune_backups(backup_dir)
        except OSError as error:
            # Retention is housekeeping: a completed save must not be reported as failed.
            self.backup_warning = f"Saved, but old backups could not be pruned: {error}"
        return backup


def make_backup(paths, backup_dir=None, *, prune=True, _snapshots=None):
    backup_dir = backup_dir or BACKUP_DIR
    if _snapshots is None:
        sources = dict.fromkeys(os.path.realpath(p) for p in paths)
        _snapshots = {p: _read_disk(p) for p in sources}
    existing = [(path, raw) for path, raw in _snapshots.items() if raw is not None]
    if not existing:
        return None
    if any(len(raw) != SAVE_SIZE for _, raw in existing):
        raise InvalidSave("Cannot back up files with an unsupported save size.")
    stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    os.makedirs(backup_dir, exist_ok=True)
    stage = tempfile.mkdtemp(dir=backup_dir, prefix=".smasher-backup-")
    try:
        entries = []
        for p, raw in existing:
            slot = _slot(p)
            filename = f"slot{slot}_system_data.bin" if slot is not None else "system_data.bin"
            target = os.path.join(stage, filename)
            if os.path.exists(target):
                raise OSError(f"Multiple sources would use the backup filename {filename}.")
            shutil.copy2(p, target)
            with open(target, "rb") as stream:
                if stream.read(SAVE_SIZE + 1) != raw:
                    raise SaveConflict(f"The source changed while copying the backup: {p}")
                os.fsync(stream.fileno())
            entries.append({"source": p, "file": filename, "size": len(raw),
                            "sha256": hashlib.sha256(raw).hexdigest()})
        with open(os.path.join(stage, "metadata.json"), "w", encoding="utf-8") as stream:
            json.dump({"created_at": time.time(), "files": entries}, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        _sync_directory(stage)
        if any(_read_disk(path) != raw for path, raw in _snapshots.items()):
            raise SaveConflict("The save changed while preparing the backup. Try again with the game closed.")
        n = 1
        while True:
            dest = os.path.join(backup_dir, stamp if n == 1 else f"{stamp}_{n}")
            if not os.path.lexists(dest):
                try:
                    os.rename(stage, dest)
                    break
                except OSError as error:
                    if error.errno not in (errno.EEXIST, errno.ENOTEMPTY):
                        raise
            n += 1
        _sync_directory(backup_dir)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    if prune:
        prune_backups(backup_dir)
    return dest


def _backup_metadata(folder):
    try:
        with open(os.path.join(folder, "metadata.json"), encoding="utf-8") as stream:
            data = json.load(stream)
    except FileNotFoundError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("files"), list):
        raise InvalidSave("The backup metadata is damaged.")
    return data


def backup_details(folder):
    """Optional metadata for display; legacy backups remain supported.

    SHA-256 describes backup contents, not a checksum required by the game.
    """
    try:
        data = _backup_metadata(folder)
        if data is not None:
            return data
    except (OSError, ValueError, InvalidSave):
        pass
    return {"created_at": os.path.getmtime(folder), "files": []}


def read_backup(path):
    """Read a backup and verify its recorded digest when metadata exists."""
    raw = _read_disk(path)
    if raw is None or len(raw) != SAVE_SIZE:
        raise InvalidSave("The backup file is missing or has an unsupported size.")
    try:
        metadata = _backup_metadata(os.path.dirname(path))
    except ValueError as error:
        raise InvalidSave("The backup metadata is damaged.") from error
    if metadata is not None:
        entry = next((record for record in metadata["files"] if isinstance(record, dict)
                      and record.get("file") == os.path.basename(path)), None)
        if (entry is None or entry.get("size") != len(raw)
                or entry.get("sha256") != hashlib.sha256(raw).hexdigest()):
            raise InvalidSave("This backup does not match its recorded size or SHA-256.")
    return raw


def list_backups(backup_dir=None):
    """Newest first: [(folder, file_to_restore, mtime)]."""
    backup_dir = backup_dir or BACKUP_DIR
    out = []
    try:
        names = os.listdir(backup_dir)
    except FileNotFoundError:
        return out
    for name in names:
        if name.startswith("."):
            continue
        d = os.path.join(backup_dir, name)
        if not os.path.isdir(d) or os.path.islink(d):
            continue
        try:
            files = sorted(f for f in os.listdir(d) if f.endswith("system_data.bin")
                           and os.path.isfile(os.path.join(d, f)) and not os.path.islink(os.path.join(d, f)))
            if not files:
                continue
            entries = backup_details(d)["files"]
            primary = entries[0].get("file") if entries and isinstance(entries[0], dict) else None
            if not isinstance(primary, str) or primary not in _BACKUP_FILES:
                primary = files[0]
            out.append((d, os.path.join(d, primary), os.path.getmtime(d)))
        except FileNotFoundError:
            # A concurrent save may have pruned this folder.
            continue
    out.sort(key=lambda t: (t[2], os.path.basename(t[0])), reverse=True)
    return out


def prune_backups(backup_dir=None, keep=BACKUP_KEEP):
    kept = 0
    for d, _, _ in list_backups(backup_dir):
        if not _BACKUP_NAME.fullmatch(os.path.basename(d)):
            continue
        try:
            with os.scandir(d) as entries:
                if any(entry.name not in _BACKUP_FILES | {"metadata.json"}
                       or not entry.is_file(follow_symlinks=False) for entry in entries):
                    continue
            if kept >= keep:
                shutil.rmtree(d)
            else:
                kept += 1
        except FileNotFoundError:
            if os.path.exists(d):
                raise
