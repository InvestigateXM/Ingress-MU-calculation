"""The big picture: field, cells, area x density, sum (no pixels, levels or tokens)."""

from .common import *  # noqa: F401,F403


def build(calc):
    f = calc.field(A3_FIELD)
    assert f["mu"] == EXPECTED_MU["a3"], f["mu"]
    pts = A3_FIELD
    # same centre and view as trace a3, so its orientation map is reused
    lat0, lng0 = sum(p[0] for p in pts) / 3e6, sum(p[1] for p in pts) / 3e6
    proj = Proj(lat0, lng0)
    tr = Trace("a0", "The big picture", proj)
    cells = f["cells"]
    for c in cells:
        tr.poly(f"c:{c['t']}", [proj.vec(v) for v in cell_vecs(c["id"])], "c")
        cp = [proj.vec(v) for v in clip_vecs(pts, c["id"])]
        tr.poly(f"cp:{c['t']}", cp, "cp")
        cell_label(tr, f"d:{c['t']}", c["id"], proj, fmt(c["d"], 0), "d")
        cx, cy = sum(p[0] for p in cp) / len(cp), sum(p[1] for p in cp) / len(cp)
        tr.text(f"m:{c['t']}", [round(cx, 4), round(cy, 4)], fmt(c["c"], 0), "m")
    tr.poly("fld", [proj.ll(p[0] / 1e6, p[1] / 1e6) for p in pts])
    vals, _ = bins([c["d"] for c in cells])
    tr.extra["bins"] = {f"c:{c['t']}": b for c, b in zip(cells, vals)}
    tr.extra["ramp"] = {"label": "MU per km² (density)", "min": min(c["d"] for c in cells),
                        "max": max(c["d"] for c in cells), "log": True}
    tr.extra["map"] = "a3"
    tr.table("cells", CELL_HEAD, field_rows(f), CELL_FMT)
    tr.legend = {"p:field": "Field (triangle)", "p:cell": "Cell outline", "p:clip": "Part of a cell inside the field"}
    tr.step("This is a field: a triangle between three portals.", {"fld": "field"})
    tr.step("To measure it, the game cuts the world into square-ish cells. Here is the grid of cells over this field.",
            {"@c": "cell"})
    tr.step("Each cell has a density: how many MU one km² is worth there. Darker cells are denser, as on a population map.",
            {"@c": "heat", "@d": "t"})
    tr.step("Only the part of the field inside a cell counts for that cell. Each part is worth its area times the cell's density, "
            "in MU. How the game chooses which cell sizes to use is shown in the last animations.",
            {"@c": "cell", "@cp": "clip", "@d": "", "@m": "t"})
    tr.step("Add up the MU of all cells and round: this field is worth " + fmt(f["mu"], 0) + " MU.",
            {},
            eq=f"sum of the cells = {fmt(f['total'], 3)}, rounded = {fmt(f['mu'], 0)} MU")
    tr.extra["summary"] = [
        ["Area of the field", f"{f['area']:.3f} km²"], ["Cells", str(len(cells))],
        ["Sum of contributions", fmt(f["total"], 3)], ["MU", fmt(f["mu"], 0)],
    ]
    tr.extra["cells"] = {"head": CELL_HEAD, "rows": field_rows(f), "fmt": CELL_FMT}
    tr.extra["check"] = check_block(f)
    return tr.finish(focus={"fld"} | {f"c:{c['t']}" for c in cells}, view=[-4.635, -3.074, 9.587, 7.19])
