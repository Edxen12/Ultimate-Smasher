"""Main-menu geometry in a virtual 1920x1080 canvas (no painting here).

Shapes were measured from a 1080p capture of the game's main menu. The hub is
scaled uniformly to the widget and centred, so the disc always stays round.
"""
from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QPainterPath, QPolygonF, QTransform

VW, VH = 1920, 1080
DISC_C = QPointF(968, 510)
ART_R = 226        # key art radius
RING_W = 18        # white ring
EDGE_W = 9         # orange outer ring
CUT_R = 282        # tiles are cut by this circle
RAIL = QRectF(1736, -40, 230, VH + 80)
STRIP = QRectF(-400, 962, 2136 + 400, 160)
TOP = QRectF(0, 0, 930, 98)

TILE_ORDER = ("CHARACTERS", "ITEMS", "GENERAL", "BACKUPS", "STATS", "SAVE")

_POLYS = {
    "CHARACTERS": [(-60, 102), (912, 102), (912, 612), (-60, 612)],
    "ITEMS": [(-60, 640), (828, 640), (828, 962), (-60, 962)],
    "GENERAL": [(948, -60), (1760, -60), (1760, 336), (948, 318)],
    "BACKUPS": [(1200, 364), (1760, 364), (1760, 618), (1222, 618)],
    "STATS": [(866, 652), (1672, 652), (1580, 962), (866, 962)],
    "SAVE": [(1650, 838), (1760, 838), (1760, 962), (1613, 962)],
}

# Where the label/icon block sits in each tile (centre, virtual units).
LABEL_C = {
    "CHARACTERS": QPointF(410, 360), "ITEMS": QPointF(385, 800),
    "GENERAL": QPointF(1385, 150), "BACKUPS": QPointF(1478, 490),
    "STATS": QPointF(1240, 815), "SAVE": QPointF(1684, 902),
}

NEIGHBORS = {
    "CHARACTERS": {Qt.Key_Right: "GENERAL", Qt.Key_Down: "ITEMS"},
    "ITEMS": {Qt.Key_Up: "CHARACTERS", Qt.Key_Right: "STATS"},
    "GENERAL": {Qt.Key_Left: "CHARACTERS", Qt.Key_Down: "BACKUPS"},
    "BACKUPS": {Qt.Key_Up: "GENERAL", Qt.Key_Down: "STATS", Qt.Key_Left: "CHARACTERS"},
    "STATS": {Qt.Key_Up: "BACKUPS", Qt.Key_Left: "ITEMS", Qt.Key_Right: "SAVE"},
    "SAVE": {Qt.Key_Left: "STATS", Qt.Key_Up: "BACKUPS"},
}


def _tiles():
    cut = QPainterPath(); cut.addEllipse(DISC_C, CUT_R, CUT_R)
    out = {}
    for name, pts in _POLYS.items():
        path = QPainterPath(); path.addPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))
        path.closeSubpath()
        out[name] = path.subtracted(cut) if name != "SAVE" else path
    return out


TILES = _tiles()


def rail_items(n):
    """Hit rects of the n rail icons, top to bottom (virtual units)."""
    top, step = 120, 132
    return [QRectF(1770, top + i * step, 120, 112) for i in range(n)]


def transform(w, h):
    """Uniform scale of the virtual canvas into a w x h widget, centred."""
    s = min(w / VW, h / VH)
    return QTransform().translate((w - VW * s) / 2, (h - VH * s) / 2).scale(s, s)


def to_virtual(w, h, pt):
    inv, _ = transform(w, h).inverted()
    return inv.map(QPointF(pt))


def tile_at(w, h, pt):
    v = to_virtual(w, h, pt)
    for name, path in TILES.items():
        if path.contains(v):
            return name
    return None


def rail_at(w, h, pt, n):
    v = to_virtual(w, h, pt)
    for i, r in enumerate(rail_items(n)):
        if r.contains(v):
            return i
    return None


def tile_center(name, w=VW, h=VH):
    """Widget-space point that lies inside the tile (for tests and pads)."""
    return transform(w, h).map(LABEL_C[name])
