"""Animation 3."""

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
    inside12 = [c for c in f["cells"] if c["lv"] == 12 and why[c["id"]] == "inside"]
    merged12 = [c for c in f["cells"] if c["lv"] == 12 and why[c["id"]] == "merged"]
    assert inside12 and merged12
    big = inside12[0]
    # children of the fully contained cell
    kid_rows = []
    kids = [ch.id() for ch in CellId(big["id"]).children()]
    kov = overlaps(pts, kids)[0]
    for (cid, _, ov), kid in zip(kov, kids):
        d = calc.mean_density(kid)
        a = cell_area_km2(kid)
        assert math.isclose(ov, a, rel_tol=1e-9), "child not completely inside"
        tr.poly(f"k:{tok(kid)}", poly(kid), "k")
        cell_label(tr, f"kt:{tok(kid)}", kid, proj, fmt(d, 1), "kt")
        kid_rows.append([tok(kid), a, ov, d, ov * d])
    sum_kids = sum(r[4] for r in kid_rows)
    mean_kids = sum(r[3] for r in kid_rows) / 4
    assert math.isclose(mean_kids, big["d"], rel_tol=1e-12)
    merge_rows = kid_rows + [[big["t"] + " (parent)", big["area"], big["ov"], big["d"], big["c"]]]
    tr.table("merge", ["Cell", "Area km²", "Overlap km²", "Density", "Contribution"], merge_rows, ["s", 5, 5, 3, 3])
    diff = big["c"] - sum_kids
    # a merged level-12 cell at the boundary
    bm = min(merged12, key=lambda c: abs(share(c) - 0.5))
    bkids = [ch.id() for ch in CellId(bm["id"]).children()]
    bov = overlaps(pts, bkids)[0]
    brows = []
    for (cid, _, ov), kid in zip(bov, bkids):
        d = calc.mean_density(kid)
        tr.poly(f"b:{tok(kid)}", poly(kid), "b")
        cell_label(tr, f"bt:{tok(kid)}", kid, proj, fmt(d, 0), "bt")
        brows.append([tok(kid), cell_area_km2(kid), ov, d, ov * d])
    bsum = sum(r[4] for r in brows)
    brows.append([bm["t"] + " (parent)", bm["area"], bm["ov"], bm["d"], bm["c"]])
    tr.table("bmerge", ["Cell", "Area km²", "Overlap km²", "Density", "Contribution"], brows, ["s", 5, 5, 3, 3])
    # a boundary cell at level 13
    cand = [c for c in f["cells"] if c["lv"] == 13 and 0.3 < share(c) < 0.7]
    b13 = max(cand, key=lambda c: c["d"])
    tr.table("cells", CELL_HEAD, field_rows(f), CELL_FMT)
    nin = sum(1 for c in f["cells"] if why[c["id"]] == "inside")
    n12, n13 = sum(1 for c in f["cells"] if c["lv"] == 12), sum(1 for c in f["cells"] if c["lv"] == 13)
    tr.legend = {"p:field": "Field (triangle)", "p:in": "Cell completely inside the field",
                 "p:merged": "Level-12 cell cut by the field edge (four children final)",
                 "p:edge": "Level-13 cell cut by the field edge", "p:clip": "Part of a cell inside the field",
                 "p:cell": "Cell outline"}
    states_all = {f"c:{c['t']}": STATE_OF[why[c["id"]]] for c in f["cells"]}
    tr.step(f"An example field of {f['area']:.2f} km² ({'; '.join(coord_str(p) for p in pts)}).", {"fld": "field"})
    tr.step(f"The covering has {len(f['cells'])} cells: {n12} at level 12 and {n13} at level 13. One level-12 cell, {big['t']}, lies "
            f"completely inside the field. Two more level-12 cells, {', '.join(c['t'] for c in merged12)}, are cut by the field edge.",
            dict(states_all))
    tr.step(f"A cell that lies completely inside the field is not divided further. {big['t']} is one cell of level 12, with an area of "
            f"{big['area']:.3f} km². It has four level-13 children, which also lie completely inside the field. "
            f"The covering contains the parent, not the four children.",
            {"@c": "cell", f"c:{big['t']}": "in", "@k": "cell"})
    tr.step(f"Density of the parent: the mean of its 64 sample points. Each level-13 child has 16 of these 64 points, so the mean of "
            f"the four child densities is the same number: {fmt(big['d'], 3)}. The values on the children are their densities.",
            {"@kt": "t"}, tb=["merge", 5, None],
            eq=f"({' + '.join(fmt(r[3], 3) for r in kid_rows)}) / 4 = {fmt(mean_kids, 3)} = density of {big['t']}")
    rel = abs(diff) / big["c"]
    tr.step(f"For a cell completely inside the field, the overlap of the parent is "
            f"the sum of the overlaps of its children, and its density is their mean. The two contributions differ by {fmt(abs(diff), 4)} "
            f"({rel * 100:.3f} %) only because the four children are not exactly equal in area.",
            {}, tb=["merge", 5, None],
            eq=f"parent: {fmt(big['c'], 3)}    four children: {fmt(sum_kids, 3)}")
    st = {"@k": "", "@kt": "", f"cp:{b13['t']}": "clip", f"c:{b13['t']}": "edge"}
    tr.step(f"Cells at the field edge. The level-13 cell {b13['t']} is cut by the edge of the field: {share(b13) * 100:.0f} % of its area "
            f"({b13['ov']:.4f} of {b13['area']:.4f} km²) lies inside. Its density, {fmt(b13['d'], 3)}, is still the mean over its 16 sample "
            f"points, inside and outside the field.", st,
            eq=f"{b13['ov']:.5f} km² × {fmt(b13['d'], 3)} = {fmt(b13['c'], 3)}")
    st = {"@cp": "", f"c:{b13['t']}": "cell", f"c:{bm['t']}": "merged", f"cp:{bm['t']}": "clip", "@b": "cell", "@bt": "t"}
    tr.step(f"The level-12 cell {bm['t']} is also cut by the edge. All four level-13 children touch the field and are final, so the "
            f"covering uses the parent. Its density, {fmt(bm['d'], 3)}, is the mean of the children's densities (shown). "
            f"Here the cell is clipped unevenly: the four children with their own overlaps would sum to {fmt(bsum, 3)} instead of "
            f"{fmt(bm['c'], 3)}. At the edge the merge changes the number.", st, tb=["bmerge", 5, None],
            eq=f"parent: {fmt(bm['ov'], 5)} km² × {fmt(bm['d'], 3)} = {fmt(bm['c'], 3)}")
    st = {"@b": "", "@bt": "", "@c": "cell"}
    for c in f["cells"]:
        st[f"c:{c['t']}"] = STATE_OF[why[c["id"]]]
        if why[c["id"]] != "inside":
            st[f"cp:{c['t']}"] = "clip"
    tr.step(f"All {len(f['cells'])} contributions (overlap × density). The overlaps add up to "
            f"the area of the field, {f['area']:.5f} km².", st, tb=["cells", len(f["cells"]), None])
    finish_steps(tr, f, "a3",
                 f"Contributions are added per level-6 region (a cell of about 140 km edge length). "
                 f"{len(f['regions'])} region{'s are' if len(f['regions']) > 1 else ' is'} touched. A region sum below 1 would be raised to 1; none is.",
                 "The total is rounded once, half up.", "regions")
    tr.extra["summary"] = [
        ["Portals", "; ".join(coord_str(p) for p in pts)], ["Area", f"{f['area']:.6f} km²"],
        ["Covering", f"{len(f['cells'])} cells: {n12} at level 12, {n13} at level 13"],
        ["Completely inside", f"{nin} cell ({big['t']})"],
        ["Sum of contributions", fmt(f["total"], 6)], ["MU", fmt(f["mu"], 0)],
    ]
    tr.extra["cells"] = {"head": CELL_HEAD, "rows": field_rows(f), "fmt": CELL_FMT}
    tr.extra["check"] = check_block(f)
    tr.extra["check"]["merge"] = {"parent": big["t"], "children": kid_rows, "parent_row": merge_rows[4]}
    return tr.finish(focus={"fld"} | {f"c:{c['t']}" for c in f["cells"]})


build = build_a3
