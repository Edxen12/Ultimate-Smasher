"""Shared visual values for the native Smash-inspired interface.

The expressive display face is kept separate from readable functional text.
All values are logical pixels; Qt applies the platform's display scaling.
"""
import os
import weakref
from dataclasses import dataclass

from PyQt5 import sip
from PyQt5.QtCore import QObject, QSettings, pyqtSignal


@dataclass(frozen=True)
class Colors:
    red_top: str = "#ee2238"
    red: str = "#d4001c"
    red_dark: str = "#a20014"
    ink: str = "#111114"
    panel: str = "#24252a"
    paper: str = "#f3f3f3"
    white: str = "#ffffff"
    yellow: str = "#ffd400"
    muted: str = "#656873"
    border: str = "#101010"
    disabled: str = "#a1a3aa"
    success: str = "#15803d"
    error: str = "#bd1028"
    field_focus: str = "#fff8c5"


@dataclass(frozen=True)
class Spacing:
    xs: int = 4
    sm: int = 8
    md: int = 12
    lg: int = 16
    xl: int = 24
    margin: int = 24


@dataclass(frozen=True)
class Typography:
    display: str = "Barlow Condensed"
    functional: str = "Nunito"
    icon: str = "Font Awesome 6 Free"
    caption: int = 13
    body: int = 16
    label: int = 18
    heading: int = 28
    title: int = 34


@dataclass(frozen=True)
class Borders:
    thin: int = 1
    control: int = 2
    panel: int = 3
    focus: int = 3
    radius: int = 0
    slant: int = 16


@dataclass(frozen=True)
class Motion:
    press: int = 70
    hover: int = 140
    release: int = 180
    transition: int = 220
    dialog: int = 260


@dataclass(frozen=True)
class DesignTokens:
    colors: Colors = Colors()
    spacing: Spacing = Spacing()
    type: Typography = Typography()
    borders: Borders = Borders()
    motion: Motion = Motion()


tokens = DesignTokens()


class MotionSettings(QObject):
    """User preference with a small registry to finish currently running tweens."""

    changed = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self._preferences = QSettings("UltimateSmasher", "UltimateSmasher")
        override = os.environ.get("SMASHER_REDUCE_MOTION")
        self.reduced_motion = (override.lower() not in ("", "0", "false", "no") if override is not None
                               else self._preferences.value("reduced_motion", False, type=bool))
        self._animations = weakref.WeakSet()

    def track(self, animation):
        self._animations.add(animation)

    def untrack(self, animation):
        self._animations.discard(animation)

    def set_reduced_motion(self, enabled, persist=True):
        enabled = bool(enabled)
        if persist:
            self._preferences.setValue("reduced_motion", enabled)
        if enabled == self.reduced_motion:
            return
        self.reduced_motion = enabled
        if enabled:
            for animation in tuple(self._animations):
                if not sip.isdeleted(animation):
                    animation._finish_without_motion()
        self.changed.emit(enabled)


settings = MotionSettings()


def stylesheet():
    """Consistent Qt controls; flat geometry matches the painted menu panels."""
    c, b, t = tokens.colors, tokens.borders, tokens.type
    return f"""* {{ font-family: '{t.functional}'; }}
QToolTip {{ background: {c.ink}; color: {c.white}; border: {b.control}px solid {c.yellow};
           padding: 6px 9px; font-size: {t.caption}px; font-weight: 700; }}
QLineEdit, QComboBox {{ background: {c.paper}; color: {c.ink}; border: {b.control}px solid {c.border};
                      border-radius: {b.radius}px; padding: 5px 9px; font-size: {t.body}px; }}
QLineEdit:focus, QComboBox:focus {{ background: {c.field_focus}; border-color: {c.red}; }}
QLineEdit:disabled, QComboBox:disabled {{ color: {c.muted}; background: #dedfe2; border-color: {c.disabled}; }}
QLineEdit {{ selection-background-color: {c.red}; selection-color: {c.white}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{ background: {c.paper}; color: {c.ink};
                             selection-background-color: {c.yellow}; selection-color: {c.ink}; }}
QCheckBox {{ color: {c.ink}; spacing: 8px; font-size: {t.body}px; }}
QCheckBox:focus {{ outline: {b.control}px solid {c.red}; }}
QScrollBar:vertical {{ background: rgba(0,0,0,0.08); width: 10px; margin: 0; border: none; }}
QScrollBar::handle:vertical {{ background: {c.yellow}; min-height: 30px; border: 1px solid {c.ink}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
"""
