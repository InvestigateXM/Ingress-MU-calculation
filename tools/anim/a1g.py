"""Simple made-up example of how a cell's density is read from pixels."""

from .common import *  # noqa: F401,F403


def _head(tip, frm, length=0.16, half=0.07):
    """Triangle (arrowhead) with its tip at `tip`, pointing away from `frm`."""
    dx, dy = tip[0] - frm[0], tip[1] - frm[1]
    d = math.hypot(dx, dy)
    ux, uy = dx / d, dy / d
    bx, by = tip[0] - ux * length, tip[1] - uy * length
    return [list(tip), [bx - uy * half, by + ux * half], [bx + uy * half, by - ux * half]]


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
        tr.poly(f"ah:{i}", _head([sx, sy], [x, y]), "ah")
        ctr = [key[0] + 0.5, key[1] + 0.5]
        tr.line(f"mb:{i}", ctr, [x, y], "mb")  # arrow ends just before the point
        dd = math.hypot(x - ctr[0], y - ctr[1])
        tip = [x - (x - ctr[0]) / dd * 0.1, y - (y - ctr[1]) / dd * 0.1]
        tr.poly(f"ah2:{i}", _head(tip, ctr, 0.13, 0.055), "ah2")
        tr.text(f"vl:{i}", [x + 0.15, y], f"{counts[key]:,}", "vl", "start")
    n = {k: read.count(k) for k in counts}
    assert sum(n.values()) == 16 and all(n.values())
    total = sum(n[k] * counts[k] for k in counts)
    assert total % 16 == 0
    mean = total // 16
    for (c, r), v in counts.items():
        tr.text(f"bd:{c}:{r}", [c + 0.5, r + 0.1], f"×{n[(c, r)]}", "bd")
        tr.text(f"ct:{c}:{r}", [c + 0.5, r + 0.91], f"{v:,}", "ct")

    tr.legend = {"p:grid": "Pixel of the population map", "p:hl": "The cell", "p:read": "Pixel that is read",
                 "d:dot": "Measuring point", "d:ghost": "Original position", "d:shift": "Point moved half a pixel up and left", "l:move": "Shift to where the game looks", "l:move2": "Count brought back to the point"}
    outside = sum(1 for (c, r) in counts if not (1 <= c <= 2 and 1 <= r <= 2))
    tr.step("This made-up cell (orange) lies exactly over four pixels of the population map. "
            "The map stores one count of people for each pixel, and the game wants one density for the cell, in MU per km².",
            {"@px": "grid", "cell": "hl"})
    tr.step("The game places 16 measuring points in the cell, evenly spaced in 4 rows of 4.", {"@d": "dot"})
    tr.step("Before reading the map, the game moves every point half a pixel up and to the left (the arrows). "
            "The game does not read the pixel a point lies in. It looks half a pixel up and to the left and reads the pixel it finds there.",
            {"@d": "ghost", "@sh": "shift", "@mv": "move", "@ah": "ah"})
    s = {"@d": "", "@mv": "", "@ah": "", "@ln": "ptr"}
    s.update({f"px:{c}:{r}": "read" for (c, r) in counts})
    s.update({f"bd:{c}:{r}": "b" for (c, r) in counts})
    tr.step(f"Each shifted point reads the pixel it now lies in. Nine pixels are read, and a pixel read by several points "
            f"counts several times (the ×2 and ×4 badges). The pixels that count can lie partly or even completely outside the cell: here {outside} of the 9 lie completely outside, "
            f"and they still count.", s)
    tr.step("These are the counts of the nine pixels (made-up numbers).",
            {f"ct:{c}:{r}": "m" for (c, r) in counts})
    s = {"@sh": "", "@ln": "", "@px": "grid", "@bd": "", "@ct": "", "@d": "dot", "@mb": "move2", "@ah2": "ah2", "cell": "hl"}
    s.update({f"px:{c}:{r}": "read" for (c, r) in counts})
    s.update({f"vl:{i}": "t" for i in range(16)})
    tr.step("Now the numbers go back. Each point takes the count of the pixel it read (purple arrows) and keeps it at its original place in the cell. "
            "The shift was only where the game looked: the 16 numbers belong to the 16 points inside the cell.", s)
    terms = " + ".join(f"{n[k]}×{counts[k]:,}" for k in sorted(counts, key=lambda k: (k[1], k[0])) if counts[k])
    tr.step(f"The density of the cell is the mean of these 16 numbers. Pixels with a count of 0 add nothing. "
            f"So every spot in this cell counts as {mean} MU per km², whatever is actually inside it.",
            {"@mb": "", "@ah2": "", "@vl": "b"},
            eq=f"({terms}) / 16 = {total:,} / 16 = {mean} MU per km²")
    return tr.finish(view=[-0.8, -0.1, 5.6, 4.2])
