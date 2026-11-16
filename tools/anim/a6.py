"""Why cells have different sizes: one cell splits into 4, 16, 64; the grid is fixed, so only four quarters of one cell merge."""

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
    ex = {13: "a few city blocks", 12: "a city district", 11: "a part of a town", 10: "a small town",
          9: "a large town", 8: "a city", 7: "a large city and its surroundings", 6: "a large region"}
    rows = [[lv, area(lv), ex[lv]] for lv in range(13, 5, -1)]
    tr.table("levels", ["Level", "Average area km²", "Example"], rows, [0, 2, "s"])
    tr.legend = {"p:cell12": "Cell", "p:sub": "Cell after splitting", "p:hl": "One cell and its quarters",
                 "p:cell": "Cells one level bigger", "p:in": "Four quarters of one cell: can be combined",
                 "p:hl2": "Four different bigger cells", "p:kept": "A square of four that is not a cell"}
    tr.step("A cell can be cut into four equal quarters. Here is one cell.", {"L0": "cell12", "t0": "b"})
    tr.step("Cut it once: 4 cells, each a quarter of the size. The orange one is a quarter of the original.",
            {"@l1": "sub", "L0": "cell12", "t0": "", "t1": "b", "L1:0:0": "hl"})
    tr.step("Cut each of those again: 16 cells. The orange cell is now a sixteenth of the original and sits inside the orange quarter.",
            {"@l1": "", "L1:0:0": "hl", "@l2": "sub", "L2:0:0": "hl", "t1": "", "t2": "b"})
    tr.step("And again: 64 cells. Every cut makes cells four times smaller. The number of cuts is the level of a cell: "
            "a higher level means a smaller cell.",
            {"@l2": "", "L2:0:0": "hl", "@l3": "sub", "L3:0:0": "hl", "t2": "", "t3": "b"})
    # fixed grid: which four cells can be merged
    ok = [(4, 4), (5, 4), (4, 5), (5, 5)]          # the four quarters of L2:2:2
    bad = [(1, 1), (2, 1), (1, 2), (2, 2)]         # a 2x2 block across four bigger cells
    s3 = S / 8
    tr.text("tok", [ox + 5 * s3, oy + 6 * s3 + 0.35], "✓ one cell", "tx")
    tr.text("tbad", [ox + 2 * s3, oy + 3 * s3 + 0.35], "✗ not a cell", "tx")
    clear = {"@l3": "sub", "@l2": "", "@l1": "", "L0": "cell12", "t3": "",
             "L1:0:0": "", "L2:0:0": "", "L3:0:0": "sub"}
    tr.step("This grid is not made for your field. It is one fixed grid over the whole world, worked out in advance: "
            "every cell of every level has its fixed place, and the game only picks cells from it.",
            {**clear, "@l2": "cell"})
    tr.step("So four small cells can only be combined if they are the four quarters of one bigger cell of the grid. "
            "These four are: together they are exactly one cell of the next level.",
            {"L2:2:2": "hl", **{f"L3:{i}:{j}": "in" for i, j in ok}, "tok": "b"})
    tr.step("These four also form a square, but no bigger cell of the grid lies there: they belong to four different "
            "bigger cells (purple). They can never be combined into one cell.",
            {"L2:2:2": "cell", **{f"L3:{i}:{j}": "sub" for i, j in ok}, "tok": "",
             **{f"L2:{i}:{j}": "hl2" for i in (0, 1) for j in (0, 1)},
             **{f"L3:{i}:{j}": "kept" for i, j in bad}, "tbad": "b"})
    tr.step(f"For MU the smallest cells have level 13, about {area(13):.1f} km², a few city blocks. "
            f"Level 12 is about {area(12):.0f} km², level 10 about {area(10):.0f} km², a small town, and level 6 about "
            f"{area(6):,.0f} km². A small field uses small cells; a big field uses bigger cells, with a lower level.",
            {"@l2": "", "@l3": "sub", "tbad": "", "t3": "b"}, tb=["levels", len(rows), None])
    tr.extra["summary"] = [["Smallest cell used for MU", f"level 13, about {area(13):.2f} km²"],
                           ["Each cut", "4 cells, a quarter of the area each"]]
    return tr.finish()
