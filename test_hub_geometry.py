"""Geometry of the main menu: tiles are disjoint, avoid the disc and scale cleanly."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QPointF, Qt

import hub_geometry as hg

SIZES = ((1040, 590), (1280, 1024), (1920, 1080), (3840, 2160))


class HubGeometryTest(unittest.TestCase):
    def test_tiles_disjoint(self):
        names = list(hg.TILES)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                inter = hg.TILES[a].intersected(hg.TILES[b]).boundingRect()
                self.assertLess(inter.width() * inter.height(), 1.0, (a, b))

    def test_disc_and_gaps_are_not_tiles(self):
        for w, h in SIZES:
            disc = hg.transform(w, h).map(hg.DISC_C)
            self.assertIsNone(hg.tile_at(w, h, disc))
            gap = hg.transform(w, h).map(QPointF(300, 626))  # between Fighters and Items
            self.assertIsNone(hg.tile_at(w, h, gap))

    def test_tile_centres_hit_their_tile(self):
        for w, h in SIZES:
            for name in hg.TILE_ORDER:
                self.assertEqual(hg.tile_at(w, h, hg.tile_center(name, w, h)), name, (name, w, h))

    def test_scale_is_uniform(self):
        for w, h in SIZES:
            t = hg.transform(w, h)
            self.assertAlmostEqual(t.m11(), t.m22())
            box = t.mapRect(hg.TILES["CHARACTERS"].boundingRect().united(hg.RAIL))
            self.assertGreater(box.width(), 0)

    def test_neighbors_valid_and_connected(self):
        for moves in hg.NEIGHBORS.values():
            for key, dst in moves.items():
                self.assertIn(key, (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down))
                self.assertIn(dst, hg.TILE_ORDER)
        seen, todo = set(), ["CHARACTERS"]
        while todo:
            n = todo.pop()
            if n not in seen:
                seen.add(n); todo.extend(hg.NEIGHBORS[n].values())
        self.assertEqual(seen, set(hg.TILE_ORDER))

    def test_tiles_stay_above_strip(self):
        for name, path in hg.TILES.items():
            self.assertLessEqual(path.boundingRect().bottom(), hg.STRIP.top() + 1, name)


if __name__ == "__main__":
    unittest.main()
