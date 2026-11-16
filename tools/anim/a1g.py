"""Simple made-up example of how a cell's density is read from pixels."""

from .common import *  # noqa: F401,F403


def build(calc):
    tr = Trace("a1g", "How a cell's density is read from pixels", Proj(0.0, 0.0))
    tr.extra["schematic"] = True
    # Pixel (col, row) is the unit square [col, col+1] x [row, row+1]; y grows downwards.
    # The cell is the square [1, 3]^2: it lies exactly over the four pixels in the middle.
    counts = {(0, 0): 0, (1, 0): 100, (2, 0): 400,
              (0, 1): 100, (1, 1): 1000, (2, 1): 400,
              (0, 2): 0, (1, 2): 400, (2, 2): 0}
    for r in range(4):
        for c in range(4):
            tr.poly(f"px:{c}:{r}", [[c, r], [c + 1, r], [c + 1, r + 1], [c, r + 1]], "px")
    tr.poly("cell", [[1, 1], [3, 1], [3, 3], [1, 3]])

    pts = [(1.25 + 0.5 * a, 1.25 + 0.5 * b) for b in range(4) for a in range(4)]
    read = []
    for i, (x, y) in enumerate(pts):
        sx, sy = x - 0.5, y - 0.5
        key = (math.floor(sx), math.floor(sy))
        read.append(key)
        tr.dot(f"d:{i}", [x, y], "d")
        tr.dot(f"sh:{i}", [sx, sy], "sh")
        tr.line(f"mv:{i}", [x, y], [sx, sy], "mv")
        tr.line(f"ln:{i}", [sx, sy], [key[0] + 0.5, key[1] + 0.5], "ln")
    n = {k: read.count(k) for k in counts}
    assert sum(n.values()) == 16 and all(n.values())
    total = sum(n[k] * counts[k] for k in counts)
    assert total % 16 == 0
    mean = total // 16
    for (c, r), v in counts.items():
        tr.text(f"bd:{c}:{r}", [c + 0.5, r + 0.1], f"×{n[(c, r)]}", "bd")
        tr.text(f"ct:{c}:{r}", [c + 0.5, r + 0.91], f"{v:,}", "ct")

    tr.legend = {"p:grid": "Pixel of the population map", "p:hl": "The cell", "p:read": "Pixel that is read",
                 "d:dot": "Measuring point", "d:ghost": "Original position", "d:shift": "Point moved half a pixel up and left"}
    outside = sum(1 for (c, r) in counts if not (1 <= c <= 2 and 1 <= r <= 2))
    tr.step("This made-up cell (orange) lies exactly over four pixels of the population map. "
            "The map stores one count of people for each pixel, and the game wants one density for the cell, in MU per km².",
            {"@px": "grid", "cell": "hl"})
    tr.step("The game places 16 measuring points in the cell, evenly spaced in 4 rows of 4.", {"@d": "dot"})
    tr.step("Before reading the map, the game moves every point half a pixel up and left. "
            "This is how the population map is aligned with the cells.",
            {"@d": "ghost", "@sh": "shift", "@mv": "move"})
    s = {"@d": "", "@mv": "", "@ln": "ptr"}
    s.update({f"px:{c}:{r}": "read" for (c, r) in counts})
    s.update({f"bd:{c}:{r}": "b" for (c, r) in counts})
    tr.step(f"Each moved point reads the pixel it now lies in. Nine pixels are read, and a pixel read by several points "
            f"counts several times (the ×2 and ×4 badges). The pixels that count can lie partly or even completely outside the cell: here {outside} of the 9 lie completely outside, "
            f"and they still count.", s)
    tr.step("These are the counts of the nine pixels (made-up numbers).",
            {f"ct:{c}:{r}": "m" for (c, r) in counts})
    terms = " + ".join(f"{n[k]}×{counts[k]:,}" for k in sorted(counts, key=lambda k: (k[1], k[0])) if counts[k])
    tr.step(f"The density of the cell is the mean of the 16 readings. Pixels with a count of 0 add nothing. "
            f"So every spot in this cell counts as {mean} MU per km², whatever is actually inside it.", {},
            eq=f"({terms}) / 16 = {total:,} / 16 = {mean} MU per km²")
    return tr.finish(view=[-0.8, -0.1, 5.6, 4.2])
