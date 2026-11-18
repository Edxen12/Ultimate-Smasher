#!/usr/bin/env python3
"""Ultimate Smasher - Super Smash Bros. Ultimate save editor.

Usage: Ultimate Smasher.py [path/to/system_data.bin]
Without a path it opens the Ryujinx save if it exists.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import smash_ui

if __name__ == "__main__":
    app, win = smash_ui.main(sys.argv)
    sys.exit(app.exec_())
