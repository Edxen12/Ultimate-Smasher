"""Smash Ultimate-style interface for Ultimate Smasher.

Everything is custom painted with QPainter and animated with QVariantAnimation.
Editing goes through `Store`, which wraps a `save_data.SaveFile`.
"""
import math
import os
import random
import sys
import time

from PyQt5 import sip
from PyQt5.QtCore import (
    QEasingCurve,
    QObject,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QUrl,
    QVariantAnimation,
    pyqtSignal,
)
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QDesktopServices,
    QFont,
    QFontDatabase,
    QFontMetricsF,
    QIcon,
    QImage,
    QIntValidator,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QRadialGradient,
)
from PyQt5.QtWidgets import (
    QAbstractButton,
    QAbstractSpinBox,
    QApplication,
    QFileDialog,
    QGraphicsOpacityEffect,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

import gamepad
import hub_geometry as hg
import save_data as sd
import sfx

BASE = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(BASE, "img")
APP_TITLE = "ULTIMATE SMASHER"

W, H = 1040, 590
M = 24          # outer margin
HB = 56         # header band height
SB_H = 58       # status bar height
TAB_Y, TAB_H = HB + 10, 64
PANEL_Y = TAB_Y + TAB_H - 4
PANEL_H = H - PANEL_Y - SB_H
SLANT = 16
TITLE_FONT = "Barlow Condensed"
FA = "Font Awesome 6 Free"
ROUND_FONT = "Nunito"
STATUS = None
CURSOR = None
SFX = None
PAD = None


def set_stage(w, h):
    """Logical size of the UI (the whole screen in fullscreen mode)."""
    global W, H, PANEL_H
    W, H = max(1040, int(w)), max(590, int(h))
    PANEL_H = H - PANEL_Y - SB_H


def play(name):
    if SFX:
        SFX.play(name)

RED_TOP, RED_MID, RED_BOT = QColor("#ee2238"), QColor("#d4001c"), QColor("#a20014")
YELLOW = QColor("#ffd400")
WHITE = QColor("white")

G = {  # Font Awesome 6 solid glyphs
    "open": "", "save": "", "help": "", "back": "",
    "min": "", "close": "", "language": "", "milestones": "",
    "mii": "", "items": "", "fighters": "", "stats": "",
    "backups": "", "lock": "", "unlock": "", "check": "",
    "warn": "", "question": "", "minus": "", "plus": "",
    "star": "", "gift": "", "flask": "", "users": "",
    "trophy": "", "folder": "", "bolt": "", "clock": "",
    "list": "", "hand": "",
}


# ============================================================ helpers ======
def lerp(a, b, t):
    return a + (b - a) * t


def lerp_color(c0, c1, t):
    return QColor(int(lerp(c0.red(), c1.red(), t)), int(lerp(c0.green(), c1.green(), t)),
                  int(lerp(c0.blue(), c1.blue(), t)), int(lerp(c0.alpha(), c1.alpha(), t)))


def tween(owner, name, start, end, ms, on_value, easing=QEasingCurve.OutCubic,
          done=None, delay=0, loops=1):
    """Animate a float and call on_value(v); replaces a running tween of the same name."""
    anims = owner.__dict__.setdefault("_tweens", {})
    old = anims.get(name)
    if old is not None:
        old.stop()
    a = QVariantAnimation(owner)
    a.setStartValue(float(start)); a.setEndValue(float(end))
    a.setDuration(int(ms)); a.setEasingCurve(QEasingCurve(easing)); a.setLoopCount(loops)
    a.valueChanged.connect(lambda v: on_value(float(v)))
    if done:
        a.finished.connect(done)
    anims[name] = a
    if delay:
        QTimer.singleShot(int(delay), a.start)
    else:
        a.start()
    return a


def para(r, s=SLANT):
    """Parallelogram leaning right, inside rect r."""
    return QPolygonF([QPointF(r.left() + s, r.top()), QPointF(r.right(), r.top()),
                      QPointF(r.right() - s, r.bottom()), QPointF(r.left(), r.bottom())])


def para_path(r, s=SLANT):
    path = QPainterPath(); path.addPolygon(para(r, s)); path.closeSubpath()
    return path


def label_font(px, weight=QFont.Bold, italic=False):
    f = QFont(TITLE_FONT); f.setPixelSize(max(1, int(px))); f.setWeight(weight); f.setItalic(italic)
    return f


def heavy_italic(px):
    return label_font(px, QFont.Black, True)


def fa_font(px):
    f = QFont(FA); f.setPixelSize(max(1, int(px))); f.setWeight(QFont.Black)
    return f


def fit_font(make, text, width, start, minimum=10):
    size = start
    while QFontMetricsF(make(size)).horizontalAdvance(text) > width and size > minimum:
        size -= 0.5
    return make(size)


def game_font(px, weight=QFont.Black):
    font = QFont("DejaVu Sans")
    font.setPixelSize(max(1, int(px))); font.setWeight(weight); font.setStretch(85)
    return font


def facets(p, rect, color, slant=18):
    """Flat panel with broad facets, bounded by the supplied slanted shape."""
    path = para_path(rect, slant)
    p.save(); p.setClipPath(path)
    p.fillRect(rect, QColor(color)); p.setPen(Qt.NoPen)
    for i in range(5):
        x = rect.left() + rect.width() * i / 4
        p.setBrush(QColor(255, 255, 255, 12 + i * 3))
        p.drawPolygon(QPolygonF([QPointF(x, rect.top()),
                                 QPointF(x + rect.width() * 0.25, rect.top()),
                                 QPointF(x - rect.height() * 0.7, rect.bottom())]))
    p.setBrush(QColor(0, 0, 0, 20))
    p.drawPolygon(QPolygonF([rect.topRight(), rect.bottomRight(), rect.bottomLeft()]))
    p.restore()
    p.setBrush(Qt.NoBrush); p.setPen(QPen(QColor("#101010"), 3)); p.drawPath(path)


def smash_ball_path(c, r):
    """Smash emblem, proportions from Wikimedia Commons File:SmashBall.svg."""
    circle = QPainterPath(); circle.addEllipse(c, r, r)
    k = r / 130.0
    cut = QPainterPath(); cut.setFillRule(Qt.WindingFill)
    cut.addRect(QRectF(c.x() + (54 - 137) * k, c.y() - r - 1, (115 - 54) * k, 2 * r + 2))
    cut.addRect(QRectF(c.x() - r - 1, c.y() + (155 - 137) * k, 2 * r + 2, (180 - 155) * k))
    return circle.subtracted(cut)


def draw_text_shadow(p, rect, flags, text, color=WHITE, shadow=150):
    p.setPen(QColor(0, 0, 0, shadow)); p.drawText(rect.translated(1.5, 2), flags, text)
    p.setPen(color); p.drawText(rect, flags, text)


def silver_pen(rect, width=2.4, alpha=255):
    g = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    g.setColorAt(0.0, QColor(255, 255, 255, alpha)); g.setColorAt(0.45, QColor(150, 150, 160, alpha))
    g.setColorAt(0.55, QColor(120, 120, 130, alpha)); g.setColorAt(1.0, QColor(235, 235, 240, alpha))
    return QPen(QBrush(g), width)


def glow(p, path, color, radius=12, strength=60):
    if strength <= 1:
        return
    p.save(); p.setBrush(Qt.NoBrush)
    for i in range(radius, 0, -2):
        c = QColor(color); c.setAlpha(int(strength * (1 - i / (radius + 1)) / 2))
        p.setPen(QPen(c, i * 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)); p.drawPath(path)
    p.restore()


def halftone(p, ox, oy, cols, rows, color):
    p.setPen(Qt.NoPen); p.setBrush(color)
    for i in range(cols):
        for j in range(rows):
            rad = max(0.0, 2.4 - i * 0.14 - j * 0.28)
            if rad > 0.35:
                p.drawEllipse(QPointF(ox + 6 + i * 8, oy + 6 + j * 8), rad, rad)


def make_streaks(seed, n=14):
    rnd = random.Random(seed)
    return [(rnd.uniform(-0.2, 1.0), rnd.uniform(0, 1), rnd.uniform(0.25, 0.7), rnd.uniform(4, 18),
             rnd.randint(6, 15), rnd.uniform(0.012, 0.04)) for _ in range(n)]


def draw_streaks(p, w, h, streaks, phase, alpha_k=1.0):
    """Diagonal light streaks drifting slowly up-right."""
    p.setPen(Qt.NoPen)
    for x, y, length, thick, alpha, speed in streaks:
        xx = ((x + phase * speed + 0.4) % 1.7) - 0.4
        x0, y0 = xx * w, y * h
        dx, dy = length * w, -length * w * 0.22
        p.setBrush(QColor(255, 255, 255, int(alpha * alpha_k)))
        p.drawPolygon(QPolygonF([QPointF(x0, y0), QPointF(x0 + dx, y0 + dy),
                                 QPointF(x0 + dx, y0 + dy + thick * 0.15), QPointF(x0, y0 + thick)]))


def draw_sp(p, c, r, color):
    pts = [QPointF(c.x() + r * math.cos(math.pi / 8 + i * math.pi / 4),
                   c.y() + r * math.sin(math.pi / 8 + i * math.pi / 4)) for i in range(8)]
    p.setPen(QPen(color, 1.8)); p.setBrush(Qt.NoBrush); p.drawPolygon(QPolygonF(pts))
    p.setFont(label_font(r * 0.95)); p.setPen(color)
    p.drawText(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r), Qt.AlignCenter, "SP")


_PIX = {}


def pixmap(name):
    if name not in _PIX:
        _PIX[name] = QPixmap(os.path.join(IMG, name))
    return _PIX[name]


# Item badges: (top colour, bottom colour, Font Awesome glyph). Snacks keep the
# game's green / orange / red sizes; Spirit Board items are orange, enemy
# handicaps green, shield items blue.
ITEM_BADGES = {
    "snack_s": ("#8ee04a", "#2f9a1c", "\uf564"),
    "snack_m": ("#ffc24a", "#e0700c", "\uf564"),
    "snack_l": ("#ff6a5a", "#c8101e", "\uf564"),
    "shuffle_all": ("#ffa23a", "#e0560c", "\uf074"),
    "all_primaries": ("#ffa23a", "#e0560c", "\uf6de"),
    "all_supports": ("#ffa23a", "#e0560c", "\uf2b5"),
    "filler": ("#ffa23a", "#e0560c", "\uf0fe"),
    "rematch": ("#ffa23a", "#e0560c", "\uf2f9"),
    "damage50": ("#5ad66a", "#138a3a", "\uf295"),
    "slow_fs": ("#5ad66a", "#138a3a", "\uf252"),
    "weaken_minions": ("#5ad66a", "#138a3a", "\uf506"),
    "health_drain": ("#5ad66a", "#138a3a", "\uf7a9"),
    "disable_items": ("#5ad66a", "#138a3a", "\uf05e"),
    "shield_spacer": ("#58b8ff", "#1458d6", "\uf3ed"),
    "sluggish_shield": ("#58b8ff", "#1458d6", "\uf132"),
}


def draw_item_badge(p, disc, key, enabled=True):
    """Round item badge drawn in code: gradient disc, white ring, white glyph."""
    top, bottom, glyph = ITEM_BADGES[key]
    d = disc.width()
    p.setPen(Qt.NoPen); p.setBrush(QColor(0, 0, 0, 90)); p.drawEllipse(disc.translated(1.5, 2.5))
    p.setBrush(QColor("#111111")); p.drawEllipse(disc)
    inner = disc.adjusted(d * 0.05, d * 0.05, -d * 0.05, -d * 0.05)
    p.setBrush(WHITE); p.drawEllipse(inner)
    core = inner.adjusted(d * 0.065, d * 0.065, -d * 0.065, -d * 0.065)
    g = QLinearGradient(core.topLeft(), core.bottomLeft())
    g.setColorAt(0, QColor(top)); g.setColorAt(1, QColor(bottom))
    if not enabled:
        g.setColorAt(0, QColor("#b0b0b6")); g.setColorAt(1, QColor("#6a6a70"))
    p.setBrush(g); p.drawEllipse(core)
    shine = QPainterPath(); shine.addEllipse(core.adjusted(core.width() * 0.12, core.height() * 0.04,
                                                           -core.width() * 0.12, -core.height() * 0.5))
    p.fillPath(shine, QColor(255, 255, 255, 55))
    p.setFont(fa_font(core.height() * 0.58))
    p.setPen(QColor(0, 0, 0, 70)); p.drawText(core.translated(0.8, 1.4), Qt.AlignCenter, glyph)
    p.setPen(WHITE); p.drawText(core, Qt.AlignCenter, glyph)


def item_badge_pixmap(key, px):
    """The item badge rendered to a crisp pixmap (for overlays that take an image)."""
    cache = f"badge:{key}:{px}"
    if cache not in _PIX:
        dpr = 2
        pm = QPixmap(px * dpr, px * dpr); pm.setDevicePixelRatio(dpr); pm.fill(Qt.transparent)
        p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing)
        draw_item_badge(p, QRectF(1, 1, px - 4, px - 4), key); p.end()
        _PIX[cache] = pm
    return _PIX[cache]


def portrait_source(pm, aspect):
    """Source rect of a portrait cropped to aspect (w/h), keeping faces near the top."""
    w, h = pm.width(), pm.height()
    if w / h > aspect:          # too wide: trim the sides
        nw = h * aspect
        return QRectF((w - nw) / 2, 0, nw, h)
    nh = w / aspect             # too tall: trim mostly from the bottom
    return QRectF(0, (h - nh) * 0.4, w, nh)


# Fighter image -> series symbol in img/series (franchise of each base fighter).
FIGHTER_SERIES = {
    "bayonetta": "bayonetta", "bowser": "mario", "bowserjr": "mario", "captainfalcon": "f_zero",
    "chrom": "fire_emblem", "cloud": "final_fantasy", "corrin": "fire_emblem", "daisy": "mario",
    "darkpit": "kid_icarus", "darksamus": "metroid", "diddykong": "dk", "dk": "dk",
    "drmario": "mario", "duckhuntduo": "duck_hunt", "falco": "star_fox", "fox": "star_fox",
    "ganondorf": "zelda", "greninja": "pokemon", "iceclimbers": "ice_climber", "ike": "fire_emblem",
    "incineroar": "pokemon", "inkling": "splatoon", "isabelle": "animal_crossing",
    "jigglypuff": "pokemon", "ken": "street_fighter", "kingdedede": "kirby", "kingkrool": "dk",
    "kirby": "kirby", "link": "zelda", "littlemac": "punch_out", "lucario": "pokemon",
    "lucas": "earthbound", "lucina": "fire_emblem", "luigi": "mario", "mario": "mario",
    "marth": "fire_emblem", "megaman": "mega_man", "metaknight": "kirby", "mewtwo": "pokemon",
    "mrgameandwatch": "game_and_watch", "ness": "earthbound", "olimar": "pikmin",
    "pacman": "pac_man", "palutena": "kid_icarus", "peach": "mario", "pichu": "pokemon",
    "pikachu": "pokemon", "pit": "kid_icarus", "pokemontrainer": "pokemon",
    "richter": "castlevania", "ridley": "metroid", "rob": "rob", "robin": "fire_emblem",
    "rosalinaandluma": "mario", "roy": "fire_emblem", "ryu": "street_fighter", "samus": "metroid",
    "sheik": "zelda", "shulk": "xenoblade", "simon": "castlevania", "snake": "metal_gear",
    "sonic": "sonic", "toonlink": "zelda", "villager": "animal_crossing", "wario": "wario",
    "wiifittrainer": "wii_fit", "wolf": "star_fox", "yoshi": "yoshi", "younglink": "zelda",
    "zelda": "zelda", "zerosuitsamus": "metroid",
}


def grayscale(pm):
    """Grey copy of a pixmap that keeps its transparency."""
    if pm.isNull():
        return QPixmap()
    img = pm.toImage().convertToFormat(QImage.Format_ARGB32)
    gray = img.convertToFormat(QImage.Format_Grayscale8).convertToFormat(QImage.Format_ARGB32)
    gray.setAlphaChannel(img.convertToFormat(QImage.Format_Alpha8))
    return QPixmap.fromImage(gray)


def series_mark(img):
    """Series symbol of a fighter recoloured to white (alpha kept), or a null pixmap."""
    key = "mark:" + img
    if key not in _PIX:
        src = pixmap(f"series/{FIGHTER_SERIES.get(img, '')}.png")
        pm = QPixmap()
        if not src.isNull():
            pm = QPixmap(src.size()); pm.fill(Qt.transparent)
            p = QPainter(pm); p.drawPixmap(0, 0, src)
            p.setCompositionMode(QPainter.CompositionMode_SourceIn); p.fillRect(pm.rect(), WHITE); p.end()
        _PIX[key] = pm
    return _PIX[key]


def fit_pixmap_rect(src, box, max_scale=1.6):
    """Aspect-preserving rect for a pixmap in box, centred, never scaled past max_scale."""
    k = min(box.width() / max(1, src.width()), box.height() / max(1, src.height()), max_scale)
    w, h = src.width() * k, src.height() * k
    return QRectF(box.center().x() - w / 2, box.center().y() - h / 2, w, h)


def fmt_duration(sec):
    h, rem = divmod(int(sec), 3600)
    return f"{h:,}h {rem // 60:02d}m"


# ============================================================== model ======
class Store(QObject):
    changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.save = None
        self._dirty = False

    @property
    def loaded(self):
        return self.save is not None

    @property
    def dirty(self):
        # Comparing the whole save is costly; it is recomputed only when the
        # store changes (every mutation goes through load / edit / write).
        return self._dirty

    def _emit(self):
        self._dirty = self.save is not None and self.save.dirty
        self.changed.emit()

    def load(self, path):
        self.save = sd.SaveFile(path)
        self._emit()

    def edit(self, fn):
        fn(self.save)
        self._emit()

    def write(self):
        dest = self.save.save()
        self._emit()
        return dest


ARROWS = (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down)


def spatial_focus(container, widgets, key):
    """Move focus to the nearest widget in the arrow's direction."""
    if not widgets:
        return False
    cur = next((b for b in widgets if b.hasFocus()), None)
    if cur is None:
        widgets[0].setFocus(Qt.TabFocusReason)
        return True
    geo = lambda w: QRect(w.mapTo(container, QPoint(0, 0)), w.size())
    c = geo(cur).center()
    dx, dy = {Qt.Key_Left: (-1, 0), Qt.Key_Right: (1, 0), Qt.Key_Up: (0, -1), Qt.Key_Down: (0, 1)}[key]
    best, best_d = None, 1e9
    for b in widgets:
        if b is cur:
            continue
        v = geo(b).center() - c
        along = v.x() * dx + v.y() * dy
        if along <= 4:
            continue
        d = along + (abs(v.x() * dy) + abs(v.y() * dx)) * 2.5
        if d < best_d:
            best, best_d = b, d
    if best:
        best.setFocus(Qt.TabFocusReason)
    return best is not None


# ============================================================ buttons ======
class AnimButton(QAbstractButton):
    """Button with animated hover (t), press (pt) and flash (ft) progress."""

    def __init__(self, parent=None, title="", desc=""):
        super().__init__(parent)
        self.t = self.pt = self.ft = 0.0
        self.title, self.desc = title, desc
        self.sfx = "select"
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.clicked.connect(lambda: play(self.sfx) if self.sfx else None)

    def cursor_rect(self):
        return QRectF(self.rect()).adjusted(10, 10, -10, -10)

    def cursor_slant(self):
        return SLANT

    def _set(self, attr):
        def f(v):
            setattr(self, attr, v); self.update()
        return f

    def hover_to(self, on):
        tween(self, "hover", self.t, 1.0 if on else 0.0, 170 if on else 260, self._set("t"))

    def enterEvent(self, e):
        self.hover_to(True)
        if STATUS and self.desc:
            STATUS.describe(self.desc)
        if self.focusPolicy() & Qt.TabFocus and self.isActiveWindow() and not self.hasFocus():
            self.setFocus(Qt.MouseFocusReason)   # mouse and pad share one cursor

    def leaveEvent(self, e):
        if not self.hasFocus():
            self.hover_to(False)
        if STATUS:
            STATUS.describe(None)

    def focusInEvent(self, e):
        self.hover_to(True)
        if STATUS and self.desc:
            STATUS.describe(self.desc)
        if e.reason() in (Qt.MouseFocusReason, Qt.TabFocusReason, Qt.BacktabFocusReason):
            play("move")
        super().focusInEvent(e)

    def focusOutEvent(self, e):
        if not self.underMouse():
            self.hover_to(False)
        super().focusOutEvent(e)

    def mousePressEvent(self, e):
        tween(self, "press", self.pt, 1.0, 70, self._set("pt"))
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        tween(self, "press", self.pt, 0.0, 320, self._set("pt"), QEasingCurve.OutBack)
        super().mouseReleaseEvent(e)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.pulse(); self.click()
        elif e.key() in ARROWS:
            e.ignore()   # spatial navigation is done by the page / overlay
        else:
            super().keyPressEvent(e)

    def pulse(self):
        tween(self, "flash", 1.0, 0.0, 520, self._set("ft"))

    # Idle buttons are rendered once into a pixmap and reused: the animated
    # background repaints them many times per second.
    def idle(self):
        return self.t < 0.002 and self.pt < 0.002 and self.ft < 0.002 and getattr(self, "pop", 0.0) < 0.002

    def cache_key(self):
        return (self.width(), self.height(), self.devicePixelRatioF(), self.text(), self.isEnabled())

    def paintEvent(self, _):
        if not self.idle():
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing); p.setRenderHint(QPainter.SmoothPixmapTransform)
            self.draw(p)
            return
        key = self.cache_key()
        if self.__dict__.get("_ckey") != key:
            dpr = self.devicePixelRatioF()
            pm = QPixmap(int(self.width() * dpr), int(self.height() * dpr))
            pm.setDevicePixelRatio(dpr); pm.fill(Qt.transparent)
            q = QPainter(pm)
            q.setRenderHint(QPainter.Antialiasing); q.setRenderHint(QPainter.SmoothPixmapTransform)
            self.draw(q)
            q.end()
            self._ckey, self._cpix = key, pm
        QPainter(self).drawPixmap(0, 0, self._cpix)

    def draw(self, p):
        pass

    def transform(self, p, r):
        """Lift on hover, squash on press."""
        c = r.center()
        s = 1.0 + 0.02 * self.t - 0.05 * self.pt
        p.translate(c.x(), c.y() - 3 * self.t + 2 * self.pt)
        p.scale(s, s)
        p.translate(-c.x(), -c.y())


class SlantButton(AnimButton):
    """Red slanted menu button: icon | label ............ [value chip]."""

    def __init__(self, text, parent, glyph=None, pix=None, value=None, desc="", label_px=None, badge=None):
        super().__init__(parent, text, desc)
        self.setText(text)
        self.glyph, self.pix, self.value, self.badge = glyph, pix, value, badge
        self.label_px = label_px
        # sprites with an opaque square background fill the whole badge
        self.pix_opaque = bool(pix and not pix.isNull() and pix.toImage().pixelColor(0, 0).alpha() == 255)

    def cache_key(self):
        return super().cache_key() + (self.value() if self.value else None, self.label_px)

    def draw(self, p):
        r = QRectF(self.rect()).adjusted(10, 10, -10, -10)
        self.transform(p, r)
        on = self.isEnabled()
        path = para_path(r)
        glow(p, path, YELLOW, radius=9, strength=210 * self.t)
        p.fillPath(para_path(r.translated(3, 4)), QColor(0, 0, 0, 60))
        color = "#0878dc" if type(self.parentWidget()).__name__ == "ItemsPage" else "#ed1929"
        facets(p, r, color if on else "#696970")
        if self.t > 0.01:
            p.fillPath(path, QColor(255, 255, 255, int(25 * self.t)))
        if self.ft > 0.01:
            p.fillPath(path, QColor(255, 244, 160, int(170 * self.ft)))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(WHITE if self.t > 0.5 else QColor("#121212"), 3))
        p.drawPath(path)

        h = r.height()
        # icon
        icon_w = h * (0.86 if self.badge else 0.74)
        icon_rect = QRectF(r.left() + SLANT * 0.5, r.top(), icon_w, h)
        fg = WHITE if on else QColor("#a6a6ad")
        if self.badge:
            d = h * 0.8
            c = icon_rect.center()
            draw_item_badge(p, QRectF(c.x() - d / 2, c.y() - d / 2, d, d), self.badge, on)
        elif self.pix is not None and not self.pix.isNull():
            d = min(icon_w, h) * 0.86
            c = icon_rect.center()
            disc = QRectF(c.x() - d / 2, c.y() - d / 2, d, d)
            p.setPen(QPen(QColor(0, 0, 0, 70), 3)); p.setBrush(QColor(250, 250, 252))
            p.drawEllipse(disc.translated(1, 2))
            p.setPen(Qt.NoPen); p.drawEllipse(disc)
            clip = QPainterPath(); clip.addEllipse(disc.adjusted(2, 2, -2, -2))
            p.save(); p.setClipPath(clip, Qt.IntersectClip)
            inner = disc.adjusted(1, 1, -1, -1) if self.pix_opaque else disc.adjusted(d * 0.12, d * 0.12, -d * 0.12, -d * 0.12)
            self.draw_sprite(p, inner)
            p.restore()
            p.setPen(QPen(WHITE, 2.2)); p.setBrush(Qt.NoBrush); p.drawEllipse(disc)
        elif self.glyph == "SP":
            draw_sp(p, icon_rect.center(), h * 0.22, fg)
        elif self.glyph:
            p.setFont(fa_font(h * 0.42)); draw_text_shadow(p, icon_rect, Qt.AlignCenter, self.glyph, fg)
        dx = icon_rect.right()
        p.setPen(QPen(QColor(255, 255, 255, 170), 1.6))
        p.drawLine(QPointF(dx + 5, r.top() + h * 0.2), QPointF(dx - 1, r.bottom() - h * 0.2))

        # label first, then the value chip takes the remaining width
        right = r.right() - SLANT * 0.6
        left = dx + 11
        val = self.value() if self.value else None
        f = label_font(self.label_px or self.label_fit())
        lw = QFontMetricsF(f).horizontalAdvance(self.text())
        if val:
            room = max(right - left - lw - 14, 40)
            vf = fit_font(heavy_italic, val, room - 24, h * 0.5, 11)
            vw = QFontMetricsF(vf).horizontalAdvance(val) + 24
            chip = QRectF(right - vw - 2, r.top() + h * 0.18, vw, h * 0.64)
            p.setPen(Qt.NoPen); p.setBrush(QColor(0, 0, 0, 130)); p.drawPolygon(para(chip, 8))
            p.setFont(vf); p.setPen(lerp_color(YELLOW, QColor("#fff6b0"), self.ft))
            p.drawText(chip, Qt.AlignCenter, val)
            right = chip.left() - 4
        p.setFont(f)
        draw_text_shadow(p, QRectF(left, r.top(), right - left, h), Qt.AlignVCenter | Qt.AlignLeft, self.text(), fg)

    def draw_sprite(self, p, rect):
        """Scale the sprite to device pixels so it stays sharp on scaled screens."""
        dpr = p.device().devicePixelRatioF() if p.device() else 1.0
        side = max(1, int(min(rect.width(), rect.height()) * dpr))
        pm = self.pix.scaled(QSize(side, side), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        pm.setDevicePixelRatio(dpr)
        lw, lh = pm.width() / dpr, pm.height() / dpr
        p.drawPixmap(QPointF(rect.center().x() - lw / 2, rect.center().y() - lh / 2), pm)

    def label_fit(self):
        """Largest label size that leaves ~40% of the text area for the value."""
        r = QRectF(self.rect()).adjusted(10, 10, -10, -10)
        h = r.height()
        area = r.right() - SLANT * 0.6 - (r.left() + SLANT * 0.5 + h * 0.74 + 11)
        share = 0.6 if self.value else 1.0
        return fit_font(label_font, self.text(), area * share - 4, h * 0.44, 11).pixelSize()


class PlateButton(AnimButton):
    """Generic slanted plate. style: 'dark' | 'yellow' | 'red'."""

    def __init__(self, text, parent, glyph="", style="dark", desc="", slant=10):
        super().__init__(parent, text, desc)
        self.setText(text); self.glyph, self.style, self.slant = glyph, style, slant
        self.checked_look = False
        if glyph == G["back"]:
            self.sfx = "back"

    def cursor_rect(self):
        pad = 4 if self.height() < 50 else 10
        return QRectF(self.rect()).adjusted(pad, pad, -pad, -pad)

    def cursor_slant(self):
        return self.slant

    def cache_key(self):
        return super().cache_key() + (self.style, self.checked_look, self.glyph)

    def draw(self, p):
        pad = 4 if self.height() < 50 else 10
        r = QRectF(self.rect()).adjusted(pad, pad, -pad, -pad)
        self.transform(p, r)
        path = para_path(r, self.slant)
        style = "yellow" if self.checked_look else self.style
        on = self.isEnabled()
        if style == "yellow":
            glow(p, path, QColor("#ffb800"), radius=10, strength=110 + 90 * self.t)
            g = QLinearGradient(r.topLeft(), r.bottomLeft())
            g.setColorAt(0, QColor("#ffe729")); g.setColorAt(0.5, YELLOW); g.setColorAt(1, QColor("#efb800"))
            fg = QColor("#111")
        elif style == "red":
            glow(p, path, YELLOW, radius=8, strength=200 * self.t)
            g = QLinearGradient(r.topLeft(), r.bottomRight())
            g.setColorAt(0, RED_TOP); g.setColorAt(0.55, RED_MID); g.setColorAt(1, RED_BOT)
            fg = WHITE
        else:
            glow(p, path, YELLOW, radius=7, strength=150 * self.t)
            g = QLinearGradient(r.topLeft(), r.bottomLeft())
            g.setColorAt(0, lerp_color(QColor("#232329"), QColor("#3a3a44"), self.t)); g.setColorAt(1, QColor("#0d0d10"))
            fg = WHITE if on else QColor("#77777f")
        p.fillPath(path, g)
        if style == "yellow":
            p.save(); p.setClipPath(path)
            sh = QLinearGradient(r.topLeft(), QPointF(r.left() + r.width() * 0.4, r.bottom()))
            sh.setColorAt(0, QColor(255, 255, 255, 120)); sh.setColorAt(0.5, QColor(255, 255, 255, 0))
            p.fillRect(QRectF(r.left(), r.top(), r.width(), r.height() * 0.55), sh)
            p.setPen(Qt.NoPen); p.setBrush(QColor(200, 130, 0, 60))
            p.drawPath(smash_ball_path(QPointF(r.right() - r.height() * 0.9, r.center().y()), r.height() * 0.42))
            p.restore()
        if self.ft > 0.01:
            p.fillPath(path, QColor(255, 255, 255, int(160 * self.ft)))
        p.setPen(QPen(QColor("#080808"), 3)); p.setBrush(Qt.NoBrush); p.drawPath(path)
        if self.t > 0.5:
            p.setPen(QPen(WHITE, 2)); p.drawPath(path)

        h = r.height()
        text = self.text()
        if text:
            gw = h * 0.95 if self.glyph else 0
            tf = fit_font(game_font, text, r.width() - gw - self.slant * 2 - 10, h * 0.48, 10)
            tw = QFontMetricsF(tf).horizontalAdvance(text)
            x0 = r.center().x() - (gw + tw) / 2
            if self.glyph:
                p.setFont(fa_font(h * 0.44)); p.setPen(fg)
                p.drawText(QRectF(x0, r.top(), gw, h), Qt.AlignCenter, self.glyph)
            p.setFont(tf)
            if style == "yellow":
                p.setPen(fg); p.drawText(QRectF(x0 + gw, r.top(), tw + 4, h), Qt.AlignVCenter | Qt.AlignLeft, text)
            else:
                draw_text_shadow(p, QRectF(x0 + gw, r.top(), tw + 4, h), Qt.AlignVCenter | Qt.AlignLeft, text, fg)
        else:
            p.setFont(fa_font(h * 0.46)); p.setPen(lerp_color(fg, YELLOW, self.t))
            p.drawText(r, Qt.AlignCenter, self.glyph)


class SlantTab(AnimButton):
    def __init__(self, text, glyph, parent):
        super().__init__(parent, text.title())
        self.setText(text.upper()); self.glyph = glyph
        self.setCheckable(True); self.setFocusPolicy(Qt.NoFocus)
        self.sfx = None
        self.st = 0.0
        self.toggled.connect(lambda on: tween(self, "sel", self.st, 1.0 if on else 0.0, 220, self._set("st")))

    def idle(self):
        return False

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(5, 6, -5, -5)
        path = para_path(r, 16)
        p.fillPath(path, lerp_color(QColor("#e5e5e5"), YELLOW, self.st))
        p.setPen(QPen(QColor("#080808"), 4)); p.setBrush(Qt.NoBrush); p.drawPath(path)
        h = r.height(); fg = QColor("#111111")
        icon_rect = QRectF(r.left() + 15, r.top(), h * 0.68, h)
        if self.glyph == "BALL":
            p.setPen(Qt.NoPen); p.setBrush(fg)
            p.drawPath(smash_ball_path(icon_rect.center(), h * 0.24))
        else:
            p.setFont(fa_font(h * 0.34)); p.setPen(fg)
            p.drawText(icon_rect, Qt.AlignCenter, self.glyph)
        tr = QRectF(icon_rect.right() + 2, r.top(), r.right() - icon_rect.right() - 18, h)
        p.setFont(fit_font(game_font, self.text().title(), tr.width(), 23))
        p.setPen(fg); p.drawText(tr, Qt.AlignCenter, self.text().title())
        if self.st > 0.5:
            p.setPen(Qt.NoPen); p.setBrush(fg)
            p.drawPolygon(QPolygonF([QPointF(r.right() - 14, r.top() + 10),
                                     QPointF(r.right() - 5, r.top() + 10),
                                     QPointF(r.right() - 11, r.top() + 18)]))


class KeyHint(QWidget):
    """Small rounded key cap, like the L / R hints on the Switch menus."""

    def __init__(self, key, parent):
        super().__init__(parent); self.key = key
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(QColor(255, 255, 255, 200), 1.6)); p.setBrush(QColor(0, 0, 0, 170))
        p.drawRoundedRect(r, 6, 6)
        p.setFont(label_font(r.height() * 0.66, QFont.Black)); p.setPen(WHITE)
        p.drawText(r, Qt.AlignCenter, self.key)


class Cursor(QWidget):
    """The selection cursor: a pulsing yellow outline that glides to the focused button."""

    def __init__(self, win):
        super().__init__(win)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setGeometry(0, 0, W, H)
        self.target = None
        self.cur = self.src = self.drawn = QRectF()
        self.slant, self.k, self.alpha, self.pulse = SLANT, 1.0, 0.0, 0.0
        self.follow = QTimer(self); self.follow.timeout.connect(self.refresh)
        self.follow_until = 0.0
        tween(self, "pulse", 0, 1, 1100, self._pulse, QEasingCurve.Linear, loops=-1)

    def _pulse(self, v):
        self.pulse = v
        if self.alpha > 0.01:
            self.repaint_area()

    def target_rect(self):
        t = self.target
        if t is None or sip.isdeleted(t) or not t.isVisible():
            return None
        r = t.cursor_rect()
        tl = t.mapTo(self.parentWidget(), QPoint(int(r.left()), int(r.top())))
        return QRectF(tl.x(), tl.y(), r.width(), r.height())

    def track(self, w):
        ok = (isinstance(w, AnimButton) and not sip.isdeleted(w) and w.window() is self.window()
              and bool(w.focusPolicy() & Qt.TabFocus))
        if not ok:
            self.target = None
            tween(self, "alpha", self.alpha, 0.0, 140, self._alpha)
            return
        self.raise_()
        self.target, self.slant = w, w.cursor_slant()
        tr = self.target_rect()
        if tr is None:
            return
        if self.alpha < 0.05 or self.cur.isNull():
            self.cur = self.src = tr; self.k = 1.0
        else:
            self.src = QRectF(self.cur)
            tween(self, "k", 0.0, 1.0, 170, self._k, QEasingCurve.OutCubic)
        tween(self, "alpha", self.alpha, 1.0, 120, self._alpha)
        self.follow_until = time.monotonic() + 0.55
        self.follow.start(16)

    def _alpha(self, v):
        self.alpha = v; self.repaint_area()

    def _k(self, v):
        self.k = v; self.refresh()

    def refresh(self):
        tr = self.target_rect()
        if tr is not None:
            k = self.k
            self.cur = QRectF(lerp(self.src.left(), tr.left(), k), lerp(self.src.top(), tr.top(), k),
                              lerp(self.src.width(), tr.width(), k), lerp(self.src.height(), tr.height(), k))
        if time.monotonic() > self.follow_until and self.k >= 1.0:
            self.follow.stop()
        self.repaint_area()

    def repaint_area(self):
        area = self.cur.adjusted(-34, -24, 40, 40)
        if not self.drawn.isNull():
            area = area.united(self.drawn)
        self.drawn = self.cur.adjusted(-34, -24, 40, 40)
        self.update(area.toAlignedRect())

    def paintEvent(self, _):
        if self.alpha <= 0.01 or self.cur.isNull():
            return
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        p.setOpacity(max(0.0, min(1.0, self.alpha)))
        s = 0.5 + 0.5 * math.sin(self.pulse * 2 * math.pi)
        r = self.cur.adjusted(-3 - 2 * s, -3 - 2 * s, 3 + 2 * s, 3 + 2 * s)
        path = para_path(r, self.slant)
        glow(p, path, YELLOW, radius=9, strength=80 + 110 * s)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 230), 6)); p.drawPath(path)
        p.setPen(QPen(YELLOW, 3.5)); p.drawPath(path)
        if isinstance(self.target, FighterTile):
            # P1 token resting on the tile's top-right corner, kept inside the window.
            rad = 11.5
            c = QPointF(min(W - rad - 4, r.right() - 4), max(rad + 2, r.top() + 4 - 2 * s))
            p.setPen(Qt.NoPen); p.setBrush(QColor(0, 0, 0, 120)); p.drawEllipse(c + QPointF(1.5, 2), rad, rad)
            p.setPen(QPen(WHITE, 2.5)); p.setBrush(QColor("#e8141e")); p.drawEllipse(c, rad, rad)
            p.setFont(label_font(14, QFont.Black)); p.setPen(WHITE)
            p.drawText(QRectF(c.x() - rad, c.y() - rad, 2 * rad, 2 * rad), Qt.AlignCenter, "P1")
            return
        # pointer bobbing on the left edge
        cy = r.center().y()
        x = r.left() + self.slant * 0.5 - 6 - 5 * s
        tri = QPolygonF([QPointF(x - 16, cy - 11), QPointF(x, cy), QPointF(x - 16, cy + 11)])
        p.setPen(QPen(QColor("#111"), 2.5)); p.setBrush(YELLOW); p.drawPolygon(tri)


# ======================================================= backgrounds =======
class Panel(QWidget):
    """Silver geometric background shared by the editor screens."""

    def __init__(self, parent):
        super().__init__(parent)
        self.phase = 0.0
        self.streaks = make_streaks(21, 12)

    def paintEvent(self, _):
        dpr = self.devicePixelRatioF()
        key = (self.width(), self.height(), dpr)
        if self.__dict__.get("_bkey") != key:
            pm = QPixmap(int(self.width() * dpr), int(self.height() * dpr)); pm.setDevicePixelRatio(dpr)
            q = QPainter(pm); q.setRenderHint(QPainter.Antialiasing)
            self.paint_static(q)
            q.end()
            self._bkey, self._bpix = key, pm
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        p.drawPixmap(0, 0, self._bpix)
        draw_streaks(p, self.width(), self.height(), self.streaks, self.phase, 1.2)

    def paint_static(self, p):
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor("#e6e7e9"))
        p.setPen(Qt.NoPen)
        for i in range(6):
            x = w * i / 5
            p.setBrush(QColor("#d3d5d9") if i % 2 else QColor("#f5f5f5"))
            p.drawPolygon(QPolygonF([QPointF(x, 0), QPointF(x + w * 0.30, 0),
                                     QPointF(x - h * 0.65, h)]))
        p.setBrush(QColor(255, 255, 255, 100))
        p.drawPath(smash_ball_path(QPointF(w * 0.8, h * 0.65), h * 0.55))
        p.setPen(QPen(QColor("#111111"), 4)); p.drawLine(0, 2, w, 2)


class DarkCard(QWidget):
    """Silver content card with a black title band."""

    def __init__(self, parent, title=""):
        super().__init__(parent); self.title = title

    def paintEvent(self, _):
        dpr = self.devicePixelRatioF()
        key = (self.width(), self.height(), dpr)
        if self.__dict__.get("_ckey") != key:
            pm = QPixmap(int(self.width() * dpr), int(self.height() * dpr)); pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.transparent)
            q = QPainter(pm); q.setRenderHint(QPainter.Antialiasing); self.draw(q); q.end()
            self._ckey, self._cpix = key, pm
        QPainter(self).drawPixmap(0, 0, self._cpix)

    def draw(self, p):
        r = QRectF(self.rect()).adjusted(3, 3, -3, -3)
        facets(p, r, "#f3f3f3", 14)
        p.save(); p.setClipPath(para_path(r, 14))
        p.fillRect(QRectF(r.left(), r.top(), r.width(), 47), QColor("#161616"))
        p.restore()
        if self.title:
            p.setFont(game_font(18)); p.setPen(WHITE)
            p.drawText(QRectF(30, 12, r.width() - 60, 26), Qt.AlignLeft | Qt.AlignVCenter, self.title)


# ============================================================ status =======
class StatusBar(QWidget):
    def __init__(self, store, parent):
        super().__init__(parent)
        self.store = store
        self.desc = None
        self.default = "Choose a section."
        self.pulse = 0.0
        self._pulsing = False
        store.changed.connect(self.on_change)

    def on_change(self):
        if self.store.dirty and not self._pulsing:
            self._pulsing = True
            tween(self, "pulse", 0, 1, 1400, self._set_pulse, QEasingCurve.Linear, loops=-1)
        elif not self.store.dirty and self._pulsing:
            self._pulsing = False
            self.__dict__["_tweens"]["pulse"].stop(); self.pulse = 0.0
        self.update()

    def _set_pulse(self, v):
        self.pulse = v; self.update(QRect(self.width() - 180, 0, 180, self.height()))

    def describe(self, text):
        self.desc = text; self.update()

    def prompts(self):
        pad = PAD is not None and PAD.connected
        ok, back = ("CROSS", "CIRCLE") if pad else ("ENTER", "ESC")
        win = self.window()
        if any(isinstance(c, Overlay) and not c.closing for c in win.children()):
            return [((ok,), "CONFIRM"), ((back,), "BACK")]
        if getattr(win, "current", None) is None:
            return [((ok,), "SELECT"), ((back,), "QUIT")]
        return [((ok,), "OK"), ((back,), "MENU"), ((("L1", "R1") if pad else ("Q", "E")), "SECTION")]

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0, QColor("#1c1c22")); g.setColorAt(1, QColor("#08080a"))
        p.fillRect(self.rect(), g)
        p.setPen(QPen(QColor("#e3001b"), 3)); p.drawLine(0, 1, w, 1)
        p.setPen(Qt.NoPen); p.setBrush(WHITE)
        p.drawPath(smash_ball_path(QPointF(M + 20, h / 2), 15))
        p.setPen(QPen(QColor(255, 255, 255, 150), 2)); p.drawLine(QPointF(M + 52, h - 10), QPointF(M + 60, 10))
        box = QRectF(w - M - 330, 6, 330, h - 12)
        # button prompts, right-aligned before the file box
        x = box.left() - 18
        for keys, label in reversed(self.prompts()):
            p.setFont(heavy_italic(19))
            lw = QFontMetricsF(p.font()).horizontalAdvance(label)
            x -= lw
            p.setPen(WHITE); p.drawText(QRectF(x, 0, lw + 2, h), Qt.AlignVCenter | Qt.AlignLeft, label)
            x -= 6
            for key in reversed(keys):
                x -= draw_key(p, x, h / 2, key, right_align=True) + 3
            x -= 16
        msg = self.desc or self.default
        f = label_font(20, QFont.DemiBold, True)
        avail = x - (M + 74) - 10
        p.setFont(f); p.setPen(WHITE)
        p.drawText(QRectF(M + 74, 0, avail, h), Qt.AlignVCenter | Qt.AlignLeft,
                   QFontMetricsF(f).elidedText(msg, Qt.ElideRight, avail))

        bp = para_path(box, 14)
        p.fillPath(bp, QColor("#141418")); p.setBrush(Qt.NoBrush); p.setPen(silver_pen(box, 1.6, 200)); p.drawPath(bp)
        div = box.left() + 200
        p.setPen(QPen(QColor(255, 255, 255, 120), 1.6))
        p.drawLine(QPointF(div + 6, box.top() + 6), QPointF(div - 2, box.bottom() - 6))
        p.setFont(fa_font(16)); p.setPen(WHITE)
        p.drawText(QRectF(box.left() + 18, box.top(), 26, box.height()), Qt.AlignCenter, G["open"])
        s = self.store.save
        if s:
            parts = s.path.split("/")
            short = "Ryujinx · system_data.bin" if s.path == sd.RYUJINX_SAVE else "/".join(parts[-2:])
        else:
            short = "No file"
        p.setFont(label_font(17)); p.setPen(WHITE if s else QColor("#8b8b95"))
        p.drawText(QRectF(box.left() + 50, box.top(), div - box.left() - 56, box.height()), Qt.AlignVCenter | Qt.AlignLeft,
                   QFontMetricsF(p.font()).elidedText(short, Qt.ElideLeft, div - box.left() - 56))
        if not s:
            icon, color, label = G["question"], QColor("#8b8b95"), "NO FILE"
        elif s.dirty:
            a = 0.55 + 0.45 * (0.5 + 0.5 * math.cos(self.pulse * 2 * math.pi))
            icon, color, label = G["warn"], QColor(255, 212, 0, int(255 * a)), "UNSAVED"
        else:
            icon, color, label = G["check"], QColor("#3ddc6a"), "SAVED"
        p.setFont(fa_font(16)); p.setPen(color)
        p.drawText(QRectF(div + 8, box.top(), 24, box.height()), Qt.AlignCenter, icon)
        p.setFont(heavy_italic(21))
        p.drawText(QRectF(div + 36, box.top(), box.right() - div - 50, box.height()), Qt.AlignVCenter | Qt.AlignLeft, label)


def draw_key(p, x_right, cy, key, right_align=True):
    """Draw a button glyph ending at x_right; returns its width."""
    if key in ("CROSS", "CIRCLE"):
        d = 24
        c = QPointF(x_right - d / 2, cy)
        p.setPen(QPen(QColor(255, 255, 255, 220), 1.6)); p.setBrush(QColor(0, 0, 0, 170)); p.drawEllipse(c, d / 2, d / 2)
        if key == "CROSS":
            p.setPen(QPen(QColor("#8fb4ff"), 2.4))
            p.drawLine(QPointF(c.x() - 5, cy - 5), QPointF(c.x() + 5, cy + 5))
            p.drawLine(QPointF(c.x() + 5, cy - 5), QPointF(c.x() - 5, cy + 5))
        else:
            p.setPen(QPen(QColor("#ff7a8a"), 2.4)); p.setBrush(Qt.NoBrush); p.drawEllipse(c, 5.5, 5.5)
        return d
    f = label_font(15, QFont.Black)
    tw = QFontMetricsF(f).horizontalAdvance(key)
    kw = max(24, tw + 12)
    r = QRectF(x_right - kw, cy - 12, kw, 24)
    p.setPen(QPen(QColor(255, 255, 255, 200), 1.4)); p.setBrush(QColor(0, 0, 0, 170)); p.drawRoundedRect(r, 6, 6)
    p.setFont(f); p.setPen(WHITE); p.drawText(r, Qt.AlignCenter, key)
    return kw


# ============================================================= toast =======
class Toast(QWidget):
    """Slanted banner that slides in from the right."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.text, self.kind, self.k, self.icon = "", "ok", 0.0, None
        self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.timeout.connect(self.hide_toast)
        self.hide()

    def show_toast(self, text, kind="ok", ms=2600, icon=None):
        self.text, self.kind, self.icon = text, kind, icon
        if kind == "error":
            play("error")
        f = heavy_italic(24)
        w = int(QFontMetricsF(f).horizontalAdvance(text) + 110)
        self.setGeometry(W - w + 10, 3, w, 50)
        self.show(); self.raise_()
        tween(self, "k", self.k, 1.0, 380, self._k, QEasingCurve.OutBack)
        self.timer.start(ms)

    def hide_toast(self):
        tween(self, "k", self.k, 0.0, 260, self._k, QEasingCurve.InCubic, done=self.hide)

    def _k(self, v):
        self.k = v; self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        off = (1 - self.k) * (self.width() + 20)
        r = QRectF(off + 4, 4, self.width() - 4, self.height() - 8)
        path = para_path(r, 18)
        p.fillPath(path.translated(4, 4), QColor(0, 0, 0, 90))
        if self.kind == "ok":
            g = QLinearGradient(r.topLeft(), r.bottomLeft())
            g.setColorAt(0, QColor("#ffe729")); g.setColorAt(0.5, YELLOW); g.setColorAt(1, QColor("#efb800"))
            fg, icon = QColor("#111"), G["check"]
        else:
            g = QLinearGradient(r.topLeft(), r.bottomLeft())
            g.setColorAt(0, RED_TOP); g.setColorAt(1, RED_BOT)
            fg, icon = WHITE, G["warn"]
        p.fillPath(path, g)
        p.setPen(QPen(WHITE, 2.5)); p.drawPath(path)
        pm = self.icon
        if pm is not None and not pm.isNull():
            ir = QRectF(r.left() + 20, r.center().y() - 17, 34, 34)
            p.drawPixmap(ir, pm, QRectF(pm.rect()))
        else:
            p.setFont(fa_font(20)); p.setPen(fg)
            p.drawText(QRectF(r.left() + 22, r.top(), 34, r.height()), Qt.AlignCenter, icon)
        p.setFont(heavy_italic(24))
        p.drawText(QRectF(r.left() + 62, r.top(), r.width() - 70, r.height()), Qt.AlignVCenter | Qt.AlignLeft, self.text)


# =========================================================== overlays ======
class Overlay(QWidget):
    """Modal in-window dialog: dark scrim + slanted card that slides in."""

    CARD_W, CARD_H = 600, 320

    def __init__(self, win, title, glyph=""):
        super().__init__(win)
        self.win, self.title, self.glyph = win, title, glyph
        self.k = 0.0
        self.closing = False
        self.setGeometry(0, 0, W, H)
        self.card = QWidget(self)
        self.card.paintEvent = self.paint_card
        self.cx = (W - self.CARD_W) // 2
        self.cy = (H - self.CARD_H) // 2 + 10
        self.card.setGeometry(self.cx, self.cy, self.CARD_W, self.CARD_H)
        self.setFocusPolicy(Qt.StrongFocus)
        self.prev_focus = QApplication.focusWidget()

    def open(self):
        self.show(); self.raise_(); self.setFocus()
        tween(self, "k", 0.0, 1.0, 420, self._k, QEasingCurve.OutBack)
        focus = self.first_focus()
        if focus:
            QTimer.singleShot(0, focus.setFocus)
        return self

    def first_focus(self):
        return None

    def _k(self, v):
        self.k = v
        self.card.move(int(self.cx + (1 - v) * 140), self.cy)
        self.update()

    def close_overlay(self):
        if self.closing:
            return
        self.closing = True
        tween(self, "k", self.k, 0.0, 170, self._k, QEasingCurve.InCubic, done=self.deleteLater)
        prev = self.prev_focus
        if prev is not None and not sip.isdeleted(prev) and prev.isVisible() and not self.isAncestorOf(prev):
            prev.setFocus()
        elif self.win.hub.isVisible():
            self.win.hub.setFocus()
        else:
            self.win.setFocus()
        if STATUS:
            STATUS.update()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            play("back")
            self.close_overlay()
        elif e.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.accept()
        elif e.key() in ARROWS:
            btns = [b for b in self.card.findChildren(AnimButton) if b.focusPolicy() & Qt.TabFocus]
            spatial_focus(self.card, btns, e.key())
        else:
            e.accept()   # modal: never leak keys to the page below

    def accept(self):
        self.close_overlay()

    def mousePressEvent(self, e):
        if not self.card.geometry().contains(e.pos()):
            play("back")
            self.close_overlay()

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(5, 5, 8, int(175 * max(0.0, min(1.0, self.k)))))

    def paint_card(self, _):
        p = QPainter(self.card); p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.card.rect()).adjusted(4, 4, -8, -8)
        path = para_path(r, 26)
        p.fillPath(path.translated(6, 7), QColor(0, 0, 0, 120))
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0, QColor("#fafafa")); g.setColorAt(1, QColor("#dadcde"))
        p.fillPath(path, g)
        # red title band
        p.save(); p.setClipPath(path)
        band = QLinearGradient(0, 0, r.width(), 0)
        band.setColorAt(0, QColor("#e3001b")); band.setColorAt(1, QColor("#9a0013"))
        p.fillRect(QRectF(r.left(), r.top(), r.width(), 54), band)
        halftone(p, r.left() + 20, r.top(), 30, 7, QColor(255, 255, 255, 50))
        p.setBrush(QColor(255, 255, 255, 25)); p.setPen(Qt.NoPen)
        p.drawPath(smash_ball_path(QPointF(r.right() - 90, r.bottom() - 60), 110))
        p.restore()
        p.setPen(QPen(QColor("#080808"), 4)); p.setBrush(Qt.NoBrush); p.drawPath(path)
        p.setPen(QPen(YELLOW, 3)); p.drawLine(QPointF(r.left() + 18, r.top() + 54), QPointF(r.right() - 4, r.top() + 54))
        x = r.left() + 40
        if self.glyph == "SP":
            draw_sp(p, QPointF(x + 12, r.top() + 27), 13, WHITE); x += 36
        elif isinstance(self.glyph, QPixmap):
            dpr = self.card.devicePixelRatioF()
            pm = self.glyph.scaled(int(34 * dpr), int(34 * dpr), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            pm.setDevicePixelRatio(dpr)
            p.drawPixmap(QPointF(x, r.top() + 10), pm); x += 44
        elif self.glyph:
            p.setFont(fa_font(22)); p.setPen(WHITE)
            p.drawText(QRectF(x, r.top(), 30, 54), Qt.AlignCenter, self.glyph); x += 40
        p.setFont(heavy_italic(30))
        draw_text_shadow(p, QRectF(x, r.top(), r.width() - x, 54), Qt.AlignVCenter | Qt.AlignLeft, self.title.upper())
        self.paint_extra(p, r)

    def paint_extra(self, p, r):
        pass

    def add_buttons(self, specs, y=None, h=54):
        """specs: [(text, glyph, style, callback)] laid out right-aligned at the bottom."""
        y = self.CARD_H - h - 22 if y is None else y
        x = self.CARD_W - 40
        made = []
        for text, glyph, style, cb in reversed(specs):
            f = heavy_italic(h * 0.55)
            bw = int(QFontMetricsF(f).horizontalAdvance(text) + (h if glyph else 0) + 48)
            x -= bw
            b = PlateButton(text, self.card, glyph, style, slant=14)
            b.setGeometry(x, y, bw, h)
            b.clicked.connect(cb)
            made.append(b)
            x -= 4
        return list(reversed(made))


class ConfirmOverlay(Overlay):
    CARD_W, CARD_H = 680, 290

    def __init__(self, win, title, message, buttons, glyph=G["warn"]):
        """buttons: [(text, glyph, style, callback)] -- callbacks run after closing."""
        super().__init__(win, title, glyph)
        lab = QLabel(message, self.card)
        lab.setWordWrap(True); lab.setTextFormat(Qt.RichText)
        lab.setStyleSheet("color: #191919; font-family: 'Barlow Condensed'; font-size: 21px; font-weight: 600;")
        lab.setGeometry(48, 74, self.CARD_W - 110, 120)
        lab.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        def wrap(cb):
            def run():
                self.close_overlay()
                if cb:
                    cb()
            return run
        self.btns = self.add_buttons([(t, g, s, wrap(cb)) for t, g, s, cb in buttons])
        self.default = self.btns[0] if self.btns else None

    def first_focus(self):
        return self.default

    def accept(self):
        if self.default:
            self.default.click()


class NumberOverlay(Overlay):
    """Edit one numeric field: big value, -/+ step, 0 / MAX, confirm."""

    CARD_H = 330

    def __init__(self, win, field, current, on_confirm):
        glyph = item_badge_pixmap(field.key, 96) if field.key in ITEM_BADGES else field.glyph
        super().__init__(win, field.name, glyph)
        self.field, self.on_confirm = field, on_confirm
        self.spin = QSpinBox(self.card)
        self.spin.setRange(0, field.maximum); self.spin.setValue(current)
        self.spin.setGroupSeparatorShown(True)
        self.spin.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin.setAlignment(Qt.AlignCenter)
        self.spin.setSingleStep(1)
        self.spin.setStyleSheet(
            "QSpinBox { background: white; color: #111111; border: 3px solid #111111;"
            " border-radius: 0px; font-family: 'Barlow Condensed'; font-size: 58px; font-weight: 900;"
            " font-style: italic; selection-background-color: #e3001b; selection-color: white; }"
            "QSpinBox:focus { border: 3px solid #e3001b; }")
        cw = self.CARD_W
        self.spin.setGeometry(150, 78, cw - 310, 92)
        self.spin.installEventFilter(self)
        minus = PlateButton("", self.card, G["minus"], "red", desc=f"-{field.step:,}")
        minus.setGeometry(54, 86, 90, 78); minus.clicked.connect(lambda: self.bump(-field.step))
        plus = PlateButton("", self.card, G["plus"], "red", desc=f"+{field.step:,}")
        plus.setGeometry(cw - 156, 86, 90, 78); plus.clicked.connect(lambda: self.bump(field.step))
        for b in (minus, plus):
            b.setAutoRepeat(True); b.setAutoRepeatDelay(350); b.setAutoRepeatInterval(60)
            b.setFocusPolicy(Qt.NoFocus)
        zero = PlateButton("0", self.card, "", "dark"); zero.setGeometry(150, 178, 110, 44)
        zero.clicked.connect(lambda: self.set_to(0)); zero.setFocusPolicy(Qt.NoFocus)
        mx = PlateButton("MAX", self.card, G["bolt"], "dark"); mx.setGeometry(cw - 270, 178, 120, 44)
        mx.clicked.connect(lambda: self.set_to(field.maximum)); mx.setFocusPolicy(Qt.NoFocus)
        self.add_buttons([("CONFIRM", G["check"], "yellow", self.accept),
                          ("BACK", G["back"], "dark", self.close_overlay)])

    def first_focus(self):
        self.spin.selectAll()
        return self.spin

    def eventFilter(self, obj, e):
        if obj is self.spin and e.type() == e.KeyPress:
            k = e.key()
            if k in (Qt.Key_Return, Qt.Key_Enter):
                self.accept(); return True
            if k == Qt.Key_Escape:
                play("back"); self.close_overlay(); return True
            if k in (Qt.Key_Right, Qt.Key_Left):
                self.bump(self.field.step if k == Qt.Key_Right else -self.field.step); return True
            if k in (Qt.Key_Up, Qt.Key_Down):
                self.bump(1 if k == Qt.Key_Up else -1); return True
            if k == Qt.Key_PageUp:
                self.bump(self.field.step); return True
            if k == Qt.Key_PageDown:
                self.bump(-self.field.step); return True
        return False

    def bump(self, d):
        self.set_to(self.spin.value() + d)
        play("move")

    def set_to(self, v):
        self.spin.setValue(max(0, min(self.field.maximum, v)))

    def paint_extra(self, p, r):
        p.setFont(label_font(17, QFont.DemiBold, True)); p.setPen(QColor("#4a4a4a"))
        p.drawText(QRectF(54, 230, self.CARD_W - 120, 24), Qt.AlignLeft | Qt.AlignVCenter,
                   f"{self.field.desc} · max {self.field.maximum:,} · \u2190\u2192 \u00b1{self.field.step:,} · \u2191\u2193 \u00b11")

    def accept(self):
        self.spin.interpretText()
        v = self.spin.value()
        self.close_overlay()
        self.on_confirm(v)


class ChoiceOverlay(Overlay):
    CARD_W, CARD_H = 700, 380

    def __init__(self, win, title, glyph, options, current, on_pick):
        super().__init__(win, title, glyph)
        self.on_pick = on_pick
        self.buttons = []
        cols, bw, bh = 3, 196, 56
        for i, opt in enumerate(options):
            r, c = divmod(i, cols)
            b = PlateButton(opt, self.card, G["check"] if i == current else "", "dark", slant=12)
            b.checked_look = i == current
            b.setGeometry(46 + c * (bw + 10), 70 + r * (bh + 2), bw, bh)
            b.clicked.connect(lambda _=False, i=i: self.pick(i))
            self.buttons.append(b)
        self.current = current

    def first_focus(self):
        return self.buttons[self.current] if 0 <= self.current < len(self.buttons) else self.buttons[0]

    def keyPressEvent(self, e):
        k = e.key()
        moves = {Qt.Key_Left: -1, Qt.Key_Right: 1, Qt.Key_Up: -3, Qt.Key_Down: 3}
        if k in moves:
            cur = next((i for i, b in enumerate(self.buttons) if b.hasFocus()), self.current)
            nxt = max(0, min(len(self.buttons) - 1, cur + moves[k]))
            if nxt != cur:
                self.buttons[nxt].setFocus(Qt.TabFocusReason)
        else:
            super().keyPressEvent(e)

    def accept(self):
        cur = next((i for i, b in enumerate(self.buttons) if b.hasFocus()), None)
        if cur is not None:
            self.pick(cur)

    def pick(self, i):
        self.close_overlay()
        self.on_pick(i)


class HelpOverlay(Overlay):
    CARD_W, CARD_H = 720, 440

    def __init__(self, win):
        super().__init__(win, "How to use", G["help"])
        lab = QLabel(self.card)
        lab.setTextFormat(Qt.RichText); lab.setWordWrap(True); lab.setOpenExternalLinks(True)
        lab.setStyleSheet("color: #191919; font-family: 'Barlow Condensed'; font-size: 19px; font-weight: 600;")
        lab.setText(
            "<ol style='margin-left:-20px'>"
            "<li><b>Close the game in Ryujinx</b> (the emulator rewrites the save while it runs).</li>"
            "<li>Your Ryujinx save opens automatically. Use <b>OPEN SAVE</b> for another file.</li>"
            "<li>Edit anything, then press <b>SAVE</b> (Ctrl+S). Both Ryujinx slots are written.</li>"
            "<li>Every save first makes a backup (last 20 kept) — restore them in <b>BACKUPS</b>.</li></ol>"
            "<p><b>Keys:</b> arrows + Enter · Esc back · Q / E change section · Ctrl+O open · "
            "Ctrl+S save · M sound on/off · F1 help<br><b>Controller:</b> D-pad / stick · "
            "Cross = OK · Circle = back · L1 / R1 = section · Options = save · Share = help</p>"
            "<p style='color:#484848'>Based on Ultimate Smasher by "
            "<a style='color:#005cad' href='https://github.com/CapitanRetraso/Ultimate-Smasher'>Capitán Retraso</a>"
            " (GPL-3.0). Editing saves can corrupt them — keep backups.</p>")
        lab.setGeometry(46, 66, self.CARD_W - 100, 290)
        self.ok = self.add_buttons([("GOT IT", G["check"], "yellow", self.close_overlay)])[0]

    def first_focus(self):
        return self.ok


# ================================================================ hub ======
SECTION_DESC = {  # status-bar text for each section
    "GENERAL": "Gold, SP, hammers, tickets, language, milestones and Mii clothes",
    "ITEMS": "Snacks and Spirit Board battle items",
    "CHARACTERS": "Unlock or lock fighters on the roster",
    "STATS": "Records: battles, spirits, vault and online",
    "BACKUPS": "Automatic backups made on every save",
}

# Main menu: drawn in code on a virtual 1920x1080 canvas (see hub_geometry).
# name: (label, description, base colour, light colour, label tint, icon,
#        icon centre, icon px, label centre, label px)
HUB_TILES = {
    "CHARACTERS": ("Fighters", "Unlock or lock any fighter on the roster.",
                   "#c80d10", "#ff3c14", "#ffd9d2", "\uf0c0",
                   (400, 255), 150, (385, 468), 122),
    "ITEMS": ("Items", "Snacks and every Spirit Board battle item.",
              "#119c36", "#3fc85e", "#d2f7d6", "\uf0c3",
              (410, 755), 128, (400, 885), 104),
    "GENERAL": ("General", "Gold, SP, hammers, tickets, language and unlocks.",
                "#1567e0", "#2fa0ff", "#d6ebff", "\uf1de",
                (1380, 95), 112, (1385, 222), 92),
    "BACKUPS": ("Backups", "Automatic backups made on every save.",
                "#e22c78", "#ff5aa0", "#ffdbe8", "\uf187",
                (1478, 445), 92, (1478, 552), 80),
    "STATS": ("Stats", "Battle records: Smash, Spirits, Vault and Online.",
              "#e8960f", "#ffbf3a", "#fff1d4", "\uf091",
              (1235, 770), 112, (1240, 892), 96),
    "SAVE": ("", "Save changes to the save file (Ctrl+S).",
             "#e8960f", "#ffbf3a", "#fff1d4", "\uf0c7",
             (1688, 900), 66, None, 0),
}
RAIL = [  # icon, description
    ("\uf015", "Main menu"),
    ("\uf07c", "Open another save file (Ctrl+O)"),
    ("\uf028", "Sound on / off (M)"),
    ("\uf128", "Help and controls (F1)"),
    ("\uf011", "Quit Ultimate Smasher (Esc)"),
]


def round_font(px, weight=QFont.Black):
    f = QFont(ROUND_FONT); f.setPixelSize(max(1, int(px))); f.setWeight(weight)
    return f


def text_path(text, font, center):
    path = QPainterPath(); path.addText(0, 0, font, text)
    r = path.boundingRect()
    return path.translated(center.x() - r.center().x(), center.y() - r.center().y())


class Hub(QWidget):
    """Main menu in the style of the game's home screen, fully vector drawn."""

    def __init__(self, parent, on_open, info, on_back=None):
        super().__init__(parent)
        self.win, self.on_open, self.info, self.on_back = parent, on_open, info, on_back
        self.art = pixmap("hub-art.png")
        self.tile_info = {}
        self.hover = "CHARACTERS"
        self.rail_hover = None
        self.flash = {name: 0.0 for name in HUB_TILES}
        self.intro = 1.0
        self.angle = self._angle("CHARACTERS")
        self.pulse = 0.0
        self.busy = False
        self.clock_text = time.strftime("%H:%M")
        self._cache = self._disc = self._sel = None
        self.streaks = {name: make_streaks(i * 7 + 3, 6) for i, name in enumerate(HUB_TILES)}
        self.timer = QTimer(self); self.timer.timeout.connect(self._tick)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName("Main menu: Fighters, Items, General, Backups, Stats")

    # ------------------------------------------------------------ state --
    @staticmethod
    def _angle(name):
        c = hg.LABEL_C[name]
        return math.degrees(math.atan2(c.y() - hg.DISC_C.y(), c.x() - hg.DISC_C.x()))

    def _tick(self):
        # Only the pulsing frame of the selected tile animates: repaint just that.
        if self.hover and self.isVisible() and self.window().isActiveWindow():
            self.pulse = (self.pulse + 0.04) % 1.0
            self.update(self.view_rect(hg.TILES[self.hover].boundingRect().adjusted(-30, -30, 30, 30)))

    def view_rect(self, r):
        return hg.transform(self.width(), self.height()).mapRect(r).toAlignedRect()

    def showEvent(self, event):
        self.timer.start(40); super().showEvent(event)

    def hideEvent(self, event):
        self.timer.stop(); super().hideEvent(event)

    def invalidate(self):
        self._cache = None; self.update()

    def resizeEvent(self, event):
        self._cache = self._disc = self._sel = None
        super().resizeEvent(event)

    def tile_at(self, pos):
        return hg.tile_at(self.width(), self.height(), QPointF(pos))

    def rail_at(self, pos):
        return hg.rail_at(self.width(), self.height(), QPointF(pos), len(RAIL))

    def play_intro(self, ms=600):
        self.busy = False
        tween(self, "intro", 0.0, 1.0, ms, self._intro)

    def _intro(self, value):
        self.intro = value; self.update()

    def set_hover(self, name):
        if name == self.hover:
            return
        self.hover = name
        if name:
            start, end = self.angle, self._angle(name)
            end = start + ((end - start + 180) % 360 - 180)
            tween(self, "angle", start, end, 220, self._set_angle)
            play("move")
        self.update()

    def _set_angle(self, v):
        self.angle = v; self.update()

    # ------------------------------------------------------------ input --
    def mouseMoveEvent(self, event):
        rail = self.rail_at(event.pos())
        if rail != self.rail_hover:
            self.rail_hover = rail
            if rail is not None:
                play("move")
            self.update()
        name = self.tile_at(event.pos())
        if name:
            self.set_hover(name)
        self.setCursor(Qt.PointingHandCursor if name or rail is not None else Qt.ArrowCursor)

    def leaveEvent(self, event):
        self.rail_hover = None; self.update()

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        rail = self.rail_at(event.pos())
        if rail is not None:
            self.rail_action(rail)
            return
        name = self.tile_at(event.pos())
        if name:
            self.set_hover(name)
            self.activate(name)

    def keyPressEvent(self, event):
        key = event.key()
        if key in ARROWS:
            self.set_hover(hg.NEIGHBORS[self.hover or "CHARACTERS"].get(key, self.hover or "CHARACTERS"))
        elif key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space) and self.hover:
            self.activate(self.hover)
        elif key == Qt.Key_Escape and self.on_back:
            self.on_back()
        else:
            super().keyPressEvent(event)

    def focusInEvent(self, event):
        if not self.hover:
            self.set_hover("CHARACTERS")

    def rail_action(self, i):
        win = self.win
        if i == 0:
            play("select")
        elif i == 1:
            play("select"); win.open_dialog()
        elif i == 2:
            on = SFX.toggle() if SFX else False
            win.toast("SOUND ON" if on else "SOUND OFF")
            self.invalidate()
        elif i == 3:
            play("select"); HelpOverlay(win).open()
        elif i == 4:
            win.ask_quit()

    def activate(self, name):
        if self.busy:
            return
        play("select")
        tween(self, "f" + name, 1.0, 0.0, 260, lambda v: self._flash(name, v))
        if name == "SAVE":
            self.win.save_file()
            return
        self.busy = True
        QTimer.singleShot(170, lambda: self._go(name))

    def _go(self, name):
        self.busy = False
        self.on_open(name)

    def _flash(self, name, value):
        self.flash[name] = value; self.update()

    # --------------------------------------------------------- painting --
    def paint_tile(self, p, name, selected):
        label, _, base, light, tint, icon, ic, ipx, lc, lpx = HUB_TILES[name]
        path = hg.TILES[name]
        box = path.boundingRect()
        p.save(); p.setClipPath(path)
        g = QLinearGradient(box.topLeft(), box.bottomRight())
        g.setColorAt(0, QColor(light).darker(108)); g.setColorAt(0.55, QColor(base)); g.setColorAt(1, QColor(base).darker(118))
        p.fillRect(box, g)
        if selected:
            rg = QRadialGradient(QPointF(*ic), max(box.width(), box.height()) * 0.55)
            rg.setColorAt(0, QColor(255, 210, 120, 150)); rg.setColorAt(0.35, QColor(light))
            rg.setColorAt(1, QColor(0, 0, 0, 0))
            p.fillRect(box, rg)
        # Soft light sweeps, as on the game's tiles.
        p.setBrush(Qt.NoBrush)
        for k, (x, y, length, thick, alpha, _) in enumerate(self.streaks[name]):
            p.setPen(QPen(QColor(255, 255, 255, alpha + 6), 2 + k % 2))
            r = 260 + length * 900
            p.drawEllipse(QPointF(box.left() + x * box.width(), box.top() + y * box.height() + r * 0.9), r, r)
        p.setPen(Qt.NoPen); p.setBrush(QColor(255, 255, 255, 14))
        p.drawPolygon(QPolygonF([box.topLeft(), QPointF(box.left() + box.width() * 0.42, box.top()),
                                 QPointF(box.left(), box.top() + box.height() * 0.8)]))
        p.restore()
        shadow = QColor(base).darker(170); shadow.setAlpha(200)
        ink = WHITE if selected else QColor(tint)
        # icon
        p.setFont(fa_font(ipx))
        ir = QRectF(ic[0] - ipx, ic[1] - ipx * 0.75, ipx * 2, ipx * 1.5)
        if selected:
            ipath = text_path(icon, fa_font(ipx), QPointF(*ic))
            p.setPen(QPen(QColor("#111111"), ipx * 0.08, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush); p.drawPath(ipath.translated(0, ipx * 0.03))
            p.fillPath(ipath, ink)
        else:
            p.setPen(shadow); p.drawText(ir.translated(ipx * 0.04, ipx * 0.05), Qt.AlignCenter, icon)
            p.setPen(ink); p.drawText(ir, Qt.AlignCenter, icon)
        if not label:
            if name == "SAVE" and self.win.store.dirty:   # unsaved changes
                dot = QPointF(ic[0] + ipx * 0.55, ic[1] - ipx * 0.5)
                p.setPen(QPen(QColor("#111111"), 4)); p.setBrush(YELLOW); p.drawEllipse(dot, 13, 13)
            return
        font = round_font(lpx)
        tpath = text_path(label, font, QPointF(*lc))
        if selected:
            p.setPen(QPen(QColor("#0b0b0b"), lpx * 0.16, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush); p.drawPath(tpath.translated(lpx * 0.03, lpx * 0.05))
            p.drawPath(tpath)
            p.fillPath(tpath, ink)
        else:
            p.fillPath(tpath.translated(lpx * 0.035, lpx * 0.05), shadow)
            p.fillPath(tpath, ink)

    def disc_layer(self):
        """Key art + rings pre-rendered once per size (the art is the costliest draw)."""
        dpr = self.devicePixelRatioF()
        key = (self.width(), self.height(), dpr, self.art.cacheKey())
        if self._disc and self._disc[0] == key:
            return self._disc[1], self._disc[2]
        outer = hg.ART_R + hg.RING_W + hg.EDGE_W + 2
        box = QRectF(hg.DISC_C.x() - outer, hg.DISC_C.y() - outer, 2 * outer, 2 * outer)
        rect = hg.transform(self.width(), self.height()).mapRect(box).toAlignedRect()
        pm = QPixmap(int(rect.width() * dpr), int(rect.height() * dpr)); pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.transparent)
        p = QPainter(pm); p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        p.translate(-rect.left(), -rect.top())
        p.setTransform(hg.transform(self.width(), self.height()), True)
        self.paint_disc(p); p.end()
        self._disc = (key, pm, rect.topLeft())
        return pm, rect.topLeft()

    def paint_disc(self, p):
        c = hg.DISC_C
        outer = hg.ART_R + hg.RING_W + hg.EDGE_W
        g = QLinearGradient(QPointF(c.x() - outer, c.y() - outer), QPointF(c.x() + outer, c.y() + outer))
        g.setColorAt(0, QColor("#e3101e")); g.setColorAt(1, QColor("#ff7a12"))
        p.setPen(Qt.NoPen); p.setBrush(g); p.drawEllipse(c, outer, outer)
        p.setBrush(WHITE); p.drawEllipse(c, hg.ART_R + hg.RING_W, hg.ART_R + hg.RING_W)
        clip = QPainterPath(); clip.addEllipse(c, hg.ART_R, hg.ART_R)
        p.save(); p.setClipPath(clip)
        if self.art.isNull():
            p.fillRect(clip.boundingRect(), QColor("#202020"))
        else:
            p.drawPixmap(QRectF(c.x() - hg.ART_R - 1, c.y() - hg.ART_R - 1, 2 * hg.ART_R + 2, 2 * hg.ART_R + 2),
                         self.art, QRectF(self.art.rect()))
        p.restore()

    def paint_pointer(self, p):
        if not self.hover:
            return
        c, a = hg.DISC_C, math.radians(self.angle)
        r = hg.ART_R + 2
        ux, uy = math.cos(a), math.sin(a)
        tip = QPointF(c.x() + ux * (r + hg.RING_W - 1), c.y() + uy * (r + hg.RING_W - 1))
        base = QPointF(c.x() + ux * (r - 6), c.y() + uy * (r - 6))
        side = QPointF(-uy * 15, ux * 15)
        p.setPen(Qt.NoPen); p.setBrush(QColor("#0a0a0a"))
        p.drawPolygon(QPolygonF([tip, base + side, base - side]))

    def frame_pen(self, name, bright):
        box = hg.TILES[name].boundingRect()
        g = QLinearGradient(box.topLeft(), box.topRight())
        g.setColorAt(0, QColor("#ff2a36") if bright else QColor("#b0101c"))
        g.setColorAt(1, QColor("#ffa020") if bright else QColor("#c85a00"))
        return QPen(QBrush(g), 48, Qt.SolidLine, Qt.SquareCap, Qt.MiterJoin)

    def selected_layers(self):
        """Selected tile pre-rendered: dim and bright outer strokes + the framed tile.

        The pulse only cross-fades the two strokes, so a frame costs three blits
        instead of re-stroking thick paths and text outlines.
        """
        dpr = self.devicePixelRatioF()
        key = (self.width(), self.height(), dpr, self.hover)
        if self._sel and self._sel[0] == key:
            return self._sel[1]
        name = self.hover
        rect = self.view_rect(hg.TILES[name].boundingRect().adjusted(-30, -30, 30, 30))
        layers = []
        for kind in ("dim", "bright", "body"):
            pm = QPixmap(int(rect.width() * dpr), int(rect.height() * dpr)); pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
            p.translate(-rect.left(), -rect.top())
            p.setTransform(hg.transform(self.width(), self.height()), True)
            p.setBrush(Qt.NoBrush)
            if kind == "body":
                p.setPen(QPen(WHITE, 34, Qt.SolidLine, Qt.SquareCap, Qt.MiterJoin))
                p.drawPath(hg.TILES[name])
                self.paint_tile(p, name, True)
            else:
                p.setPen(self.frame_pen(name, kind == "bright")); p.drawPath(hg.TILES[name])
            p.end()
            layers.append(pm)
        self._sel = (key, (rect.topLeft(), *layers))
        return self._sel[1]

    def paint_rail(self, p):
        r = hg.RAIL
        p.setPen(QPen(QColor("#5c5c5c"), 3)); p.setBrush(QColor("#0b0b0b"))
        p.drawRoundedRect(r, 44, 44)
        active = self.rail_hover if self.rail_hover is not None else 0
        muted = bool(SFX and SFX.muted)
        for i, (rect, (icon, _)) in enumerate(zip(hg.rail_items(len(RAIL)), RAIL)):
            if i == 2 and muted:
                icon = "\uf6a9"
            on = i == active
            p.setFont(fa_font(62))
            p.setPen(QColor(0, 0, 0)); p.drawText(rect.translated(3, 4), Qt.AlignCenter, icon)
            p.setPen(WHITE if on else QColor("#c9c9c9")); p.drawText(rect, Qt.AlignCenter, icon)
            if on:
                y = rect.center().y()
                p.setPen(Qt.NoPen); p.setBrush(QColor("#e8141e"))
                x = rect.right() + 6
                p.drawPolygon(QPolygonF([QPointF(x, y), QPointF(x + 16, y - 14), QPointF(x + 16, y + 14)]))
        p.setFont(round_font(50, QFont.Bold)); p.setPen(QColor("#9b9b9b"))
        p.drawText(QRectF(r.left(), 990, 184, 70), Qt.AlignCenter, self.clock_text)

    def paint_strip(self, p):
        s = hg.STRIP
        p.fillRect(s, QColor("#080808"))
        p.save(); p.setClipRect(s)
        p.setPen(QPen(QColor(255, 255, 255, 10), 2))
        for x in range(int(s.left()), int(s.right()), 9):
            p.drawLine(QPointF(x, s.bottom()), QPointF(x + 120, s.top()))
        p.restore()
        if self.rail_hover is not None:
            text = RAIL[self.rail_hover][1]
        elif self.hover:
            text = HUB_TILES[self.hover][1]
            info = self.tile_info.get(self.hover)
            if info and self.hover != "SAVE":
                text = f"{text}   ·   {info}"
        else:
            text = "Choose a menu."
        p.setFont(round_font(46, QFont.DemiBold)); p.setPen(WHITE)
        p.drawText(QRectF(20, s.top(), hg.RAIL.left() - 40, 118), Qt.AlignCenter,
                   QFontMetricsF(p.font()).elidedText(text, Qt.ElideRight, hg.RAIL.left() - 80))

    def paint_top(self, p):
        store = self.win.store
        p.setFont(label_font(34, QFont.Bold)); p.setPen(QColor("#8d8d8d"))
        name = os.path.basename(store.save.path) if store.loaded else "No save loaded"
        p.drawText(QRectF(28, 18, 880, 64), Qt.AlignVCenter, f"ULTIMATE SMASHER   ·   {name}")
        if store.dirty:
            r = QRectF(700, 28, 200, 46)
            p.setPen(Qt.NoPen); p.setBrush(YELLOW); p.drawRoundedRect(r, 23, 23)
            p.setFont(label_font(30, QFont.Bold)); p.setPen(QColor("#111111"))
            p.drawText(r, Qt.AlignCenter, "UNSAVED")

    def static_layer(self, size, dpr):
        key = (size.width(), size.height(), dpr, self.hover, self.win.store.dirty,
               bool(SFX and SFX.muted), tuple(sorted(self.tile_info.items())))
        if self._cache and self._cache[0] == key:
            return self._cache[1]
        pm = QPixmap(int(size.width() * dpr), int(size.height() * dpr)); pm.setDevicePixelRatio(dpr)
        pm.fill(QColor("#000000"))
        p = QPainter(pm); p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
        p.setTransform(hg.transform(size.width(), size.height()))
        for name in HUB_TILES:
            if name != self.hover:
                self.paint_tile(p, name, False)
        p.end()
        self._cache = (key, pm)
        return pm

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), Qt.black)
        p.setOpacity(self.intro)
        p.drawPixmap(0, 0, self.static_layer(self.size(), self.devicePixelRatioF()))
        if self.hover:
            at, dim, bright, body = self.selected_layers()
            k = 0.5 + 0.5 * math.sin(self.pulse * math.tau)
            p.drawPixmap(at, dim)
            p.setOpacity(self.intro * k); p.drawPixmap(at, bright); p.setOpacity(self.intro)
            p.drawPixmap(at, body)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
        p.setTransform(hg.transform(self.width(), self.height()))
        for name, f in self.flash.items():
            if f > 0.01:
                p.fillPath(hg.TILES[name], QColor(255, 255, 255, int(170 * f)))
        dirty = event.rect()
        disc, at = self.disc_layer()
        if dirty.intersects(QRect(at, disc.size() / disc.devicePixelRatio())):
            p.save(); p.resetTransform(); p.drawPixmap(at, disc); p.restore()
            self.paint_pointer(p)
        # Skip chrome outside the repainted area (the pulse only touches one tile).
        for area, paint in ((hg.STRIP, self.paint_strip), (hg.TOP, self.paint_top), (hg.RAIL, self.paint_rail)):
            if dirty.intersects(self.view_rect(area)):
                paint(p)


# ============================================================== pages ======
class Page(QWidget):
    title = ""

    def __init__(self, app, parent):
        super().__init__(parent)
        self.app = app
        self.setGeometry(0, 8, W, PANEL_H - 8)

    @property
    def save(self):
        return self.app.store.save

    def refresh(self):
        for b in self.findChildren(QAbstractButton):
            b.update()


def grid(page, specs, cols, top, bh, gap_x=14, gap_y=24):
    """Lay out SlantButtons; returns them."""
    bw = (W - 2 * M - (cols - 1) * gap_x) / cols
    made = []
    for i, (text, kw) in enumerate(specs):
        r, c = divmod(i, cols)
        b = SlantButton(text, page, **kw)
        b.setGeometry(int(M + c * (bw + gap_x)) - 10, int(top + r * (bh + gap_y)) - 10, int(bw) + 20, bh + 20)
        made.append(b)
    px = min(b.label_fit() for b in made)
    for b in made:
        b.label_px = px
    return made


class GeneralPage(Page):
    def __init__(self, app, parent):
        super().__init__(app, parent)
        self.by_field = {}
        num = lambda f: (f.name, {"glyph": f.glyph, "value": lambda f=f: self.fmt(f), "desc": f.desc})
        bh, gy, top = 70, 22, 34
        row1 = grid(self, [num(sd.GOLD), num(sd.SP)], 2, top, bh)
        row2 = grid(self, [num(sd.HAMMERS), num(sd.TICKETS),
                           ("Language", {"glyph": G["language"], "value": self.lang_name, "desc": "Game language"})],
                    3, top + bh + gy, bh)
        row3 = grid(self, [("Milestones", {"glyph": G["milestones"], "value": lambda: self.pct(self.save.milestones_progress()),
                                               "desc": "Unlock every milestone"}),
                           ("Mii Clothes", {"glyph": G["mii"], "value": lambda: self.pct(self.save.mii_clothes_progress()),
                                                "desc": "Unlock every Mii Fighter outfit and hat"})],
                    2, top + 2 * (bh + gy), bh)
        btns = row1 + row2[:2]
        for f, b in zip([sd.GOLD, sd.SP, sd.HAMMERS, sd.TICKETS], btns):
            b.clicked.connect(lambda _=False, f=f, b=b: self.edit_number(f, b))
            self.by_field[f.key] = b
        self.lang = row2[2]
        self.miles, self.mii = row3
        px = min(b.label_px for b in row1 + row2 + row3)
        for b in row1 + row2 + row3:
            b.label_px = px
        self.lang.clicked.connect(self.pick_language)
        self.miles.clicked.connect(lambda: self.bulk(self.miles, "unlock_milestones", "milestones_progress", "ALL MILESTONES UNLOCKED"))
        self.mii.clicked.connect(lambda: self.bulk(self.mii, "unlock_mii_clothes", "mii_clothes_progress", "ALL MII CLOTHES UNLOCKED"))

    def fmt(self, f):
        return f"{self.save.value(f):,}" if self.save else ""

    def lang_name(self):
        if not self.save:
            return ""
        i = self.save.language
        return sd.LANGUAGES[i] if 0 <= i < len(sd.LANGUAGES) else f"#{i}"

    @staticmethod
    def pct(progress):
        on, total = progress
        return "100%" if on == total else f"{100 * on // total}%"

    def edit_number(self, f, btn):
        def done(v):
            if v != self.save.value(f):
                self.app.store.edit(lambda s: s.set_value(f, v))
                btn.pulse()
                self.app.toast(f"{f.name.upper()} SET TO {v:,}")
        NumberOverlay(self.app, f, self.save.value(f), done).open()

    def pick_language(self):
        def done(i):
            if i != self.save.language:
                self.app.store.edit(lambda s: setattr(s, "language", i))
                self.lang.pulse()
                self.app.toast(f"LANGUAGE: {sd.LANGUAGES[i].upper()}")
        ChoiceOverlay(self.app, "Language", G["language"], sd.LANGUAGES, self.save.language, done).open()

    def bulk(self, btn, action, progress, msg):
        on, total = getattr(self.save, progress)()
        if on == total:
            self.app.toast("ALREADY COMPLETE")
            return
        self.app.store.edit(lambda s: getattr(s, action)())
        btn.pulse()
        self.app.toast(msg)


ITEM_GROUPS = [  # header, item keys
    ("SNACKS", ["snack_s", "snack_m", "snack_l"]),
    ("SPIRIT BOARD", ["shuffle_all", "all_primaries", "all_supports", "filler", "rematch"]),
    ("BATTLE ITEMS", ["damage50", "slow_fs", "weaken_minions", "health_drain", "disable_items",
                      "shield_spacer", "sluggish_shield"]),
]


class ItemTile(AnimButton):
    """Inventory slot: big badge, short name and the amount owned."""
    previewed = pyqtSignal(object)
    SLANT = 8

    def __init__(self, field, page):
        super().__init__(page, field.name, field.desc)
        self.field, self.page = field, page
        self.selected = False

    def cursor_rect(self):
        return QRectF(self.rect()).adjusted(3, 3, -3, -3)

    def cursor_slant(self):
        return self.SLANT

    def enterEvent(self, e):
        super().enterEvent(e); self.previewed.emit(self.field)

    def focusInEvent(self, e):
        super().focusInEvent(e); self.previewed.emit(self.field)

    def cache_key(self):
        return super().cache_key() + (self.page.amount(self.field), self.selected)

    def draw(self, p):
        r = QRectF(self.rect()).adjusted(4, 4, -4, -4)
        self.transform(p, r)
        path = para_path(r, self.SLANT)
        p.fillPath(para_path(r.translated(2, 3), self.SLANT), QColor(0, 0, 0, 55))
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0, QColor("#2a8cf0" if self.selected else "#1f6fd1"))
        g.setColorAt(1, QColor("#0a4aa6" if self.selected else "#0b3f8c"))
        p.fillPath(path, g)
        if self.ft > 0.01:
            p.fillPath(path, QColor(255, 244, 160, int(170 * self.ft)))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(WHITE if self.selected else QColor("#0c0c0c"), 2.5)); p.drawPath(path)
        d = min(r.width() * 0.7, r.height() * 0.66)
        disc = QRectF(r.center().x() - d / 2, r.top() + r.height() * 0.06, d, d)
        draw_item_badge(p, disc, self.field.key)
        val = f"{self.page.amount(self.field):,}"
        chip = QRectF(r.left() + r.width() * 0.16, r.bottom() - r.height() * 0.26, r.width() * 0.68, r.height() * 0.22)
        p.setPen(Qt.NoPen); p.setBrush(QColor(0, 0, 0, 150)); p.drawPolygon(para(chip, 6))
        p.setFont(fit_font(heavy_italic, val, chip.width() - 10, chip.height() * 1.05, 9))
        p.setPen(YELLOW); p.drawText(chip, Qt.AlignCenter, val)


class ItemsPage(Page):
    """Inventory: grouped item slots on the left, selected item detail on the right."""

    def __init__(self, app, parent):
        super().__init__(app, parent)
        fields = {f.key: f for f in sd.ITEMS}
        self.split = W * 0.62
        cols, gap = 7, 8
        tw = (self.split - M - (cols - 1) * gap) / cols
        head, row_gap = 26, 10
        th = min(tw * 0.92, (self.height() - 3 * (head + row_gap) - 14) / 3)
        self.headers = []
        self.btns, self.by_key = [], {}
        y = 10
        for title, keys in ITEM_GROUPS:
            self.headers.append((title, y))
            y += head
            for i, key in enumerate(keys):
                t = ItemTile(fields[key], self)
                t.setGeometry(round(M + i * (tw + gap)), round(y), round(tw), round(th))
                t.previewed.connect(self.preview)
                t.clicked.connect(lambda _=False, f=fields[key]: self.edit_number(f))
                self.by_key[key] = t
            y += th + row_gap
        self.btns = [self.by_key[f.key] for f in sd.ITEMS]
        self.current = sd.ITEMS[0]
        self.by_key[self.current.key].selected = True
        # detail panel
        px = self.split + 18
        pw = W - M - px
        self.panel = QRectF(px, 10, pw, self.height() - 22)
        by = self.panel.bottom() - 70
        bw = (pw - 2 * 12 - 30) / 3
        self.minus = PlateButton("", self, G["minus"], "dark", desc="One less (−)")
        self.plus = PlateButton("", self, G["plus"], "dark", desc="One more (+)")
        self.maxone = PlateButton("MAX", self, "", "yellow", desc="Set this item to the maximum")
        for i, b in enumerate((self.minus, self.plus, self.maxone)):
            b.setGeometry(round(px + 15 + i * (bw + 12)), round(by), round(bw), 54)
        self.mx = PlateButton("MAX ALL", self, G["bolt"], "yellow", desc="Set every item and snack to the maximum")
        self.mx.setGeometry(round(self.split - 170), 4, 170, 40)
        for b in (self.minus, self.plus):
            b.setAutoRepeat(True); b.setAutoRepeatDelay(350); b.setAutoRepeatInterval(60)
        self.minus.clicked.connect(lambda: self.bump(-1))
        self.plus.clicked.connect(lambda: self.bump(1))
        self.maxone.clicked.connect(lambda: self.set_amount(self.current, self.current.maximum))
        self.mx.clicked.connect(self.max_all)

    def amount(self, f):
        return self.save.value(f) if self.save else 0

    def preview(self, f):
        if f is self.current:
            return
        self.by_key[self.current.key].selected = False
        self.by_key[self.current.key].update()
        self.current = f
        self.by_key[f.key].selected = True
        self.by_key[f.key].update()
        self.update(self.panel.toAlignedRect().adjusted(-4, -4, 4, 4))

    def set_amount(self, f, v):
        if not self.save:
            return
        v = max(0, min(f.maximum, v))
        if v != self.save.value(f):
            self.app.store.edit(lambda s: s.set_value(f, v))
            self.by_key[f.key].pulse()
        self.update(self.panel.toAlignedRect())

    def bump(self, d):
        if self.save:
            self.set_amount(self.current, self.save.value(self.current) + d)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Plus, Qt.Key_Equal):
            play("move"); self.bump(10 if e.modifiers() & Qt.ShiftModifier and e.key() == Qt.Key_Plus else 1)
        elif e.key() in (Qt.Key_Minus, Qt.Key_Underscore):
            play("move"); self.bump(-1)
        else:
            super().keyPressEvent(e)

    def edit_number(self, f, btn=None):
        self.preview(f)

        def done(v):
            if v != self.save.value(f):
                self.set_amount(f, v)
                self.app.toast(f"{f.name.upper()} × {v:,}")
        NumberOverlay(self.app, f, self.save.value(f), done).open()

    def max_all(self):
        def run(s):
            for f in sd.ITEMS:
                s.set_value(f, f.maximum)
        self.app.store.edit(run)
        for i, b in enumerate(self.btns):
            QTimer.singleShot(i * 35, b.pulse)
        self.app.toast("ALL ITEMS MAXED")

    def refresh(self):
        super().refresh(); self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        for title, y in self.headers:
            p.setFont(heavy_italic(19)); p.setPen(QColor("#1b1b1f"))
            p.drawText(QRectF(M + 4, y, 300, 24), Qt.AlignVCenter | Qt.AlignLeft, title)
            fm = QFontMetricsF(p.font())
            x0 = M + 14 + fm.horizontalAdvance(title)
            x1 = self.split - (182 if y == self.headers[0][1] else 6)
            p.setPen(QPen(QColor("#1b1b1f"), 2)); p.drawLine(QPointF(x0, y + 13), QPointF(x1, y + 13))
        # detail panel
        r = self.panel
        facets(p, r, "#16171b", 16)
        f = self.current
        d = min(r.width() * 0.34, r.height() * 0.32)
        disc = QRectF(r.center().x() - d / 2, r.top() + 20, d, d)
        p.setPen(Qt.NoPen); p.setBrush(QColor(255, 255, 255, 18)); p.drawEllipse(disc.adjusted(-14, -14, 14, 14))
        draw_item_badge(p, disc, f.key)
        y = disc.bottom() + 16
        p.setFont(fit_font(heavy_italic, f.name.upper(), r.width() - 60, 32)); p.setPen(WHITE)
        p.drawText(QRectF(r.left() + 20, y, r.width() - 40, 36), Qt.AlignCenter, f.name.upper())
        p.setFont(label_font(17, QFont.DemiBold)); p.setPen(QColor("#b8b8c0"))
        p.drawText(QRectF(r.left() + 30, y + 36, r.width() - 60, 44), Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap, f.desc)
        val = f"{self.amount(f):,}"
        bottom = r.bottom() - 84
        chip = QRectF(r.left() + 34, max(y + 82, bottom - 66), r.width() - 68, min(66, bottom - y - 82))
        p.setPen(Qt.NoPen); p.setBrush(QColor(0, 0, 0, 170)); p.drawPolygon(para(chip, 14))
        p.setFont(fit_font(heavy_italic, val, chip.width() * 0.6, chip.height() * 0.85, 14)); p.setPen(YELLOW)
        p.drawText(chip, Qt.AlignCenter, val)
        p.setFont(label_font(13, QFont.Bold)); p.setPen(QColor("#8a8a92"))
        p.drawText(chip.adjusted(0, 0, -20, -4), Qt.AlignRight | Qt.AlignBottom, f"MAX {f.maximum:,}")


class FighterTile(AnimButton):
    previewed = pyqtSignal(int)

    def __init__(self, idx, name, img, parent):
        super().__init__(parent, name)
        self.idx = idx
        self.img = img
        self.sfx = None
        self.setFocusPolicy(Qt.StrongFocus)
        src = pixmap(f"portraits/{img}.png")
        self.src = src
        self.src_locked = grayscale(src)
        self.render = pixmap(f"renders/{img}.png")
        self.render_locked = grayscale(self.render)
        self.unlocked = True
        self.pop = 0.0

    def enterEvent(self, event):
        super().enterEvent(event)
        self.previewed.emit(self.idx)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.previewed.emit(self.idx)

    def cursor_rect(self):
        return QRectF(self.rect()).adjusted(1, 1, -1, -1)

    def cursor_slant(self):
        return 0

    def set_state(self, unlocked, animate=False, delay=0):
        changed = unlocked != self.unlocked
        self.unlocked = unlocked
        self.desc = f"{self.title} — {'unlocked (click to lock)' if unlocked else 'locked (click to unlock)'}"
        if STATUS and (self.underMouse() or self.hasFocus()):
            STATUS.describe(self.desc)
        if animate and changed:
            tween(self, "pop", 1.0, 0.0, 420, self._set("pop"), QEasingCurve.OutQuad, delay=delay)
            if delay:
                QTimer.singleShot(int(delay), self.update)
        self.update()

    def cache_key(self):
        return super().cache_key() + (self.unlocked,)

    def draw(self, p):
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        band = max(10.0, r.height() * 0.27)
        face = QRectF(r.left(), r.top(), r.width(), r.height() - band)
        p.fillRect(r, QColor("#111111"))
        pm = self.src if self.unlocked else self.src_locked
        p.drawPixmap(face, pm, portrait_source(pm, face.width() / face.height()))
        if not self.unlocked:
            p.fillRect(face, QColor(10, 10, 14, 150))
            p.setFont(fa_font(face.height() * 0.42)); p.setPen(QColor(255, 255, 255, 220))
            p.drawText(face, Qt.AlignCenter, G["lock"])
        if self.pop > 0.01:
            p.fillRect(r, QColor(255, 240, 150, int(180 * self.pop)))
        nb = QRectF(r.left(), face.bottom(), r.width(), band)
        p.fillRect(nb, QColor("#0c0c0c"))
        name = self.title.upper()
        p.setFont(fit_font(lambda px: label_font(px, QFont.Bold), name, nb.width() - 6, band * 0.95, 7))
        p.setPen(WHITE if self.unlocked else QColor("#8a8a8a"))
        p.drawText(nb, Qt.AlignCenter, name)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(YELLOW if self.t > 0.5 else QColor("#000000"), 3 if self.t > 0.5 else 1))
        p.drawRect(r)


class CharactersPage(Page):
    COLS = 13

    def __init__(self, app, parent):
        super().__init__(app, parent)
        n = len(sd.FIGHTERS)
        rows = math.ceil(n / self.COLS)
        gap = 1
        tw = (W - 16 - (self.COLS - 1) * gap) / self.COLS
        th = min(tw * 62 / 94, (self.height() - 148) / rows - gap)
        top = 4
        x0 = 8
        self.tiles = []
        self.selected_idx = 0
        last = n - (rows - 1) * self.COLS
        for i, (name, img) in enumerate(sd.FIGHTERS):
            r, c = divmod(i, self.COLS)
            x = x0 + c * (tw + gap)
            if r == rows - 1:
                x += (self.COLS - last) * (tw + gap) / 2
            tile = FighterTile(i, name, img, self)
            tile.setGeometry(round(x), round(top + r * (th + gap)), round(tw), round(th))
            tile.setAccessibleName(name)
            tile.previewed.connect(self.preview)
            tile.clicked.connect(lambda _=False, i=i: self.toggle(i))
            self.tiles.append(tile)
        self.bar_y = int(top + rows * (th + gap) + 7)
        self.count_txt = ""
        self.unlock_all = PlateButton("UNLOCK ALL", self, G["unlock"], "yellow", desc="Unlock all 71 base fighters")
        self.unlock_all.setGeometry(W - 275, self.bar_y + 6, 265, 58)
        self.unlock_all.clicked.connect(lambda: self.set_all(True))
        self.lock_all = PlateButton("LOCK ALL", self, G["lock"], "dark", desc="Lock every fighter on the roster")
        self.lock_all.setGeometry(W - 275, self.bar_y + 66, 265, 52)
        self.lock_all.clicked.connect(self.confirm_lock_all)

    def preview(self, idx):
        if idx != self.selected_idx:
            self.selected_idx = idx
            self.update()

    def refresh(self):
        if not self.save:
            return
        for t in self.tiles:
            t.set_state(self.save.fighter_unlocked(t.idx))
        n = self.save.fighters_unlocked()
        self.count_txt = f"{n} / {len(sd.FIGHTERS)}"
        self.update()

    def toggle(self, i):
        new = not self.save.fighter_unlocked(i)
        self.app.store.edit(lambda s: s.set_fighter(i, new))
        play("unlock" if new else "lock")
        self.tiles[i].set_state(new, animate=True)
        self.app.toast(f"{sd.FIGHTERS[i][0].upper()} {'UNLOCKED' if new else 'LOCKED'}",
                       icon=pixmap(f"stock/{sd.FIGHTERS[i][1]}.png"))

    def set_all(self, value):
        before = [self.save.fighter_unlocked(i) for i in range(len(sd.FIGHTERS))]
        if all(b == value for b in before):
            self.app.toast("ALREADY " + ("UNLOCKED" if value else "LOCKED"))
            return

        def run(s):
            for i in range(len(sd.FIGHTERS)):
                s.set_fighter(i, value)
        self.app.store.edit(run)
        play("unlock" if value else "lock")
        for t in self.tiles:
            t.unlocked = before[t.idx]
            r, c = divmod(t.idx, self.COLS)
            t.set_state(value, animate=True, delay=(r + c) * 22)
        self.app.toast("ALL FIGHTERS UNLOCKED!" if value else "ALL FIGHTERS LOCKED")

    def confirm_lock_all(self):
        ConfirmOverlay(self.app, "Lock all fighters?",
                       "Every fighter will be locked again and you'll have to unlock them "
                       "in-game (or here). This only changes the editor until you press <b>SAVE</b>.",
                       [("LOCK ALL", G["lock"], "red", lambda: self.set_all(False)),
                        ("CANCEL", G["back"], "dark", None)]).open()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.fillRect(QRectF(0, 0, W, self.bar_y), QColor("#08090b"))
        y = self.bar_y + 4
        h = self.height() - y - 7
        p.setPen(QPen(QColor("#32b9d6"), 3)); p.drawLine(0, self.bar_y, W, self.bar_y)
        card = QRectF(8, y, W * 0.46, h)
        facets(p, card, "#ed1728", 20)
        tile = self.tiles[self.selected_idx]
        p.save(); p.setClipPath(para_path(card, 20))
        portrait = QRectF(card.left() + 10, card.top(), card.width() * 0.36, h)
        halftone(p, portrait.left(), portrait.top(), 24, 14, QColor(255, 255, 255, 40))
        mark = series_mark(tile.img)
        if not mark.isNull():
            ms = h * 1.3
            p.setOpacity(0.3)
            p.drawPixmap(QRectF(card.right() - ms - 18, card.center().y() - ms / 2, ms, ms), mark, QRectF(mark.rect()))
            p.setOpacity(1.0)
        render = tile.render if tile.unlocked else tile.render_locked
        if not render.isNull():
            # Big fighter render, cropped to head and shoulders like the game's player panel.
            side = h * 2.1
            target = QRectF(portrait.center().x() - side / 2, card.top() - h * 0.12, side, side)
            p.setOpacity(1.0 if tile.unlocked else 0.55)
            p.drawPixmap(target, render, QRectF(render.rect()))
            p.setOpacity(1.0)
        else:
            pm = tile.src if tile.unlocked else tile.src_locked
            shot = fit_pixmap_rect(QSize(94, 62), portrait.adjusted(12, 12, -12, -12))
            p.drawPixmap(shot, pm, portrait_source(pm, 94 / 62))
        p.restore()
        x = portrait.right() + 12
        p.setFont(label_font(15)); p.setPen(WHITE)
        p.drawText(QRectF(x, y + 8, card.right() - x - 18, 20), Qt.AlignLeft | Qt.AlignVCenter, "FIGHTER SELECT")
        stock = pixmap(f"stock/{tile.img}.png")
        nx = x
        if not stock.isNull():
            p.setOpacity(1.0 if tile.unlocked else 0.45)
            p.drawPixmap(QRectF(x, y + 33, 38, 38), stock, QRectF(stock.rect()))
            p.setOpacity(1.0)
            nx = x + 46
        p.setFont(fit_font(game_font, tile.title, card.right() - nx - 20, 29))
        draw_text_shadow(p, QRectF(nx, y + 31, card.right() - nx - 16, 42), Qt.AlignVCenter, tile.title)
        state = "UNLOCKED" if tile.unlocked else "LOCKED"
        badge = QRectF(x, y + h - 36, card.right() - x - 20, 27)
        p.fillRect(badge, QColor("#fafafa")); p.setPen(QPen(QColor("#111111"), 2)); p.drawRect(badge)
        p.setFont(game_font(16)); p.setPen(QColor("#111111")); p.drawText(badge, Qt.AlignCenter, state)
        summary = QRectF(card.right() + 10, y, W - 285 - card.right() - 10, h)
        facets(p, summary, "#292b30", 12)
        p.setFont(label_font(18)); p.setPen(WHITE)
        p.drawText(summary.adjusted(16, 10, -16, -10), Qt.AlignHCenter | Qt.AlignTop, "BASE FIGHTERS")
        p.setFont(game_font(32)); p.setPen(YELLOW)
        p.drawText(summary, Qt.AlignCenter, self.count_txt)
        p.setFont(label_font(14)); p.setPen(WHITE)
        p.drawText(summary.adjusted(15, 0, -15, -10), Qt.AlignHCenter | Qt.AlignBottom, "DLC requires installed content")


class StatsPage(Page):
    def __init__(self, app, parent):
        super().__init__(app, parent)
        self.cats = []
        icons = {"Combined": G["trophy"], "Smash": G["bolt"], "Spirits": G["star"],
                 "Games & More": G["gift"], "Vault": G["folder"], "Online": G["users"]}
        for i, name in enumerate(sd.STATS):
            b = PlateButton(name.upper(), self, icons[name], "dark", desc=f"{name} records", slant=12)
            b.setGeometry(M - 4, 14 + i * 60, 270, 58)
            b.clicked.connect(lambda _=False, n=name: self.show_cat(n))
            self.cats.append((name, b))
        self.card = DarkCard(self, "")
        self.card.setGeometry(M + 280, 10, W - 2 * M - 280, PANEL_H - 36)
        self.scroll = QScrollArea(self.card)
        self.scroll.setGeometry(34, 50, self.card.width() - 70, self.card.height() - 64)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        self.head = QLabel(self.card)
        self.head.setGeometry(34, 8, self.card.width() - 80, 38)
        self.head.setStyleSheet("color: white; font-family: 'Barlow Condensed'; font-size: 28px;"
                                " font-weight: 900; font-style: italic; background: transparent;")
        self.cat = None
        self.shown_for = None

    def refresh(self):
        if not self.save:
            return
        if self.cat is None or self.save is not self.shown_for:
            self.show_cat(self.cat or "Combined")
            return
        body = self.scroll.widget()
        for row in body.findChildren(StatRow) if body else []:
            row.sync(self.save.get(row.off, 4))

    def show_cat(self, name):
        self.cat = name
        self.shown_for = self.save
        for n, b in self.cats:
            b.checked_look = n == name; b.update()
        self.head.setText(name.upper())
        body = QWidget()
        lay = QVBoxLayout(body); lay.setContentsMargins(0, 0, 14, 0); lay.setSpacing(4)
        for label, off, value in self.save.stats(name):
            lay.addWidget(StatRow(self, label, off, value))
        lay.addStretch()
        self.scroll.setWidget(body)
        eff = QGraphicsOpacityEffect(body); body.setGraphicsEffect(eff)
        tween(body, "fade", 0, 1, 260, lambda v: eff.setOpacity(v),
              done=lambda: body.setGraphicsEffect(None))

    def write(self, off, value, row):
        self.app.store.edit(lambda s: s.set_stats({off: value}))
        row.flash()


class StatRow(QWidget):
    def __init__(self, page, label, off, value):
        super().__init__()
        self.page, self.off, self.secs = page, off, "(seconds)" in label
        self.setFixedHeight(40)
        self.label = label.replace(" (seconds)", "")
        self.edit = QLineEdit(str(value), self)
        self.edit.setValidator(QIntValidator(0, sd.STAT_MAX, self))
        self.edit.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.edit.setStyleSheet(
            "QLineEdit { background: #ffffff; color: #111111; border: 2px solid #242424; border-radius: 0px;"
            " font-family: 'Barlow Condensed'; font-size: 21px; font-weight: 800; padding: 0 8px;"
            " selection-background-color: #e3001b; selection-color: white; }"
            "QLineEdit:focus { border-color: #e3001b; background: #fff8c5; }")
        self.edit.editingFinished.connect(self.commit)
        self.edit.returnPressed.connect(self.on_return)
        self.edit.textChanged.connect(lambda _: self.update())
        self.edit.installEventFilter(self)
        self.value = value
        self.start_text = str(value)
        self.ft = 0.0

    def eventFilter(self, obj, e):
        if e.type() == e.FocusOut:
            self.edit.deselect()
        elif e.type() == e.FocusIn:
            self.start_text = self.edit.text()
            QTimer.singleShot(0, self.edit.selectAll)
            self.page.scroll.ensureWidgetVisible(self, 0, 30)
            if STATUS:
                STATUS.describe(f"{self.label}: type a number, or press OK / Enter to adjust")
            if e.reason() in (Qt.MouseFocusReason, Qt.TabFocusReason, Qt.BacktabFocusReason):
                play("move")
        elif e.type() == e.KeyPress and (e.key() in (Qt.Key_Up, Qt.Key_Down) or (
                e.key() == Qt.Key_Left and (self.edit.hasSelectedText() or self.edit.cursorPosition() == 0))):
            self.page.app.move_focus(e.key())
            return True
        return False

    def on_return(self):
        if self.edit.text() != self.start_text:
            return  # typed a value: editingFinished commits it
        field = sd.Field(f"stat{self.off:x}", self.label, self.off, 4, sd.STAT_MAX, 100,
                         glyph=G["trophy"], desc=self.label)

        def done(v):
            self.edit.setText(str(v)); self.commit(); self.start_text = str(v)
        play("select")
        NumberOverlay(self.page.app, field, self.value, done).open()

    def resizeEvent(self, e):
        self.edit.setGeometry(self.width() - 170, 3, 166, 34)
        self.edit.setFocusPolicy(Qt.StrongFocus)

    def sync(self, value):
        """Show a value that changed underneath (backup loaded, file reopened)."""
        if value != self.value:
            self.value = value
            self.edit.setText(str(value))
            self.start_text = str(value)

    def commit(self):
        t = self.edit.text().strip()
        if not t:
            self.edit.setText(str(self.value)); return
        v = int(t)
        if v != self.value:
            self.value = v
            self.page.write(self.off, v, self)
            play("select")

    def flash(self):
        tween(self, "ft", 1.0, 0.0, 600, self._ft)

    def _ft(self, v):
        self.ft = v; self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0, 2, -176, -2)
        p.fillRect(r, QColor("#ffe25a") if self.ft > 0.1 else QColor("#d9dade"))
        p.setFont(label_font(19, QFont.DemiBold)); p.setPen(QColor("#161616"))
        p.drawText(r.adjusted(12, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, self.label)
        if self.secs and self.edit.text().isdigit():
            p.setFont(label_font(15, QFont.DemiBold, True)); p.setPen(QColor("#494949"))
            p.drawText(r.adjusted(0, 0, -10, 0), Qt.AlignVCenter | Qt.AlignRight, fmt_duration(int(self.edit.text())))


class BackupsPage(Page):
    def __init__(self, app, parent):
        super().__init__(app, parent)
        self.card = DarkCard(self, "")
        self.card.setGeometry(M - 4, 10, 640, PANEL_H - 36)
        head = QLabel("SAVED BACKUPS", self.card)
        head.setGeometry(34, 8, 400, 38)
        head.setStyleSheet("color: white; font-family: 'Barlow Condensed'; font-size: 28px;"
                           " font-weight: 900; font-style: italic; background: transparent;")
        self.list = QListWidget(self.card)
        self.list.setGeometry(34, 52, self.card.width() - 78, self.card.height() - 70)
        self.list.setStyleSheet(
            "QListWidget { background: transparent; border: none; outline: none; color: #161616;"
            " font-family: 'Barlow Condensed'; font-size: 20px; font-weight: 700; }"
            "QListWidget::item { padding: 8px 10px; margin: 2px 0; background: #dedfe2; border-left: 4px solid #161616; }"
            "QListWidget::item:hover { background: #fff3a3; }"
            "QListWidget::item:selected { background: #ffd400; color: #111; }")
        self.list.itemActivated.connect(lambda _: self.restore())
        x = M + 650
        bw = W - M - x + 4
        self.restore_btn = PlateButton("LOAD BACKUP", self, G["backups"], "yellow",
                                       desc="Load the selected backup into the editor (then SAVE to write it)")
        self.restore_btn.setGeometry(x, 18, bw, 64); self.restore_btn.clicked.connect(self.restore)
        now = PlateButton("BACKUP NOW", self, G["save"], "dark", desc="Copy the save files on disk to a new backup")
        now.setGeometry(x + 4, 92, bw - 8, 50); now.clicked.connect(self.backup_now)
        folder = PlateButton("OPEN FOLDER", self, G["folder"], "dark", desc=sd.BACKUP_DIR)
        folder.setGeometry(x + 4, 146, bw - 8, 50)
        folder.clicked.connect(lambda: (os.makedirs(sd.BACKUP_DIR, exist_ok=True),
                                        QDesktopServices.openUrl(QUrl.fromLocalFile(sd.BACKUP_DIR))))
        self.note = QLabel(self)
        self.note.setWordWrap(True)
        self.note.setGeometry(x + 4, 210, bw - 8, 150)
        self.note.setStyleSheet("color: #303035; font-family: 'Barlow Condensed'; font-size: 17px;"
                                " font-weight: 600; font-style: italic; background: transparent;")
        self.note.setText(f"A backup of both Ryujinx slots is made every time you press SAVE. "
                          f"The newest {sd.BACKUP_KEEP} are kept.")

    def refresh(self):
        sel = self.list.currentRow()
        self.list.clear()
        for d, f, mt in sd.list_backups():
            slots = len([x for x in os.listdir(d) if x.endswith("system_data.bin")])
            it = QListWidgetItem(f"{time.strftime('%d %b %Y  ·  %H:%M:%S', time.localtime(mt))}"
                                 f"      {'both slots' if slots > 1 else '1 file'}")
            it.setData(Qt.UserRole, f)
            self.list.addItem(it)
        if self.list.count() == 0:
            it = QListWidgetItem("No backups yet — one is made on every save.")
            it.setFlags(Qt.NoItemFlags); self.list.addItem(it)
        else:
            self.list.setCurrentRow(max(0, min(sel, self.list.count() - 1)))
        super().refresh()

    def restore(self):
        it = self.list.currentItem()
        path = it.data(Qt.UserRole) if it else None
        if not path:
            self.app.toast("SELECT A BACKUP FIRST", "error"); return

        play("select")

        def go():
            try:
                with open(path, "rb") as f:
                    raw = f.read()
                self.app.store.edit(lambda s: s.load_bytes(raw))
            except (OSError, sd.InvalidSave) as e:
                self.app.toast(f"COULDN'T LOAD: {e}", "error"); return
            self.app.toast("BACKUP LOADED — PRESS SAVE TO KEEP IT")
        ConfirmOverlay(self.app, "Load this backup?",
                       f"<b>{it.text().split('      ')[0]}</b><br>The editor will show the backup's data. "
                       "Nothing is written to disk until you press <b>SAVE</b>.",
                       [("LOAD", G["backups"], "yellow", go), ("CANCEL", G["back"], "dark", None)],
                       glyph=G["backups"]).open()

    def backup_now(self):
        s = self.save
        targets = [s.path] + ([sd.mirror_path(s.path)] if sd.mirror_path(s.path) else [])
        dest = sd.make_backup(targets)
        self.refresh()
        self.app.toast(f"BACKUP CREATED: {os.path.basename(dest)}" if dest else "NOTHING TO BACK UP")


# ========================================================= main window =====
SECTIONS = [  # name, tab glyph, page class
    ("GENERAL", "BALL", GeneralPage),
    ("ITEMS", G["items"], ItemsPage),
    ("CHARACTERS", G["fighters"], CharactersPage),
    ("STATS", G["stats"], StatsPage),
    ("BACKUPS", G["backups"], BackupsPage),
]


class MainWindow(QWidget):
    def __init__(self, path=None):
        super().__init__(None)
        self.setWindowTitle("Ultimate Smasher")
        self.setWindowIcon(QIcon(os.path.join(IMG, "icon.ico")))
        self.setFixedSize(W, H)
        self.setFocusPolicy(Qt.StrongFocus)
        self.store = Store()
        self.force_close = False
        self.current = None
        self.streaks = make_streaks(7)
        self.phase = 0.0
        self.header_title, self.header_k = APP_TITLE, 1.0

        global STATUS, CURSOR, PAD
        # header buttons
        x = M
        self.open_btn = PlateButton("OPEN SAVE", self, G["open"], "dark", desc="Open a system_data.bin (Ctrl+O)")
        self.open_btn.setGeometry(x, 10, 150, 36); self.open_btn.clicked.connect(self.open_dialog)
        self.save_btn = PlateButton("SAVE", self, G["save"], "dark", desc="Save changes and back up the old file (Ctrl+S)")
        self.save_btn.setGeometry(x + 156, 10, 104, 36); self.save_btn.clicked.connect(self.save_file)
        self.help_btn = PlateButton("HELP", self, G["help"], "dark", desc="How to use")
        self.help_btn.setGeometry(x + 266, 10, 100, 36); self.help_btn.clicked.connect(lambda: HelpOverlay(self).open())
        self.back_btn = PlateButton("MENU", self, G["back"], "dark", desc="Back to the main menu (Esc)")
        self.back_btn.setGeometry(x + 372, 10, 110, 36); self.back_btn.clicked.connect(self.show_hub)
        for b in (self.open_btn, self.save_btn, self.help_btn, self.back_btn):
            b.setFocusPolicy(Qt.NoFocus)
        mb = PlateButton("", self, G["min"], "dark", desc="Minimize"); mb.setGeometry(W - M - 88, 10, 42, 36)
        mb.clicked.connect(self.showMinimized); mb.setFocusPolicy(Qt.NoFocus)
        xb = PlateButton("", self, G["close"], "dark", desc="Close"); xb.setGeometry(W - M - 42, 10, 42, 36)
        xb.clicked.connect(self.close); xb.setFocusPolicy(Qt.NoFocus)
        self.header_buttons = [self.open_btn, self.save_btn, self.help_btn, mb, xb]

        # section view: tabs + panel with pages
        self.panel = Panel(self)
        self.panel.setGeometry(0, PANEL_Y, W, PANEL_H)
        weights = [1.1, 0.95, 1.25, 0.95, 1.05]
        overlap = 6
        span = W - 2 * M - 70 + overlap * (len(SECTIONS) - 1)
        widths = [span * w / sum(weights) for w in weights]
        self.tabs, self.pages, self.tab_x = [], [], []
        tx = float(M + 35)
        for (name, glyph, cls), wd in zip(SECTIONS, widths):
            t = SlantTab(name, glyph, self)
            t.setGeometry(round(tx), TAB_Y, round(wd), TAB_H)
            self.tab_x.append(round(tx))
            t.clicked.connect(lambda _=False, n=name: self.select(n))
            self.tabs.append(t)
            tx += wd - overlap
            page = cls(self, self.panel); page.hide()
            self.pages.append(page)
        self.key_q = KeyHint("Q", self); self.key_q.setGeometry(M - 4, TAB_Y + 18, 30, 30)
        self.key_e = KeyHint("E", self); self.key_e.setGeometry(W - M - 26, TAB_Y + 18, 30, 30)
        self.empty = EmptyState(self, self.panel)
        self.empty.setGeometry(0, 8, W, PANEL_H - 8)
        self.section_widgets = self.tabs + [self.panel, self.key_q, self.key_e]

        self.hub = Hub(self, self.open_section, self.hub_info, self.ask_quit)
        self.hub.setGeometry(0, 0, W, H)

        STATUS = StatusBar(self.store, self)
        STATUS.setGeometry(0, H - SB_H, W, SB_H)
        CURSOR = Cursor(self)
        self.toast_w = Toast(self)
        self.store.changed.connect(self.on_change)
        QApplication.instance().focusChanged.connect(self.focus_changed)
        PAD = gamepad.Gamepad(self)
        PAD.connected_changed.connect(self.pad_changed)
        self.motion = QTimer(self); self.motion.timeout.connect(self.tick); self.motion.start(40)

        if path or sd.default_save_path():
            try:
                self.store.load(path or sd.default_save_path())
            except sd.InvalidSave as e:
                msg = str(e)
                QTimer.singleShot(600, lambda: self.toast(msg, "error", 5000))
        self.on_change()
        self.show_hub(intro=True)

    # ------------------------------------------------------------- state --
    def focus_changed(self, old, new):
        if CURSOR is not None:
            CURSOR.track(new)
        if STATUS is not None:
            STATUS.update()

    def pad_changed(self, on):
        self.toast("CONTROLLER CONNECTED" if on else "CONTROLLER DISCONNECTED", "ok" if on else "error")
        STATUS.update()

    def tick(self):
        if not self.isVisible() or self.isMinimized() or not self.isActiveWindow():
            return
        self.phase += 0.04
        if self.current is None:
            clock_text = time.strftime("%H:%M")
            if clock_text != self.hub.clock_text:
                self.hub.clock_text = clock_text
                self.hub.update()
        else:
            self.panel.phase = self.phase
            self.panel.update()

    def set_header(self, text):
        if text == self.header_title:
            return
        self.header_title = text
        tween(self, "header", 0.0, 1.0, 320, self._header, QEasingCurve.OutCubic)

    def _header(self, v):
        self.header_k = v
        self.update(QRect(int(W * 0.6) - 30, 0, W, HB + 6))

    def overlay_open(self):
        return any(isinstance(c, Overlay) and not c.closing for c in self.children())

    def ask_quit(self):
        play("back")
        ConfirmOverlay(self, "Quit Ultimate Smasher?", "Close the editor and go back to the desktop.",
                       [("QUIT", G["close"], "red", self.close), ("CANCEL", G["back"], "dark", None)],
                       glyph=G["close"]).open()

    def toast(self, text, kind="ok", ms=2600, icon=None):
        self.toast_w.show_toast(text, kind, ms, icon)

    def on_change(self):
        dirty = self.store.dirty
        self.save_btn.style = "yellow" if dirty else "dark"
        self.save_btn.update()
        if self.current is not None and self.store.loaded:
            self.pages[self.current].refresh()
        self.hub.tile_info = {name: self.hub_info(name) for name in SECTION_DESC}
        self.hub.update()

    def hub_info(self, name):
        s = self.store.save
        if not s:
            return "Open a save first"
        if name == "GENERAL":
            return f"{s.value(sd.GOLD):,} G  ·  {s.value(sd.SP):,} SP"
        if name == "CHARACTERS":
            return f"{s.fighters_unlocked()} / {len(sd.FIGHTERS)} unlocked"
        if name == "ITEMS":
            return f"{len(sd.ITEMS)} items"
        if name == "STATS":
            return f"{len(sd.STATS)} categories"
        if name == "BACKUPS":
            n = len(sd.list_backups())
            return f"{n} backup{'s' if n != 1 else ''}"
        return ""

    # -------------------------------------------------------- navigation --
    def show_hub(self, intro=False):
        self.current = None
        self.hub.tile_info = {name: self.hub_info(name) for name in SECTION_DESC}
        self.set_header(APP_TITLE)
        STATUS.default = "Choose a section"
        for wdg in self.section_widgets:
            wdg.hide()
        self.back_btn.hide()
        for button in self.header_buttons:
            button.hide()
        self.update()
        self.hub.show(); self.hub.raise_()
        self.hub.play_intro(1000 if intro else 520)
        self.hub.setFocus()
        STATUS.hide(); self.toast_w.raise_()
        STATUS.update()

    def open_section(self, name):
        if not self.store.loaded:
            self.open_dialog(then=lambda: self.open_section(name))
            return
        self.hub.hide()
        STATUS.show()
        for button in self.header_buttons:
            button.show()
        self.update()
        self.back_btn.show()
        self.panel.show()
        for i, t in enumerate(self.tabs):  # tabs drop in, staggered
            start = QPoint(self.tab_x[i] + 90 + 30 * i, TAB_Y)
            t.show(); t.move(start)
            a = QPropertyAnimation(t, b"pos", t)
            a.setDuration(420); a.setStartValue(start); a.setEndValue(QPoint(self.tab_x[i], TAB_Y))
            a.setEasingCurve(QEasingCurve.OutBack)
            QTimer.singleShot(i * 45, a.start)
            t.__dict__["_drop"] = a
        self.key_q.show(); self.key_e.show()
        self.select(name, direction=0)
        STATUS.raise_(); self.toast_w.raise_()

    def select(self, name, direction=None):
        idx = [s[0] for s in SECTIONS].index(name)
        if direction is None:
            direction = 1 if self.current is None or idx >= self.current else -1
        prev = self.current
        self.current = idx
        if prev is not None and prev != idx:
            play("tab")
        self.set_header(name)
        STATUS.default = SECTION_DESC[name]
        for i, t in enumerate(self.tabs):
            t.setChecked(i == idx)
        self.empty.setVisible(not self.store.loaded)
        if not self.store.loaded:
            for pg in self.pages:
                pg.hide()
            return
        page = self.pages[idx]
        page.refresh()
        for j, pg in enumerate(self.pages):
            if j != idx:
                pg.hide()
        page.show(); page.raise_()
        if prev != idx:
            start = QPoint(70 * (direction or 1), 8) if direction else QPoint(0, 40)
            a = QPropertyAnimation(page, b"pos", page)
            a.setDuration(340); a.setStartValue(start); a.setEndValue(QPoint(0, 8))
            a.setEasingCurve(QEasingCurve.OutCubic)
            page.__dict__["_slide"] = a
            eff = QGraphicsOpacityEffect(page); page.setGraphicsEffect(eff)
            tween(page, "fade", 0, 1, 300, lambda v: eff.setOpacity(v), done=lambda: page.setGraphicsEffect(None))
            a.start()
        focusable = self.focusables(page)
        (focusable[0] if focusable else self).setFocus()

    def cycle(self, d):
        if self.current is None:
            return
        n = (self.current + d) % len(SECTIONS)
        self.select(SECTIONS[n][0], direction=d)

    # --------------------------------------------------------------- file --
    def open_dialog(self, then=None):
        if self.store.dirty:
            ConfirmOverlay(self, "Discard changes?", "You have unsaved changes. Open another file anyway?",
                           [("SAVE FIRST", G["save"], "yellow", lambda: self.save_file(after=lambda: self._open(then))),
                            ("DISCARD", G["close"], "red", lambda: self._open(then)),
                            ("CANCEL", G["back"], "dark", None)]).open()
        else:
            self._open(then)

    def _open(self, then=None):
        start = self.store.save.path if self.store.save else (sd.default_save_path() or os.path.expanduser("~"))
        path, _ = QFileDialog.getOpenFileName(self, "Open system_data.bin", start, "Smash save (system_data.bin *.bin);;All files (*)")
        if not path:
            return
        try:
            self.store.load(path)
        except sd.InvalidSave as e:
            ConfirmOverlay(self, "Not a valid save", str(e), [("OK", G["check"], "yellow", None)]).open()
            return
        self.toast("SAVE FILE LOADED")
        if self.current is not None:
            self.select(SECTIONS[self.current][0], direction=0)
        if then:
            then()

    def save_file(self, after=None):
        row = QApplication.focusWidget()
        row = row.parent() if isinstance(row, QLineEdit) else None
        if isinstance(row, StatRow):
            row.commit()  # a number still being typed counts as an edit
        if not self.store.loaded:
            self.toast("OPEN A SAVE FIRST", "error"); return
        if not self.store.dirty:
            self.toast("NO CHANGES TO SAVE")
            if after:
                after()
            return
        if sd.ryujinx_running():
            ConfirmOverlay(self, "Ryujinx is running",
                           "If the game is open, it will overwrite your changes (or the save may get corrupted). "
                           "<b>Close the game in Ryujinx first.</b>",
                           [("SAVE ANYWAY", G["warn"], "red", lambda: self._write(after)),
                            ("CANCEL", G["back"], "dark", None)]).open()
        else:
            self._write(after)

    def _write(self, after=None):
        try:
            dest = self.store.write()
        except OSError as e:
            ConfirmOverlay(self, "Save failed", f"{e}", [("OK", G["check"], "yellow", None)]).open()
            return
        mirrored = sd.mirror_path(self.store.save.path)
        play("save")
        self.toast("SAVED!" + ("  BOTH SLOTS UPDATED" if mirrored else "") + ("  ·  BACKUP MADE" if dest else ""))
        if self.current is not None and SECTIONS[self.current][0] == "BACKUPS":
            self.pages[self.current].refresh()
        if after:
            after()

    # ------------------------------------------------------------ events --
    def keyPressEvent(self, e):
        k, mod = e.key(), e.modifiers()
        if mod & Qt.ControlModifier and k == Qt.Key_S:
            self.save_file()
        elif mod & Qt.ControlModifier and k == Qt.Key_O:
            self.open_dialog()
        elif mod & Qt.ControlModifier and k == Qt.Key_Q:
            self.close()
        elif k == Qt.Key_Escape and self.current is not None:
            play("back")
            self.show_hub()
        elif k == Qt.Key_Escape:
            self.ask_quit()
        elif k == Qt.Key_F1:
            play("select")
            HelpOverlay(self).open()
        elif k == Qt.Key_M:
            on = SFX.toggle() if SFX else False
            self.toast("SOUND ON" if on else "SOUND OFF")
        elif k in (Qt.Key_Q, Qt.Key_PageUp) and self.current is not None:
            self.cycle(-1)
        elif k in (Qt.Key_E, Qt.Key_PageDown) and self.current is not None:
            self.cycle(1)
        elif k in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down) and self.current is not None:
            self.move_focus(k)
        else:
            super().keyPressEvent(e)

    @staticmethod
    def focusables(page):
        return [w for w in page.findChildren(QWidget)
                if isinstance(w, (AnimButton, QLineEdit, QListWidget)) and w.isVisibleTo(page)
                and w.focusPolicy() & Qt.TabFocus]

    def move_focus(self, k):
        if self.current is None or self.overlay_open():
            return
        page = self.pages[self.current]
        spatial_focus(page, self.focusables(page), k)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and e.pos().y() < HB and self.windowHandle():
            self.windowHandle().startSystemMove()

    def closeEvent(self, e):
        if self.store.dirty and not self.force_close:
            e.ignore()

            def quit_now():
                self.force_close = True; self.close()
            ConfirmOverlay(self, "Unsaved changes", "Save before quitting?",
                           [("SAVE & QUIT", G["save"], "yellow", lambda: self.save_file(after=quit_now)),
                            ("QUIT", G["close"], "red", quit_now),
                            ("CANCEL", G["back"], "dark", None)]).open()
        else:
            e.accept()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        bg = QLinearGradient(0, 0, w, h)
        bg.setColorAt(0, QColor("#17171b")); bg.setColorAt(1, QColor("#0b0b0e"))
        p.fillRect(self.rect(), bg)
        if self.current is None:
            p.fillRect(QRectF(0, 0, w, 32), QColor("#090909"))
            p.setFont(label_font(16, QFont.DemiBold)); p.setPen(WHITE)
            p.drawText(QRectF(20, 0, w - 40, 32), Qt.AlignVCenter, "ULTIMATE SMASHER   /   Save editor")
            return
        draw_streaks(p, w, h, self.streaks, self.phase)
        band = QLinearGradient(0, 0, 0, HB)
        band.setColorAt(0, QColor("#e3001b")); band.setColorAt(1, QColor("#9a0013"))
        p.setBrush(band)
        p.drawPolygon(QPolygonF([QPointF(0, 0), QPointF(w, 0), QPointF(w, HB - 8), QPointF(0, HB + 4)]))
        p.setBrush(QColor(0, 0, 0, 70))
        for x in (0.70, 0.735):
            p.drawPolygon(QPolygonF([QPointF(w * x, 0), QPointF(w * x + 26, 0), QPointF(w * x - 4, HB), QPointF(w * x - 30, HB)]))
        p.setBrush(QColor(12, 12, 15, 235))
        p.drawPolygon(QPolygonF([QPointF(w * 0.62, 0), QPointF(w, 0), QPointF(w, HB - 8), QPointF(w * 0.62 - 26, HB - 4)]))
        p.setPen(QPen(QColor(255, 255, 255, 120), 1.5))
        p.drawLine(QPointF(w * 0.62 - 26, HB - 4), QPointF(w, HB - 8))
        p.setPen(Qt.NoPen); p.setBrush(QColor(255, 60, 70, 150))
        p.drawPath(smash_ball_path(QPointF(w * 0.555, HB * 0.55), 48))
        tr = QRectF(w * 0.62, 0, w * 0.38 - 132, HB - 6)
        k = self.header_k
        p.save(); p.setOpacity(k)
        p.setFont(fit_font(game_font, self.header_title.title(), tr.width(), 27)); p.setPen(WHITE)
        p.drawText(tr.translated((1 - k) * 60, 0), Qt.AlignVCenter | Qt.AlignRight, self.header_title.title())
        p.restore()
        p.setBrush(QColor(200, 0, 24, 220))
        p.drawPolygon(QPolygonF([QPointF(w * 0.35, h), QPointF(w, h - 22), QPointF(w, h)]))


class EmptyState(QWidget):
    """Shown in the section panel while no save file is loaded."""

    def __init__(self, win, parent):
        super().__init__(parent)
        self.cta = PlateButton("OPEN SAVE FILE", self, G["open"], "yellow", slant=26)
        self.cta.clicked.connect(win.open_dialog)

    def resizeEvent(self, e):
        self.cta.setGeometry(int((self.width() - 470) / 2), int(self.height() * 0.55), 470, 104)

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        cy = h * 0.16
        p.setPen(Qt.NoPen); p.setBrush(QColor("#202020"))
        p.drawPath(smash_ball_path(QPointF(w / 2, cy), 28))
        p.setFont(heavy_italic(46)); p.setPen(QColor("#171717"))
        p.drawText(QRectF(0, h * 0.27, w, 56), Qt.AlignCenter, "NO SAVE FILE LOADED")
        p.setFont(label_font(19, QFont.Bold, True)); p.setPen(QColor("#424242"))
        p.drawText(QRectF(0, h * 0.27 + 66, w, 30), Qt.AlignCenter,
                   "Open your system_data.bin to edit fighters, items and stats.")


STYLE = """
* { font-family: "Barlow Condensed"; }
QToolTip { background: #111114; color: #ffffff; border: 2px solid #ffd400; font-size: 15px; font-weight: 700; }
QScrollBar:vertical { background: rgba(255,255,255,0.06); width: 10px; margin: 0; border: none; }
QScrollBar::handle:vertical { background: #ffd400; min-height: 30px; border-radius: 3px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
"""


def load_fonts():
    """Register every bundled font (Font Awesome, Nunito, Barlow Condensed)."""
    global FA
    folder = os.path.join(BASE, "fonts")
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".ttf"):
            continue
        fid = QFontDatabase.addApplicationFont(os.path.join(folder, name))
        fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
        if name.startswith("fa-solid") and fams:
            FA = fams[0]


def main(argv):
    """Open a compact desktop window; --fullscreen opts into screen scaling."""
    global SFX
    windowed = "--fullscreen" not in argv or "--window" in argv
    argv = [a for a in argv if a not in ("--window", "--fullscreen")]
    app = QApplication(argv)
    if not windowed and not os.environ.get("SMASHER_SCALED"):
        g = app.primaryScreen().geometry()
        f = min(g.width() / 1040, g.height() / 590)
        if abs(f - 1) > 0.02:  # restart once with Qt's own scaling (crisp, not stretched)
            env = dict(os.environ, SMASHER_SCALED="1",
                       QT_SCALE_FACTOR=f"{float(os.environ.get('QT_SCALE_FACTOR', '1')) * f:.4f}")
            os.execve(sys.executable, [sys.executable] + sys.orig_argv[1:], env)
    if windowed:
        set_stage(1040, 590)
    else:
        g = app.primaryScreen().geometry()
        set_stage(g.width(), g.height())
    app.setApplicationName("Ultimate Smasher")
    app.setDesktopFileName("ultimate-smasher")
    app.setWindowIcon(QIcon(os.path.join(IMG, "icon.ico")))
    app.setStyle("fusion")
    app.setStyleSheet(STYLE)
    load_fonts()
    SFX = sfx.Player()
    path = argv[1] if len(argv) > 1 else None
    win = MainWindow(path)
    if windowed:
        win.show()
    else:
        win.showFullScreen()
    win.activateWindow()
    return app, win
