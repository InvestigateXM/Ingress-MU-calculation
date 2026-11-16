"""Animation 5."""

from .common import *  # noqa: F401,F403
from .common import _clip, _normals  # noqa: F401


# ---------------------------------------------------------------- animation 5

def merge_parts(f, final_id):
    """The final cells that normalisation replaced by final_id, with how each one arose."""
    before = [k for e, k in f["events"] if e == "normalize"][0]["before"]
    why = {k["cid"]: k["why"] for e, k in f["events"] if e == "result"}
    polls = {}
    for n, (e, k) in enumerate((e, k) for e, k in f["events"] if e == "poll"):
        pass
    plist = [k for e, k in f["events"] if e == "poll"]
    for n, k in enumerate(plist, 1):
        polls[k["cid"]] = (n, k)
    parts = [b for b in before if b != final_id and CellId(final_id).contains(CellId(b))]
    assert len(parts) == 4 and final_id not in before
    return [(b, why[b], polls.get(b)) for b in parts]


def build_a5(calc):
    fF, fG = calc.field(A5_OUTER), calc.field(A5_INNER)
    assert fF["mu"] == EXPECTED_MU["a5_outer"], fF["mu"]
    assert fG["mu"] == EXPECTED_MU["a5_inner"], fG["mu"]
    assert fG["mu"] > fF["mu"] and fG["area"] < fF["area"]
    # G inside F: every vertex of G on the inner side of every edge of F
    normals = _normals([unit(*p) for p in A5_OUTER])
    margin = []
    for p in A5_INNER:
        v = ll_unit(p[0] / 1e6, p[1] / 1e6)
        d = [RE * math.asin(float(np.dot(n, v)) / float(np.linalg.norm(n))) for n in normals]
        assert min(d) > -1e-6, (p, d)
        if p not in A5_OUTER:
            margin.append(min(d))
    shared = [p for p in A5_INNER if p in A5_OUTER]
    assert len(shared) == 2 and len(margin) == 1
    pts = A5_OUTER
    proj = Proj(sum(p[0] for p in pts) / 3e6, sum(p[1] for p in pts) / 3e6)
    tr = Trace("a5", "A smaller field with more MU", proj)
    poly = lambda c: [proj.vec(v) for v in cell_vecs(c)]
    contrib = [c["c"] for c in fF["cells"] + fG["cells"]]
    b, _ = bins([max(x, 1.0) for x in contrib])
    tr.extra["bins"] = {}
    i = 0
    for pre, f in (("F", fF), ("G", fG)):
        for c in f["cells"]:
            eid = f"{pre}:{c['t']}"
            tr.poly(eid, poly(c["id"]), pre)
            tr.extra["bins"][eid] = b[i]
            i += 1
    tr.extra["ramp"] = {"label": "Contribution of the cell (MU)", "min": max(1.0, min(contrib)), "max": max(contrib), "log": True}
    tr.poly("fF", [proj.ll(p[0] / 1e6, p[1] / 1e6) for p in A5_OUTER])
    tr.poly("fG", [proj.ll(p[0] / 1e6, p[1] / 1e6) for p in A5_INNER])
    tr.text("tA", proj.ll(A5_OUTER[0][0] / 1e6, A5_OUTER[0][1] / 1e6), "A")
    tr.text("tB", proj.ll(A5_OUTER[1][0] / 1e6, A5_OUTER[1][1] / 1e6), "B")
    tr.text("tF3", proj.ll(A5_OUTER[2][0] / 1e6, A5_OUTER[2][1] / 1e6), "F3")
    tr.text("tG3", proj.ll(A5_INNER[2][0] / 1e6, A5_INNER[2][1] / 1e6), "G3")
    domF = max(fF["cells"], key=lambda c: c["c"])
    domG = max(fG["cells"], key=lambda c: c["c"])
    cell_label(tr, 'decF', domF['id'], proj, 'F: ' + domF['t'])
    cell_label(tr, 'decG', domG['id'], proj, 'G: ' + domG['t'])
    partsF, partsG = merge_parts(fF, domF["id"]), merge_parts(fG, domG["id"])
    assert [p[1] for p in partsF if p[0] == domG["id"]] == ["inside"], "the cell of G is not a final inside cell of F"
    dens = {}
    for pre, parts, dom in (("F", partsF, domF), ("G", partsG, domG)):
        ds = [calc.mean_density(p[0]) for p in parts]
        assert math.isclose(sum(ds) / 4, dom["d"], rel_tol=1e-12)
        for (cid, w, _), d in zip(parts, ds):
            dens[(pre, cid)] = d
            tr.poly(f"p{pre}:{tok(cid)}", poly(cid), f"p{pre}")
            cell_label(tr, f"q{pre}:{tok(cid)}", cid, proj, fmt(d, 1), f"q{pre}")
    tr.table("cmp", ["Field", "Cell", "Level", "Cell km²", "Overlap km²", "Density", "Contribution"],
             [["F (outer)", domF["t"], domF["lv"], domF["area"], domF["ov"], domF["d"], domF["c"]],
              ["G (inner)", domG["t"], domG["lv"], domG["area"], domG["ov"], domG["d"], domG["c"]]],
             ["s", "s", 0, 2, 2, 3, 0])
    for pre, f in (("F", fF), ("G", fG)):
        tr.table(f"cells{pre}", CELL_HEAD, field_rows(f), CELL_FMT)
    for pre, parts in (("F", partsF), ("G", partsG)):
        rows = []
        for cid, w, pl in parts:
            how = "completely inside" if w == "inside" else (f"kept at poll {pl[0]}: {pl[1]['result']} + {pl[1]['queue']} + {len(pl[1]['children'])} = "
                                                          f"{pl[1]['result'] + pl[1]['queue'] + len(pl[1]['children'])} > 20")
            rows.append([tok(cid), CellId(cid).level(), dens[(pre, cid)], how])
        tr.table(f"parts{pre}", ["Cell", "Level", "Density", "Why it is final"], rows, ["s", 0, 3, "s"])
    tr.table("totals", ["Field", "Area km²", "Cells", "Sum of contributions", "MU"],
             [["F (outer)", fF["area"], len(fF["cells"]), fF["total"], fF["mu"]],
              ["G (inner)", fG["area"], len(fG["cells"]), fG["total"], fG["mu"]]], ["s", 1, 0, 3, 0])

    def lv(f):
        d = {}
        for c in f["cells"]:
            d[c["lv"]] = d.get(c["lv"], 0) + 1
        return ", ".join(f"{v} at level {k}" for k, v in sorted(d.items()))

    def n_budget(parts):
        return sum(1 for p in parts if p[1] == "budget")

    tr.legend = {"p:field": "Field F (outer)", "p:field2": "Field G (inner)", "p:heat": "Cell, shaded by its contribution",
                 "p:hl": "Cell that dominates the MU of the field", "p:in": "Final cell completely inside the field",
                 "p:kept": "Final cell kept whole because of the budget"}
    heatF = {f"F:{c['t']}": "heat" for c in fF["cells"]}
    heatG = {f"G:{c['t']}": "heat" for c in fG["cells"]}
    tr.extra['comparison'] = {
        pre: dict(cover=heat, highlight=f'{pre}:{dom["t"]}', token=dom['t'],
                  level=dom['lv'], density=dom['d'], overlap=dom['ov'], contribution=dom['c'])
        for pre, heat, dom in [('F', heatF, domF), ('G', heatG, domG)]
    }
    pl = partsF
    tr.step(f"Two example fields. F is the larger one, {fF['area']:,.0f} km². G, {fG['area']:,.0f} km², shares the portals A and B with F "
            f"and lies completely inside F: its third portal G3 is {margin[0]:.1f} km inside the edge of F. "
            f"Both are well below 100,000 km².",
            {"fF": "field", "fG": "field2", "tA": "t", "tB": "t", "tF3": "t", "tG3": "t"},
            eq=f"area F = {fmt(fF['area'], 1)} km²   area G = {fmt(fG['area'], 1)} km²")
    tr.step(f"Covering of F: {len(fF['cells'])} cells ({lv(fF)}). The cell {domF['t']} (level {domF['lv']}, {domF['area']:,.0f} km²) has "
            f"{share(domF) * 100:.0f} % of its area inside F and density {fmt(domF['d'], 1)}. It contributes {domF['c']:,.0f} of the "
            f"{fF['total']:,.0f} ({domF['c'] / fF['total'] * 100:.1f} %).",
            dict(heatF, **{"tG3": "", f"F:{domF['t']}": "hl"}), tb=["cellsF", len(fF["cells"]), None])
    tr.step(f"The cell {domF['t']} is made of four level-{domF['lv'] + 1} cells that were all final: {n_budget(partsF)} were kept whole because "
            f"the budget of 20 was used up, one ({tok(domG['id'])}) lies completely inside F. Four final siblings are merged into "
            f"their parent. The densities of the four are shown.",
            dict({"@F": "", "@qF": "t"}, **{f"pF:{tok(c)}": STATE_OF[w] for c, w, _ in partsF}), tb=["partsF", 4, None])
    tr.step(f"The merged cell has the mean of the four densities, {fmt(domF['d'], 1)}. Only one of the four, {tok(domG['id'])}, "
            f"has a high density; its density is {dens[('F', domG['id'])] / domF['d']:.1f} times the density of the merged cell. "
            f"F counts its {domF['ov']:,.0f} km² in {domF['t']} at {fmt(domF['d'], 1)}.",
            {}, eq=f"({' + '.join(fmt(dens[('F', p[0])], 1) for p in partsF)}) / 4 = {fmt(domF['d'], 1)}")
    tr.step(f"Covering of G: {len(fG['cells'])} cells ({lv(fG)}). The budget is spent on a smaller area, so the cells are finer. "
            f"The cell {domG['t']} (level {domG['lv']}, {domG['area']:,.0f} km²) is one of the four children of {domF['t']}. "
            f"{share(domG) * 100:.0f} % of it lies inside G. It contributes {domG['c']:,.0f} of the {fG['total']:,.0f} "
            f"({domG['c'] / fG['total'] * 100:.0f} %).",
            dict(heatG, **{"@pF": "", "@qF": "", "fF": "", f"G:{domG['t']}": "hl", "tF3": "", "tG3": "t"}),
            tb=["cellsG", len(fG["cells"]), None])
    tr.step(f"{domG['t']} is again made of four final cells, of level {domG['lv'] + 1}: {n_budget(partsG)} kept whole by the budget and "
            f"{4 - n_budget(partsG)} inside G. Their mean is its density, {fmt(domG['d'], 1)}: the same value as in F, because it is the "
            f"same cell. The level-{domG['lv']} cell averages an area roughly a quarter as large as the level-{domF['lv']} cell in F.",
            dict({"@G": "", "@qG": "t"}, **{f"pG:{tok(c)}": STATE_OF[w] for c, w, _ in partsG}), tb=["partsG", 4, None],
            eq=f"({' + '.join(fmt(dens[('G', p[0])], 1) for p in partsG)}) / 4 = {fmt(domG['d'], 1)}")
    tr.step(f"Same ground, different cell. F counts {domF['ov']:,.0f} km² of its area at the density of the level-{domF['lv']} cell, "
            f"{fmt(domF['d'], 1)}. G counts {domG['ov']:,.0f} km² at the density of the level-{domG['lv']} cell, {fmt(domG['d'], 1)}. "
            f"G is part of F, but the density that applies to this ground is {domG['d'] / domF['d']:.1f} times as large. "
            f"F averages the populated cell {domG['t']} with three sparsely populated siblings; G keeps it separately.",
            {"@pG": "", "@qG": "", "fF": "field", "tF3": "t"}, tb=["cmp", 2, None],
            eq=f"F: {domF['ov']:,.0f} km² × {fmt(domF['d'], 1)} = {domF['c']:,.0f}     G: {domG['ov']:,.0f} km² × {fmt(domG['d'], 1)} = {domG['c']:,.0f}")
    tr.step(f"Result: G earns {fG['mu']:,} MU and F earns {fF['mu']:,} MU. The same ground is multiplied by a different density: "
            f"F's covering averages the populated cell {domG['t']} with three sparsely populated siblings in {domF['t']}, "
            f"while G keeps {domG['t']} separately. Switch between the coverings to compare the highlighted cells. "
            f"The covering depends on the field's size, shape and position.", {}, tb=["totals", 2, None],
            eq=f"MU(G) = {fG['mu']:,}  >  MU(F) = {fF['mu']:,}")
    tr.extra["summary"] = [
        ["Outer field F", "; ".join(coord_str(p) for p in A5_OUTER)], ["Inner field G", "; ".join(coord_str(p) for p in A5_INNER)],
        ["Area F / G", f"{fF['area']:.3f} / {fG['area']:.3f} km²"], ["Cells F / G", f"{len(fF['cells'])} / {len(fG['cells'])}"],
        ["MU F / G", f"{fF['mu']:,} / {fG['mu']:,}"], ["G inside F", f"yes; portal G3 {margin[0]:.2f} km inside"],
    ]
    tr.extra["cells"] = {"head": CELL_HEAD, "rows": field_rows(fF), "fmt": CELL_FMT}
    tr.extra["cells2"] = {"head": CELL_HEAD, "rows": field_rows(fG), "fmt": CELL_FMT}
    tr.extra["check"] = {"outer": check_block(fF), "inner": check_block(fG), "margin_km": margin[0]}
    return tr.finish(focus={"fF", "fG"} | {e for e in tr.index if e[:3] in ("pF:", "pG:")})


build = build_a5
