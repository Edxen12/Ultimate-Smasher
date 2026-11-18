# Ultimate Smasher

A Super Smash Bros. Ultimate (Nintendo Switch) save editor written in Python / PyQt5,
with an interface styled after the game's own menus. The main menu is drawn in
code (crisp at any resolution): Fighters, Items, General, Backups and Stats tiles
around the key-art disc (`img/hub-art.png`), a side rail (home, open, sound, help,
quit) and a live description strip with the clock. The small floppy tile saves
changes; Ctrl+S also works.

Install on Linux with Python 3.10 or newer using `python3 -m pip install -r requirements.txt` in a virtual environment.

Run `python3 "Ultimate Smasher.py" [--fullscreen] [system_data.bin]`. Without a path it looks for
a Ryujinx or Ryubing save in known local installations. It starts in a resizable 1040×590 desktop window
(the minimum size). Drag the window borders to resize, or use the title bar to maximize.
F11 toggles native fullscreen and restores the previous window mode; Esc also leaves
fullscreen when no dialog is open. The menu rail and section header include a fullscreen
button. `--fullscreen` starts in fullscreen; `--window` is also accepted. Panels adapt
to the available space while Qt handles high-DPI rendering.

## Features

* **General**: Gold, SP, Hammers, Tickets, game language, unlock all Milestones and Mii clothes
* **Items**: inventory of Snacks (S/M/L), Spirit Board and battle items with a detail panel (− / + / MAX, keys + and −), or MAX ALL
* **Characters**: search the 71 base fighters by name, filter by unlock state or pending changes, and edit them individually or in bulk
* **Stats**: find and edit records within Combined, Smash, Spirits, Games & More, Vault and Online
* **Backups**: create copies manually or on save, with the newest 20 managed copies retained. Filter backups by the recorded source. Load a backup into the editor, then press Save to write it to disk.

Open **Files** with Alt+F or the folder icon to browse and reopen recent files. **Review changes**
shows original and edited values side by side. **Export copy** writes the current editor contents
to a new file and preserves the original file and edit history. If the save has changed on disk,
the conflict dialog also offers export.

The editor checks for on-disk changes before saving, creates a recovery copy, then replaces each Ryujinx commit slot atomically. The two slots are separate files. Close the game before saving to prevent Ryujinx from writing to either slot during the operation. The supported layout is identified by file size and uses inherited offsets.

Use the arrow keys and Enter to navigate. Press → from the right-hand tiles to reach the side rail.
Esc goes back. Q / E and Ctrl+PgUp / Ctrl+PgDn change section. Ctrl+O opens a file and Ctrl+S saves.
Ctrl+Z undoes a save edit and Ctrl+Shift+Z redoes it. F11 toggles fullscreen, M toggles sound, and F1 opens help.
Ctrl+I opens the change review and Ctrl+Shift+S exports a copy.

Controller (read straight from `/dev/input`, needs the `input` group; hot-plug supported):
D-pad / left stick move (PlayStation, Xbox and other evdev pads) · Cross/A OK · Circle/B back · L1 / R1 section · Options/Start save · Share/Select help.

UI sounds play through `pw-play` or `paplay`. If the bundled WAVs are missing or damaged,
`sfx.py` regenerates them under `$XDG_CACHE_HOME/ultimate-smasher` (by default `~/.cache/ultimate-smasher`).
Set `SMASHER_MUTE=1` to silence them.

## Layout

* `save_data.py` – save file model, offsets, backups (no GUI code)
* Tests run with `python3 -m unittest discover`, including headless UI checks.
  Set `SMASH_TEST_SAVE=path` to exercise the editor on temporary copies of a real save.
* `smash_ui.py` – the interface · `hub_geometry.py` – main-menu shapes (virtual 1920×1080)
* `gamepad.py` – controller input · `sfx.py` – sound effects
* `Ultimate Smasher.py` – entry point

Fighter portraits (`img/portraits/`), renders (`img/renders/`), stock icons (`img/stock/`) and series symbols (`img/series/`) come from the community package
[smash-ultimate-assets](https://github.com/marcrd/smash-ultimate-assets) (Apache-2.0, see `img/portraits/LICENSE-smash-ultimate-assets.txt`).

Fonts bundled in `fonts/`: Nunito and Barlow Condensed (SIL OFL, see `fonts/OFL.txt`), Font Awesome.

Based on Ultimate Smasher by Capitán Retraso (GPL-3.0). Editing saves can corrupt them: keep backups.
