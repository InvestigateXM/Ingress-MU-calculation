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
    nvals = sorted(nd.values())
    # the same triangle slid into the neighbour with the highest density
    best = max(nbs, key=lambda n: nd[n])
    assert nd[best] == nvals[-1] and nd[best] > 1500 and tok(best) in ("479e0b2c",)

    def centre(c_):
        ll = s2sphere.LatLng.from_point(CellId(c_).to_point())
        return ll.lat().degrees, ll.lng().degrees
    (la0, lo0), (la1, lo1) = centre(cid), centre(best)
    dl, dg = round((la1 - la0) * 1e6), round((lo1 - lo0) * 1e6)
    moved = [(p[0] + dl, p[1] + dg) for p in A2_FIELD]
    f2 = calc.field(moved)
    assert len(f2["cells"]) == 1 and f2["cells"][0]["id"] == best
    area2, mu2 = f2["area"], f2["cells"][0]["c"]
    assert round_half_up(f2["total"]) == 303
    tr.poly("fld2", [proj.ll(p[0] / 1e6, p[1] / 1e6) for p in moved])
    mid = lambda pts_: [sum(proj.ll(p[0] / 1e6, p[1] / 1e6)[k] for p in pts_) / 3 for k in (0, 1)]
    tr.line("mv", mid(A2_FIELD), mid(moved))
    tr.legend = {"d:dot": "Portal", "d:in": "Measuring point", "p:field": "Field (triangle)",
                 "p:field2": "The same field, moved", "p:hl": "Cell of the field",
                 "p:hl2": "Neighbouring cell with the highest density", "p:cell": "Neighbouring cell",
                 "p:clip": "Part of the field inside the cell"}
    tr.step(f"A field is the triangle between three portals. This small one covers {area:.2f} km², about {area * 100:.0f} hectares.",
            {"fld": "field", "vA": "dot", "vB": "dot", "vC": "dot", "tA": "t", "tB": "t", "tC": "t"})
    tr.step(f"The game describes this field with a single cell, the orange one. It is the smallest size of cell the game uses, "
            f"{cell['area']:.2f} km² in area, so a field this small is not split further.", {"c13": "hl"})
    s = {f"d:{i}": "in" for i in range(16)}
    tr.step("The game measures the population at 16 evenly spaced points in the cell. All 16 count, inside or outside the field.", s)
    tr.step(f"The density of the cell is the mean of its 16 measurements, {fmt(dens, 1)} MU per km². This is the same cell as in the "
            f"real example of the last animation, \"Where the density of a cell comes from\".", {},
            eq=f"density = mean of 16 points = {fmt(dens, 3)} MU per km²")
    tr.step(f"The density belongs to the cell, not to the spot where the field lies. The eight neighbouring cells have densities "
            f"from {fmt(nvals[0], 0)} to {fmt(nvals[-1], 0)} MU per km² (shown).", {"@nb": "cell", "@nt": "t"})
    tr.step(f"Slide the same field into the neighbour with the highest density, {fmt(nd[best], 1)} MU per km². "
            f"The field is unchanged, but it is now worth about {mu2:.0f} MU instead of {fmt(f['mu'], 0)}.",
            {"fld2": "field2", "mv": "move", f"nb:{tok(best)}": "hl2"},
            eq=f"{area2:.3f} km² × {fmt(nd[best], 1)} = {fmt(mu2, 1)} MU (instead of {fmt(area * dens, 1)})")
    tr.step(f"Back to the real field. The whole field lies in the cell, so MU before rounding = part of the field in the cell × density.",
            {"fld2": "", "mv": "", "@nb": "", "@nt": "", "clip": "clip"},
            eq=f"{area:.6f} km² × {fmt(dens, 3)} = {fmt(area * dens, 3)}")
    tr.step(f"The game rounds to whole Mind Units: {fmt(f['total'], 1)} becomes {fmt(f['mu'], 0)} MU.", {},
            eq=f"round half up({fmt(f['total'], 3)}) = {fmt(f['mu'], 0)} MU")
    tr.extra["summary"] = [
        ["Portals", "; ".join(coord_str(p) for p in A2_FIELD)], ["Area", f"{area:.6f} km²"],
        ["Covering", f"1 cell, level 13, {cell['t']}"], ["Measuring points inside the field", f"{k_in} of 16 (all 16 count)"],
        ["Density", fmt(dens, 6) + " MU per km²"], ["MU before rounding", fmt(area * dens, 6)],
        ["Same field moved into the neighbour " + tok(best), f"{fmt(mu2, 3)} MU before rounding, {round_half_up(f2['total'])} MU"],
        ["MU", fmt(f["mu"], 0)],
    ]
    tr.extra["cells"] = {"head": CELL_HEAD, "rows": field_rows(f), "fmt": CELL_FMT}
    tr.extra["check"] = check_block(f)
    return tr.finish(focus={"c13", "fld"} | {f"nb:{tok(n)}" for n in nbs})


build = build_a2
