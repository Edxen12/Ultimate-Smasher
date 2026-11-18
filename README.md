# Ultimate Smasher

**Edit Super Smash Bros. Ultimate saves on Linux, Windows, and macOS.** A Python and PyQt5 desktop editor with change review, backups, and keyboard and controller navigation.

[![Desktop tests](https://github.com/Edxen12/Ultimate-Smasher/actions/workflows/checks.yml/badge.svg)](https://github.com/Edxen12/Ultimate-Smasher/actions/workflows/checks.yml)

[Quick start](#quick-start) · [Editing tools](#editing-tools) · [Controls](#controls) · [Compatibility](#compatibility)

![Ultimate Smasher main menu showing the five editing sections and the file controls](docs/preview.png)

## Quick start

Install Python 3.10 or newer. Clone the repository on any platform:

```sh
git clone https://github.com/Edxen12/Ultimate-Smasher.git
cd Ultimate-Smasher
```

**Linux and macOS**

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python "Ultimate Smasher.py"
```

**Windows (PowerShell)**

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe "Ultimate Smasher.py"
```

The editor looks for saves in known Ryujinx and Ryubing locations. To choose one, open **Files** or pass a path:

```sh
python "Ultimate Smasher.py" "/path/to/system_data.bin"
```

The window can shrink to 800×450. Use `--fullscreen` to start in fullscreen. Sound effects use `pw-play` or `paplay` on Linux and the system audio tools on Windows and macOS. Set `SMASHER_MUTE=1` to start muted.

## Editing tools

| Section | What you can edit |
| --- | --- |
| **General** | Gold, SP, hammers, tickets, game language, milestones, and Mii clothes |
| **Items** | Snacks, Spirit Board items, and battle items |
| **Characters** | Unlock or lock 71 base fighters individually or in bulk |
| **Stats** | Search and edit records across six categories |
| **Backups** | Snapshot disk saves, filter by source, and load a backup into the editor |

Open **Files → Review Changes** to see the original and edited values before writing them. **Export Copy** writes your edits to a new file. Loading a backup is undoable and writes to disk only when you choose **Save**.

## Controls

| Action | Keyboard |
| --- | --- |
| Navigate and select | Arrow keys and Enter |
| Open files or show the file menu | Ctrl+O or Alt+F |
| Save or export a copy | Ctrl+S or Ctrl+Shift+S |
| Review pending edits | Ctrl+I |
| Undo or redo | Ctrl+Z or Ctrl+Shift+Z |
| Change section | Q/E or Ctrl+Page Up/Page Down |
| Back, fullscreen, help | Esc, F11, F1 |

Controllers use evdev on Linux and XInput on Windows. The D-pad or left stick moves focus, Cross/A confirms, Circle/B goes back, L1/R1 change section, and Options/Start saves. On macOS, use keyboard or mouse. macOS uses Command for the shortcuts listed with Ctrl.

## Compatibility

- Supports the inherited `system_data.bin` layout of **5,982,968 bytes**. File size alone does not confirm compatibility. DLC fighter flags are outside the supported layout.
- The original 1.2.1 bulk core, sticker, and spirit commands overwrite entire regions of the save. On a sample save, that also replaced existing progress data. These commands were disabled in the original 2.0 alpha and are unavailable in this editor.
- Close the game before saving. The editor checks for changes on disk, creates a recovery copy, and updates the Ryujinx slots separately. If the save changes externally, the editor keeps your pending edits and offers to export them.
- The public checkout runs with its bundled artwork. You can add optional local images in `img/portraits`, `img/renders`, `img/stock`, and `img/series`, plus a hub image at `img/hub-art.png`. These paths are ignored by Git.

## Development

```sh
python -m unittest discover
```

The suite includes offscreen UI tests. Set `SMASH_TEST_SAVE=/path/to/system_data.bin` to run the save tests on temporary copies of an existing file.

## Credits and license

Based on the original [Ultimate Smasher by Ret-HZ](https://github.com/Ret-HZ/Ultimate-Smasher). The project source uses the [GNU GPL v2](LICENSE). This is an unofficial editor.

Bundled fonts have their own licenses for [Barlow Condensed](fonts/OFL.txt), [Nunito](fonts/OFL-Nunito.txt), and [Font Awesome Free](fonts/LICENSE-Font-Awesome.txt).
