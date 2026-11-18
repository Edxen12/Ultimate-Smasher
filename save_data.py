"""Smash Bros. Ultimate system_data.bin model (no GUI code).

All offsets come from the original Ultimate Smasher (Ret-HZ, 2019); the fighter
table offsets were corrected locally (8-byte slots from 0x53FF40, official order).
"""
import os
import shutil
import struct
import tempfile
import time
from dataclasses import dataclass

SAVE_SIZE = 5982968
RYUJINX_SAVE = os.path.expanduser(
    "~/.var/app/io.github.ryubing.Ryujinx/config/Ryujinx/bis/user/save/"
    "0000000000000001/0/save_data/system_data.bin")
BACKUP_DIR = os.path.expanduser("~/Games/Switch/smash-save-backups")
BACKUP_KEEP = 20

FMT = {1: "<B", 2: "<H", 4: "<I"}


class InvalidSave(Exception):
    pass


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
    return RYUJINX_SAVE if os.path.exists(RYUJINX_SAVE) else ""


def mirror_path(path):
    """Ryujinx keeps two commit slots (.../0/save_data and .../1/save_data)."""
    parts = os.path.abspath(path).split(os.sep)
    if len(parts) > 3 and parts[-2] == "save_data" and parts[-3] in ("0", "1"):
        parts[-3] = "1" if parts[-3] == "0" else "0"
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


def _atomic_write(path, data):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".smasher-")
    try:
        try:
            os.fchmod(fd, os.stat(path).st_mode & 0o7777)  # keep the original permissions
        except FileNotFoundError:
            os.fchmod(fd, 0o644)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


class SaveFile:
    def __init__(self, path):
        try:
            size = os.path.getsize(path)
        except OSError as e:
            raise InvalidSave(f"Can't read the file: {e.strerror}") from e
        if size != SAVE_SIZE:
            raise InvalidSave(f"Not a Smash Ultimate system_data.bin "
                              f"(size {size:,} bytes, expected {SAVE_SIZE:,}).")
        with open(path, "rb") as f:
            raw = f.read()
        self.path = path
        self.data = bytearray(raw)
        self.clean = raw

    # --- raw access -----------------------------------------------------
    def get(self, offset, size=1):
        return struct.unpack_from(FMT[size], self.data, offset)[0]

    def set(self, offset, value, size=1):
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
        for v in values.values():
            if not 0 <= v <= STAT_MAX:
                raise ValueError(f"{v} is out of range (0..{STAT_MAX:,})")
        for off, v in values.items():
            self.set(off, v, 4)

    def load_bytes(self, raw):
        """Replace the editor contents (e.g. from a backup); marks it dirty."""
        if len(raw) != SAVE_SIZE:
            raise InvalidSave("Backup has the wrong size.")
        self.data = bytearray(raw)

    # --- saving ---------------------------------------------------------
    def save(self, backup_dir=None):
        """Back up current files, write atomically, mirror the other Ryujinx slot."""
        targets = [self.path] + ([mirror_path(self.path)] if mirror_path(self.path) else [])
        backup = make_backup(targets, backup_dir)
        payload = bytes(self.data)
        for t in targets:
            _atomic_write(t, payload)
        self.clean = payload
        return backup


def make_backup(paths, backup_dir=None):
    backup_dir = backup_dir or BACKUP_DIR
    existing = [p for p in paths if os.path.exists(p)]
    if not existing:
        return None
    stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    dest = os.path.join(backup_dir, stamp)
    n = 1
    while os.path.exists(dest):
        n += 1
        dest = os.path.join(backup_dir, f"{stamp}_{n}")
    os.makedirs(dest)
    for p in existing:
        slot = p.split(os.sep)[-3] if mirror_path(p) else "file"
        shutil.copy2(p, os.path.join(dest, f"slot{slot}_system_data.bin" if slot != "file" else "system_data.bin"))
    prune_backups(backup_dir)
    return dest


def list_backups(backup_dir=None):
    """Newest first: [(folder, file_to_restore, mtime)]."""
    backup_dir = backup_dir or BACKUP_DIR
    out = []
    if not os.path.isdir(backup_dir):
        return out
    for name in os.listdir(backup_dir):
        d = os.path.join(backup_dir, name)
        if not os.path.isdir(d):
            continue
        files = sorted(f for f in os.listdir(d) if f.endswith("system_data.bin"))
        if files:
            f = os.path.join(d, files[0])
            out.append((d, f, os.path.getmtime(d)))  # backup time, not the save's mtime
    out.sort(key=lambda t: os.path.basename(t[0]), reverse=True)
    return out


def prune_backups(backup_dir=None, keep=BACKUP_KEEP):
    for d, _, _ in list_backups(backup_dir)[keep:]:
        shutil.rmtree(d, ignore_errors=True)
