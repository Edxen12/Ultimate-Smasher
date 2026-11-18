# Ultimate Smasher

A Super Smash Bros. Ultimate (Nintendo Switch) save editor written in Python / PyQt5,
with an interface styled after the game's own menus. The main menu is drawn in
code (crisp at any resolution): Fighters, Items, General, Backups and Stats tiles
around the key-art disc (`img/hub-art.png`), a side rail (home, open, sound, help,
quit) and a live description strip with the clock. The small floppy tile saves
changes; Ctrl+S also works.

Run: `python3 "Ultimate Smasher.py" [--fullscreen] [system_data.bin]` — without a path it opens the
Ryujinx (flatpak) save automatically. It starts in a compact 1040×590 desktop window. `--fullscreen` opts into fullscreen,
scaled to the screen with Qt's high-DPI scaling; `--window` is also accepted.

## Features

* **General**: Gold, SP, Hammers, Tickets, game language, unlock all Milestones and Mii clothes
* **Items**: inventory of Snacks (S/M/L), Spirit Board and battle items with a detail panel (− / + / MAX, keys + and −), or MAX ALL
* **Characters**: lock / unlock any of the 71 base fighters, or all at once; HD portraits, fighter render, series symbol and stock icon
* **Stats**: edit every record (Combined, Smash, Spirits, Games & More, Vault, Online)
* **Backups**: a backup of both Ryujinx slots is made on every save (last 20 kept); load any of them back

Saving writes atomically, keeps both Ryujinx commit slots (`0/` and `1/`) identical and
warns if Ryujinx is running. Unsaved changes are confirmed before quitting or opening another file.

Keys: arrows + Enter (→ from the right-hand tiles reaches the side rail) · Esc back (quit from the main menu) · Q / E change section · Ctrl+O open ·
Ctrl+S save · M sound on/off · F1 help.

Controller (read straight from `/dev/input`, needs the `input` group; hot-plug supported):
D-pad / left stick move (PlayStation, Xbox and other evdev pads) · Cross/A OK · Circle/B back · L1 / R1 section · Options/Start save · Share/Select help.

UI sounds are original, synthesised by `sfx.py` into `sounds/` and played with `pw-play`/`paplay`
(set `SMASHER_MUTE=1` to silence them).

## Layout

* `save_data.py` – save file model, offsets, backups (no GUI code)
* Tests: `python3 -m unittest test_save_data test_ui_smoke test_hub_geometry` (the UI one runs headless);
  set `SMASH_TEST_SAVE=path` to run them on a temporary copy of a real save
* `smash_ui.py` – the interface · `hub_geometry.py` – main-menu shapes (virtual 1920×1080)
* `gamepad.py` – controller input · `sfx.py` – sound effects
* `Ultimate Smasher.py` – entry point

Fighter portraits (`img/portraits/`), renders (`img/renders/`), stock icons (`img/stock/`) and series symbols (`img/series/`) come from the community package
[smash-ultimate-assets](https://github.com/marcrd/smash-ultimate-assets) (Apache-2.0, see `img/portraits/LICENSE-smash-ultimate-assets.txt`).

Fonts bundled in `fonts/`: Nunito and Barlow Condensed (SIL OFL, see `fonts/OFL.txt`), Font Awesome.

Based on Ultimate Smasher by Capitán Retraso (GPL-3.0). Editing saves can corrupt them: keep backups.
