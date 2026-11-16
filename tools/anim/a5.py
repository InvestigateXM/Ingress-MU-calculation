"""A smaller field with more MU: the real example near Las Vegas."""

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
    tr.extra["place"] = "Las Vegas / Lake Mead"
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
    tr.text("tA", proj.ll(A5_OUTER[0][0] / 1e6, A5_OUTER[0][1] / 1e6), "portal A")
    tr.text("tB", proj.ll(A5_OUTER[1][0] / 1e6, A5_OUTER[1][1] / 1e6), "portal B")
    tr.text("tF3", proj.ll(A5_OUTER[2][0] / 1e6, A5_OUTER[2][1] / 1e6), "third portal of F")
    tr.text("tG3", proj.ll(A5_INNER[2][0] / 1e6, A5_INNER[2][1] / 1e6), "third portal of G")
    tr.extra["vertices"] = {"tA": "fF", "tB": "fF", "tF3": "fF", "tG3": "fG"}
    tr.text("mF", [40.0, -4.0], f"F: {fF['mu']:,} MU", "m")
    tr.text("mG", [-30.0, 28.0], f"G: {fG['mu']:,} MU", "m")
    domF = max(fF["cells"], key=lambda c: c["c"])
    domG = max(fG["cells"], key=lambda c: c["c"])
    cell_label(tr, "decF", domF["id"], proj, f"F uses {domF['t']}")
    cell_label(tr, "decG", domG["id"], proj, f"G uses {domG['t']}")
    partsF = merge_parts(fF, domF["id"])
    assert [p[1] for p in partsF if p[0] == domG["id"]] == ["inside"], "the cell of G is not a final inside cell of F"
    dens = {}
    ds = [calc.mean_density(p[0]) for p in partsF]
    assert math.isclose(sum(ds) / 4, domF["d"], rel_tol=1e-12)
    for (cid, w, _), d in zip(partsF, ds):
        dens[cid] = d
        pts = poly(cid)
        cx, cy = sum(x for x, _ in pts) / 4, sum(y for _, y in pts) / 4
        dense = cid == domG["id"]
        tr.poly(f"zq:{tok(cid)}", pts, "zq")
        tr.text(f"zt:{tok(cid)}", [cx, cy - 9], "dense" if dense else "quiet", "zt")
        tr.text(f"zd:{tok(cid)}", [cx, cy + 9], fmt(d, 0), "zd")
    tr.table("totals", ["Field", "Area km²", "Cell used for most of the MU", "Density", "MU"],
             [["F (big)", fF["area"], domF["t"], domF["d"], fF["mu"]],
              ["G (small)", fG["area"], domG["t"], domG["d"], fG["mu"]]], ["s", 0, "s", 0, 0])

    def lv(f):
        d = {}
        for c in f["cells"]:
            d[c["lv"]] = d.get(c["lv"], 0) + 1
        return ", ".join(f"{v} at level {k}" for k, v in sorted(d.items()))

    tr.legend = {"p:field": "Field F (big)", "p:field2": "Field G (small)", "p:heat": "Cell, shaded by its contribution",
                 "p:hl": "Cell that gives most of the MU", "p:cell12": "The cell G uses (one quarter)"}
    heatF = {f"F:{c['t']}": "heat" for c in fF["cells"]}
    heatG = {f"G:{c['t']}": "heat" for c in fG["cells"]}
    tr.extra["comparison"] = {
        pre: dict(cover=heat, highlight=f'{pre}:{dom["t"]}', token=dom['t'],
                  level=dom['lv'], density=dom['d'], overlap=dom['ov'], contribution=dom['c'])
        for pre, heat, dom in [('F', heatF, domF), ('G', heatG, domG)]
    }
    tr.extra["comparison"]["from"] = 1
    quarters = {f"zq:{tok(c)}": "cell" for c, _, _ in partsF}
    ratio = fG["mu"] / fF["mu"]
    tr.step(f"G lies completely inside F, but G earns {fG['mu']:,} MU and F only {fF['mu']:,}: almost twice as much. Why?",
            {"fF": "field", "fG": "field2", "tA": "t", "tB": "t", "tF3": "t", "tG3": "t", "mF": "b", "mG": "b"})
    tr.step(f"Each field is covered with cells, and every cell has its own density (MU per km²). The orange cell is the one "
            f"that matters most. Press the buttons to see the cells of F and of G: F's is much bigger. "
            f"(The cells are shaded by how many MU they give.)",
            {"tA": "", "tB": "", "mF": "", "mG": ""})
    tr.step(f"This is the simple example again. F uses the big cell {domF['t']}, made of four quarters. One quarter, "
            f"{domG['t']}, holds Las Vegas. The other three are quiet desert and lake. G is small enough to use the Las Vegas quarter on its own.",
            dict(quarters, **{f"zq:{tok(domG['id'])}": "cell12", "@zt": "t"}))
    tr.step(f"The four quarters have very different densities. Las Vegas has {fmt(dens[domG['id']], 0)} MU per km², "
            f"the others only {', '.join(fmt(dens[p[0]], 0) for p in partsF if p[0] != domG['id'])}. "
            f"The big cell has the mean of the four: {fmt(domF['d'], 0)}.",
            {"@zt": "", "@zd": "t"},
            eq=f"({' + '.join(fmt(dens[p[0]], 1) for p in partsF)}) / 4 = {fmt(domF['d'], 1)}")
    tr.step(f"F is big, so it has to use the whole big cell. It counts {domF['ov']:,.0f} km² of it at {fmt(domF['d'], 0)}. "
            f"That one cell gives {domF['c']:,.0f} of the {fF['total']:,.0f} MU of F, because the city is averaged with the desert.",
            {}, eq=f"F: {domF['ov']:,.0f} km² × {fmt(domF['d'], 0)} = {domF['c']:,.0f}")
    tr.step(f"G is small enough to use the Las Vegas quarter alone. It counts {domG['ov']:,.0f} km² of it at {fmt(domG['d'], 0)}. "
            f"That is {domG['d'] / domF['d']:.1f} times the density that F uses for the same ground.",
            {}, eq=f"G: {domG['ov']:,.0f} km² × {fmt(domG['d'], 0)} = {domG['c']:,.0f}")
    tr.step(f"So G, which lies inside F, earns more: {fG['mu']:,} MU against {fF['mu']:,}. Bigger fields have to use "
            f"bigger cells, and a big cell averages a city with its empty surroundings. Press the buttons to compare the two coverings.",
            {"@zq": "", "@zd": "", "mF": "b", "mG": "b"}, tb=["totals", 2, None],
            eq=f"MU(G) = {fG['mu']:,}  >  MU(F) = {fF['mu']:,}")
    tr.extra["summary"] = [
        ["Outer field F", "; ".join(coord_str(p) for p in A5_OUTER)], ["Inner field G", "; ".join(coord_str(p) for p in A5_INNER)],
        ["Area F / G", f"{fF['area']:.3f} / {fG['area']:.3f} km²"], ["Cells F / G", f"{len(fF['cells'])} / {len(fG['cells'])}"],
        ["MU F / G", f"{fF['mu']:,} / {fG['mu']:,}"], ["G inside F", f"yes; third portal of G {margin[0]:.2f} km inside"],
    ]
    tr.extra["cells"] = {"head": CELL_HEAD, "rows": field_rows(fF), "fmt": CELL_FMT}
    tr.extra["cells2"] = {"head": CELL_HEAD, "rows": field_rows(fG), "fmt": CELL_FMT}
    tr.extra["check"] = {"outer": check_block(fF), "inner": check_block(fG), "margin_km": margin[0]}
    return tr.finish(focus={"fF", "fG"} | {e for e in tr.index if e[:3] in ("zq:",)})


build = build_a5
