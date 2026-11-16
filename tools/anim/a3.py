"""Big cells inside, small cells at the edge."""

from .common import *  # noqa: F401,F403
from .common import _clip, _normals  # noqa: F401


# ---------------------------------------------------------------- animation 3

def build_a3(calc):
    f = calc.field(A3_FIELD)
    assert f["mu"] == EXPECTED_MU["a3"], f["mu"]
    why = why_map(f)
    pts = A3_FIELD
    lat0, lng0 = sum(p[0] for p in pts) / 3e6, sum(p[1] for p in pts) / 3e6
    proj = Proj(lat0, lng0)
    tr = Trace("a3", "A field that contains a combined cell", proj)
    poly = lambda c: [proj.vec(v) for v in cell_vecs(c)]
    for c in f["cells"]:
        tr.poly(f"c:{c['t']}", poly(c["id"]), "c")
        if why[c["id"]] != "inside":
            tr.poly(f"cp:{c['t']}", [proj.vec(v) for v in clip_vecs(pts, c["id"])], "cp")
    tr.poly("fld", [proj.ll(p[0] / 1e6, p[1] / 1e6) for p in pts])
    cells12 = [c for c in f["cells"] if c["lv"] == 12]
    cells13 = [c for c in f["cells"] if c["lv"] == 13]
    inside12 = [c for c in cells12 if why[c["id"]] == "inside"]
    merged12 = [c for c in cells12 if why[c["id"]] == "merged"]
    assert inside12 and merged12 and len(cells12) == len(inside12) + len(merged12)
    big = inside12[0]
    bm = min(merged12, key=lambda c: abs(share(c) - 0.5))

    # stage 1: the level-13 cells that touch the field (quarters of the level-12 cells)
    quarters = {}
    for c in cells12:
        kids = [ch.id() for ch in CellId(c["id"]).children()]
        kov = overlaps(pts, kids)[0]
        assert len(kov) == 4 and all(ov > 0 for _, _, ov in kov)
        rows = []
        for (_, _, ov), kid in zip(kov, kids):
            d = calc.mean_density(kid) if c["t"] in (big["t"], bm["t"]) else float("nan")
            tr.poly(f"q:{tok(kid)}", poly(kid), "q")
            rows.append([tok(kid), cell_area_km2(kid), ov, d, ov * d])
        quarters[c["t"]] = rows
    n_small = len(cells13) + 4 * len(cells12)
    # density labels on the quarters of the two cells that are explained
    for key, nd_ in ((big["t"], 1), (bm["t"], 0)):
        for r in quarters[key]:
            cell_label(tr, f"qt:{r[0]}", cid_of(r[0]), proj, fmt(r[3], nd_), "qt")
    kid_rows = quarters[big["t"]]
    mean_kids = sum(r[3] for r in kid_rows) / 4
    assert math.isclose(mean_kids, big["d"], rel_tol=1e-12)
    sum_kids = sum(r[4] for r in kid_rows)
    merge_rows = kid_rows + [[big["t"] + " (parent)", big["area"], big["ov"], big["d"], big["c"]]]
    brows = quarters[bm["t"]]
    bsum = sum(r[4] for r in brows)
    nin = sum(1 for c in f["cells"] if why[c["id"]] == "inside")
    n12, n13 = len(cells12), len(cells13)
    tr.legend = {"p:field": "Field (triangle)", "p:cell": "Smallest cell (level 13) touching the field",
                 "p:hl": "Four quarters that are all needed", "p:in": "Whole cell used, completely inside the field",
                 "p:merged": "Whole cell used, cut by the field edge",
                 "p:edge": "Smallest cell, cut by the field edge", "p:clip": "Part of a cell inside the field"}
    q_of = lambda key: {f"q:{r[0]}": None for r in quarters[key]}
    qs = lambda key, st: {k: st for k in q_of(key)}
    start = {f"c:{c['t']}": "cell" for c in cells13}
    for c in cells12:
        start.update(qs(c["t"], "cell"))
    tr.step(f"This example field covers {f['area']:.1f} km². The game covers it with big cells where it can and small cells at the edge.", {"fld": "field"})
    tr.step(f"First the game finds every smallest cell (level 13) that touches the field. There are {n_small} of them.", start)
    st = {**qs(big["t"], "hl"), "@qt": ""}
    st.update({f"qt:{r[0]}": "t" for r in kid_rows})
    tr.step("In the middle, all four quarters of one cell are needed. When all four quarters of a cell are needed, the game uses the whole cell instead.", st)
    rel = abs(big["c"] - sum_kids) / big["c"]
    st = {f"c:{big['t']}": "in", **qs(big["t"], "cell")}
    tr.step(f"The whole cell is used (yellow). Its density is the mean of its four quarters: {fmt(big['d'], 1)} = mean of "
            f"{', '.join(fmt(r[3], 1) for r in kid_rows)}. Inside the field, merging changes almost nothing: "
            f"{fmt(big['c'], 0)} MU for the whole cell, {fmt(sum_kids, 0)} MU for the quarters.", st,
            eq=f"whole cell: {fmt(big['c'], 3)} MU    four quarters counted separately: {fmt(sum_kids, 3)} MU  (differ by {rel * 100:.3f} %)")
    st = {**qs(big["t"], ""), **{f"qt:{r[0]}": "" for r in kid_rows}, **qs(bm["t"], "hl")}
    st.update({f"qt:{r[0]}": "t" for r in brows})
    tr.step("Now a cell at the edge of the field. Its four quarters are all needed too, so the same rule applies.", st)
    st = {f"c:{bm['t']}": "merged", f"cp:{bm['t']}": "clip", **qs(bm["t"], "cell")}
    tr.step(f"The game uses {fmt(bm['c'], 0)} MU, the merged cell. Counting the four quarters separately would give {fmt(bsum, 0)}. "
            f"Here the field cuts the cell unevenly, so merging does change the number.", st,
            eq=f"whole cell: {bm['ov']:.5f} km² × {fmt(bm['d'], 3)} = {fmt(bm['c'], 3)} MU    four quarters: {fmt(bsum, 3)} MU")
    st = {**qs(bm["t"], ""), "@qt": ""}
    for c in f["cells"]:
        st[f"c:{c['t']}"] = STATE_OF[why[c["id"]]]
        if why[c["id"]] != "inside":
            st[f"cp:{c['t']}"] = "clip"
    for c in cells12:
        st.update(qs(c["t"], ""))
    nreg = len(f["regions"])
    regs = sorted(f["regions"].items())
    rrows = [[k, sum(1 for c in f["cells"] if c["reg"] == k), v, max(1, v)] for k, v in regs]
    tr.table("regions", ["Large region", "Cells", "Sum of contributions", "After minimum of 1"], rrows, ["s", 0, 3, 3])
    tr.step(f"The final covering has {len(f['cells'])} cells. Each gives its part of the field × its density; together they come to "
            f"{fmt(f['total'], 2)} MU in total. Each large region gives at least 1 MU, "
            f"{'and the one region here is far above that' if nreg == 1 else 'which makes no difference here'}.",
            st, tb=["regions", len(rrows), None],
            eq=f"sum of {len(f['cells'])} contributions = {fmt(f['total'], 3)}")
    tr.step(f"The game rounds to whole Mind Units: {fmt(f['total'], 2)} becomes {fmt(f['mu'], 0)} MU.", {},
            tb=["regions", len(rrows), None],
            eq=f"round half up({fmt(f['total'], 3)}) = {fmt(f['mu'], 0)} MU")
    tr.table("cells", CELL_HEAD, field_rows(f), CELL_FMT)
    tr.table("merge", ["Cell", "Area km²", "Overlap km²", "Density", "Contribution"], merge_rows, ["s", 5, 5, 3, 3])
    tr.extra["summary"] = [
        ["Portals", "; ".join(coord_str(p) for p in pts)], ["Area", f"{f['area']:.6f} km²"],
        ["Covering", f"{len(f['cells'])} cells: {n12} at level 12, {n13} at level 13"],
        ["Completely inside", f"{nin} cell ({big['t']})"],
        ["Mean of the four quarters of " + big["t"], fmt(mean_kids, 3)],
        ["Edge cell " + bm["t"] + ": whole / four quarters", f"{fmt(bm['c'], 3)} / {fmt(bsum, 3)}"],
        ["Sum of contributions", fmt(f["total"], 6)], ["MU", fmt(f["mu"], 0)],
    ]
    tr.extra["cells"] = {"head": CELL_HEAD, "rows": field_rows(f), "fmt": CELL_FMT}
    tr.extra["check"] = check_block(f)
    tr.extra["check"]["merge"] = {"parent": big["t"], "children": kid_rows, "parent_row": merge_rows[4]}
    return tr.finish(focus={"fld"} | {f"c:{c['t']}" for c in f["cells"]})


build = build_a3
