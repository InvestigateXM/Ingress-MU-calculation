"""Animation 2."""

from .common import *  # noqa: F401,F403
from .common import _clip, _normals  # noqa: F401


# ---------------------------------------------------------------- animation 2

def build_a2(calc):
    f = calc.field(A2_FIELD)
    assert f["mu"] == EXPECTED_MU["a2"], f["mu"]
    assert len(f["cells"]) == 1 and f["cells"][0]["t"] == A1_CELL
    cell = f["cells"][0]
    cid = cell["id"]
    lat0 = sum(p[0] for p in A2_FIELD) / 3e6
    lng0 = sum(p[1] for p in A2_FIELD) / 3e6
    proj = Proj(lat0, lng0)
    tr = Trace("a2", "A field inside one level-13 cell", proj)
    poly = lambda c: [proj.vec(v) for v in cell_vecs(c)]
    nbs = [n.id() for n in CellId(cid).get_all_neighbors(13)]
    nd = {n: calc.mean_density(n) for n in nbs}
    for n in nbs:
        tr.poly(f"nb:{tok(n)}", poly(n), "nb")
        cell_label(tr, f"nt:{tok(n)}", n, proj, fmt(nd[n], 1), "nt")
    tr.poly("c13", poly(cid))
    cell_label(tr, "ct", cid, proj, "", None)
    tr.els.pop(); tr.index.pop("ct")
    fpoly = [proj.ll(p[0] / 1e6, p[1] / 1e6) for p in A2_FIELD]
    tr.poly("fld", fpoly)
    clip = clip_vecs(A2_FIELD, cid)
    assert math.isclose(sph_area(clip) * RE ** 2, f["area"], rel_tol=1e-6)
    tr.poly("clip", [proj.vec(v) for v in clip])
    portal_labels(tr, proj, A2_FIELD)
    la, lo = l15_centres(cid)
    normals = _normals([unit(*p) for p in A2_FIELD])
    inside = []
    for i in range(16):
        p = ll_unit(float(la[i]), float(lo[i]))
        inside.append(all(float(np.dot(n, p)) >= 0 for n in normals))
        tr.dot(f"d:{i}", proj.ll(float(la[i]), float(lo[i])), "d")
    k_in = sum(inside)
    in_ids = [f"d:{i}" for i in range(16) if inside[i]]
    out_ids = [f"d:{i}" for i in range(16) if not inside[i]]
    dens = cell["d"]
    area = f["area"]
    reg = cell["reg"]
    nvals = sorted(nd.values())
    tr.legend = {"p:field": "Field (triangle)", "p:hl": "Level-13 cell of the field", "p:cell": "Neighbouring level-13 cell", "d:in": "Sample point inside the field",
                 "d:out": "Sample point outside the field", "p:clip": "Overlap of field and cell"}
    tr.step(f"An example field with three portals ({'; '.join(coord_str(p) for p in A2_FIELD)}). Its area is {area:.4f} km², "
            f"about {area * 100:.0f} hectares.", {"fld": "field", "vA": "dot", "vB": "dot", "vC": "dot", "tA": "t", "tB": "t", "tC": "t"})
    tr.step(f"The covering of the field is a single cell: level 13, token {cell['t']}, area {cell['area']:.3f} km². "
            f"Level 13 is the finest level that is used, so a field this small is not split further.", {"c13": "hl"})
    s = {i: "in" for i in in_ids}
    s.update({i: "out" for i in out_ids})
    s["c13"] = "hl"
    tr.step(f"The cell has 16 sample points (the level-15 cell centres). {k_in} of them lie inside the field, {16 - k_in} outside. "
            f"All 16 enter the density.", s)
    tr.step(f"The density of the cell is the mean over all 16 sample points, {fmt(dens, 3)}. It is the same cell as in the first "
            f"animation. The part of the cell under the field does not change it.", {}, eq=f"density = mean of 16 samples = {fmt(dens, 3)}")
    tr.step(f"The density belongs to the cell, not to the spot where the field lies. The eight neighbouring level-13 cells have "
            f"densities from {fmt(nvals[0], 1)} to {fmt(nvals[-1], 1)}; a field of the same size in one of them would get "
            f"that cell's density.", {"@nb": "cell", "@nt": "t"})
    tr.step(f"The overlap of the field and the cell is the whole field: {area:.6f} km².", {"clip": "clip", "@nb": "", "@nt": ""},
            eq=f"overlap = {area:.6f} km²")
    tr.step("Contribution of the cell = overlap × density.", {}, eq=f"{area:.6f} km² × {fmt(dens, 3)} = {fmt(area * dens, 3)}")
    finish_steps(tr, f, "a2",
                 f"The cell lies in one level-6 region, {reg}. The sum of the region is {fmt(f['total'], 3)}. The minimum of 1 per region "
                 f"only applies when a region sum is below 1; here it is not.",
                 f"The total is rounded once, half up, to the Mind Units of the field.", "regions")
    tr.extra["summary"] = [
        ["Portals", "; ".join(coord_str(p) for p in A2_FIELD)], ["Area", f"{area:.6f} km²"],
        ["Covering", f"1 cell, level 13, {cell['t']}"], ["Sample points inside the field", f"{k_in} of 16"],
        ["Density", fmt(dens, 6)], ["Contribution", fmt(area * dens, 6)], ["MU", fmt(f["mu"], 0)],
    ]
    tr.extra["cells"] = {"head": CELL_HEAD, "rows": field_rows(f), "fmt": CELL_FMT}
    tr.extra["check"] = check_block(f)
    return tr.finish(focus={"c13", "fld"} | {f"nb:{tok(n)}" for n in nbs})


build = build_a2
