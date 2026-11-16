"""Why cells have different sizes, part 1 (made-up drawing): one cell splits into 4, 16, 64."""

from .common import *  # noqa: F401,F403


def build(calc):
    tr = Trace("a6", "Why cells have different sizes", Proj(48.0, 11.0))
    tr.extra["schematic"] = True
    S = 8.0                                  # side of the big cell, km (made-up drawing)
    ox, oy = 0.0, 0.0

    def square(eid, x, y, s, group):
        tr.poly(eid, [[x, y], [x + s, y], [x + s, y + s], [x, y + s]], group)

    square("L0", ox, oy, S, "l0")
    for lvl, n, grp in ((1, 2, "l1"), (2, 4, "l2"), (3, 8, "l3")):
        s = S / n
        for i in range(n):
            for j in range(n):
                square(f"L{lvl}:{i}:{j}", ox + i * s, oy + j * s, s, grp)
    tr.text("t0", [ox + S / 2, oy + S / 2], "1 cell", "tx")
    tr.text("t1", [ox + S / 2, oy + S + 0.9], "4 cells", "tx")
    tr.text("t2", [ox + S / 2, oy + S + 0.9], "16 cells", "tx")
    tr.text("t3", [ox + S / 2, oy + S + 0.9], "64 cells", "tx")
    area = lambda lv: 4 * math.pi * RE ** 2 / (6 * 4 ** lv)
    tr.legend = {"p:cell12": "Cell", "p:sub": "Cell after splitting", "p:hl": "One cell and its quarters"}
    tr.step("A cell can be cut into four equal quarters. Here is one cell.", {"L0": "cell12", "t0": "b"})
    tr.step("Cut it once: 4 cells, each a quarter of the size. The orange one is a quarter of the original.",
            {"@l1": "sub", "L0": "cell12", "t0": "", "t1": "b", "L1:0:0": "hl"})
    tr.step("Cut each of those again: 16 cells. The orange cell is now a sixteenth of the original and sits inside the orange quarter.",
            {"@l1": "", "L1:0:0": "hl", "@l2": "sub", "L2:0:0": "hl", "t1": "", "t2": "b"})
    tr.step("And again: 64 cells. Every cut makes cells four times smaller. The number of cuts is the level of a cell: "
            "a higher level means a smaller cell.",
            {"@l2": "", "L2:0:0": "hl", "@l3": "sub", "L3:0:0": "hl", "t2": "", "t3": "b"})
    tr.extra["summary"] = [["Smallest cell used for MU", f"level 13, about {area(13):.2f} km²"],
                           ["Each cut", "4 cells, a quarter of the area each"]]
    return tr.finish()
