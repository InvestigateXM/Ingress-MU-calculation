"""Animation 1."""

from .common import *  # noqa: F401,F403
from .common import _clip, _normals  # noqa: F401


# ---------------------------------------------------------------- animation 1

def _head(tip, frm, length, half):
    """Triangle (arrowhead) with its tip at `tip`, pointing away from `frm`."""
    dx, dy = tip[0] - frm[0], tip[1] - frm[1]
    d = math.hypot(dx, dy)
    ux, uy = dx / d, dy / d
    bx, by = tip[0] - ux * length, tip[1] - uy * length
    return [list(tip), [bx - uy * half, by + ux * half], [bx + uy * half, by - ux * half]]


def build_a1(calc):
    g = calc.g
    c13 = cid_of(A1_CELL)
    c12 = CellId(c13).parent(12).id()
    lat0, lng0 = [x.degrees for x in (CellId(c12).to_lat_lng().lat(), CellId(c12).to_lat_lng().lng())]
    proj = Proj(lat0, lng0)
    tr = Trace("a1", "A real cell on the population map", proj)

    def samples(cid):
        la, lo = l15_centres(cid)
        gi, gj = g.pix(la, lo)
        vals = g.sample(la, lo)
        return la, lo, gi.tolist(), gj.tolist(), vals

    la13, lo13, gi13, gj13, v13 = samples(c13)
    la12, lo12, gi12, gj12, v12 = samples(c12)
    d13, d12 = calc.mean_density(c13), calc.mean_density(c12)
    assert float(v13.mean()) == d13 and float(v12.mean()) == d12
    kids = [(ch.id(), calc.mean_density(ch.id())) for ch in CellId(c12).children()]
    assert math.isclose(sum(d for _, d in kids) / 4, d12, rel_tol=1e-12)
    assert any(k == c13 for k, _ in kids)

    # pixel value of every pixel read by the level-12 samples (checked to be consistent)
    px12 = {}
    for a, b, v in zip(gi12, gj12, v12.tolist()):
        assert px12.setdefault((a, b), v) == v
    px13 = {}
    for a, b, v in zip(gi13, gj13, v13.tolist()):
        px13[(a, b)] = v
    assert all(px12[k] == v for k, v in px13.items())

    # the pixels of the 4096 level-19 centres of the cell are the pixels the cell overlaps
    la_f, lo_f = l15_centres(c13, 19)
    overlapped = set(zip(np.floor((lo_f + 180) / D).astype(int).tolist(), np.floor((90 - la_f) / D).astype(int).tolist()))
    unread = sorted(overlapped - set(px13), key=lambda k: (k[1], k[0]))
    reads = sorted(px13, key=lambda k: (k[1], k[0]))
    letter = {k: "ABCDEF"[i] for i, k in enumerate(reads)}
    assert len(reads) == 6

    cols = [k[0] for k in px13]
    rows = [k[1] for k in px13]
    c_lo, c_hi, r_lo, r_hi = min(cols) - 1, max(cols) + 1, min(rows) - 1, max(rows) + 1

    def pix_poly(col, row):
        w, e = -180 + col * D, -180 + (col + 1) * D
        n, s = 90 - row * D, 90 - (row + 1) * D
        return [proj.ll(n, w), proj.ll(n, e), proj.ll(s, e), proj.ll(s, w)]

    for row in range(r_lo, r_hi + 1):
        for col in range(c_lo, c_hi + 1):
            tr.poly(f"px:{col}:{row}", pix_poly(col, row), "px")

    def poly_of(cid):
        return [proj.vec(v) for v in cell_vecs(cid)]

    tr.poly("c13", poly_of(c13))
    tips = {}
    nread = {k: sum(1 for a, b in zip(gi13, gj13) if (a, b) == k) for k in reads}
    for i in range(16):
        p = proj.ll(float(la13[i]), float(lo13[i]))
        sp = proj.ll(float(la13[i]) + D / 2, float(lo13[i]) - D / 2)
        key = (gi13[i], gj13[i])
        tr.dot(f"d13:{i}", p, "d13")
        tr.dot(f"sh:{i}", sp, "sh")
        tr.line(f"sl:{i}", p, sp, "sl")
        ctr = proj.ll(90 - (key[1] + 0.5) * D, -180 + (key[0] + 0.5) * D)
        tr.line(f"ln:{i}", sp, ctr, "ln")
        mv = math.hypot(sp[0] - p[0], sp[1] - p[1])
        tr.poly(f"ah:{i}", _head(sp, p, 0.16 * mv, 0.065 * mv), "ah")
        dd = math.hypot(p[0] - ctr[0], p[1] - ctr[1])
        tip = [p[0] - (p[0] - ctr[0]) / dd * 0.1 * mv, p[1] - (p[1] - ctr[1]) / dd * 0.1 * mv]
        tr.line(f"mb:{i}", ctr, p, "mb")
        tr.poly(f"ah2:{i}", _head(tip, ctr, 0.14 * mv, 0.06 * mv), "ah2")
        tr.text(f"vl:{i}", p, str(round(v13[i].item())), "vl")
        tips[f"d13:{i}"] = tips[f"sh:{i}"] = f"Point {i + 1}: reads pixel {letter[key]}, count {fmt(v13[i].item(), 0)}"
    tr.extra["tips"] = tips
    for k in reads:
        pp = pix_poly(*k)
        xs, ys = [q[0] for q in pp], [q[1] for q in pp]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        tr.text(f"lt:{k[0]}:{k[1]}", [x0 + 0.1 * (x1 - x0), y0 + 0.12 * (y1 - y0)], letter[k], "lt")
        tr.text(f"bd:{k[0]}:{k[1]}", [x1 - 0.2 * (x1 - x0), y0 + 0.12 * (y1 - y0)], f"×{nread[k]}", "bd")
        tr.text(f"ct:{k[0]}:{k[1]}", [(x0 + x1) / 2, y1 - 0.1 * (y1 - y0)], fmt(px13[k], 0), "ct")
    for k in unread:
        tr.text(f"un:{k[0]}:{k[1]}", [sum(q[0] for q in pix_poly(*k)) / 4, sum(q[1] for q in pix_poly(*k)) / 4], "not read", "un")

    # tables
    tr.table("samples", ["Point", "Pixel", "Count"],
             [[i + 1, letter[(gi13[i], gj13[i])], v13[i].item()] for i in range(16)], [0, "s", 0])
    n12 = {}
    for k in zip(gi12, gj12):
        n12[k] = n12.get(k, 0) + 1

    h_km = D * math.pi / 180 * RE
    w_km = h_km * math.cos(math.radians(lat0))
    a13 = cell_area_km2(c13)
    tr.legend = {"p:grid": "Pixel of the population map", "p:hl": "The cell", "p:read": "Pixel that is read",
                 "p:unread": "Pixel the cell overlaps but no point reads",
                 "d:dot": "Measuring point", "d:ghost": "Original position",
                 "d:shift": "Point moved half a pixel up and left",
                 "l:move": "Shift to where the game looks", "l:move2": "Count brought back to the point"}
    px_all = [f"px:{k[0]}:{k[1]}" for k in reads]
    tr.step(f"The population map is a grid of pixels, each about {w_km:.2f} km wide and {h_km:.2f} km tall. "
            f"The orange cell, {a13:.2f} km² in size, is tilted and does not line up with them, so it covers parts of several pixels.",
            {"@px": "grid", "c13": "hl"})
    tr.step("Inside the cell the game places the same 16 measuring points, evenly spaced. Hover or focus a point to see which pixel it reads.",
            {"@d13": "dot"})
    tr.step("Every point is moved half a pixel up and to the left (the arrows) before the map is read. "
            "The game does not read the pixel a point lies in. It looks half a pixel up and to the left and reads the pixel it finds there.",
            {"@d13": "ghost", "@sh": "shift", "@sl": "move", "@ah": "ah"})
    s = {"@d13": "", "@sl": "", "@ah": "", "@ln": "ptr", **{k: "read" for k in px_all}}
    s.update({f"px:{k[0]}:{k[1]}": "unread" for k in unread})
    s.update({f"lt:{k[0]}:{k[1]}": "b" for k in reads})
    s.update({f"bd:{k[0]}:{k[1]}": "b" for k in reads})
    s.update({f"un:{k[0]}:{k[1]}": "m" for k in unread})
    tr.step(f"Each shifted point reads the pixel it now lies in. Six pixels (A to F) are read, and the badges show how many points read each one. "
            f"The cell also overlaps {len(unread)} pixels that no point reads, which are ignored.", s)
    tr.step("Each pixel has a count of people. The table shows, for each of the 16 points, the pixel it reads and that pixel's count.",
            {"@ln": "", **{f"ct:{k[0]}:{k[1]}": "b" for k in reads}}, tb=["samples", 16, None])
    back = {"@sh": "", "@ln": "", "@lt": "", "@bd": "", "@un": "", "@d13": "dot", "@mb": "move2", "@ah2": "ah2",
            **{f"px:{k[0]}:{k[1]}": "read" for k in reads}, **{f"px:{k[0]}:{k[1]}": "grid" for k in unread}}
    tr.step("Now the counts go back. Each point takes the count of the pixel it read (purple arrows) and returns to its original place in the cell.",
            back, tb=["samples", 16, None])
    # zoomed view on the cell for the steps with 16 numbers (same map, only magnified)
    cp = poly_of(c13)
    zx0, zx1 = min(p[0] for p in cp), max(p[0] for p in cp)
    zy0, zy1 = min(p[1] for p in cp), max(p[1] for p in cp)
    zw, zh = (zx1 - zx0) * 1.3, (zy1 - zy0) * 1.3
    zw, zh = max(zw, zh * 4 / 3), max(zh, zw * 3 / 4)
    zcx, zcy = (zx0 + zx1) / 2, (zy0 + zy1) / 2
    zoom = [round(zcx - zw / 2, 3), round(zcy - zh / 2, 3), round(zw, 3), round(zh, 3)]
    tr.step("Zoomed in on the cell: each number now sits at the original place of its point, the number that point brought back. "
            "The shift was only where the game looked: the 16 numbers belong to the 16 points inside the cell.",
            {"@mb": "", "@ah2": "", "@ct": "", "@d13": "", "@vl": "b"}, tb=["samples", 16, None], view=zoom)
    groups = {}
    for k in reads:
        groups.setdefault(round(px13[k], 3), [0, px13[k]])[0] += nread[k]
    terms = " + ".join(f"{m}×{fmt(v, 0)}" for m, v in sorted(groups.values(), key=lambda t: -t[1]))
    tr.step(f"The density of the cell is the mean of these 16 numbers, in MU per km². "
            f"So every spot in this cell counts as about {fmt(d13, 0)} MU per km², whatever is actually inside it.",
            {}, tb=["samples", 16, None], eq=f"({terms}) / 16 = {fmt(d13, 0)} MU per km²", view=zoom)
    tr.extra["summary"] = [
        ["Cell", A1_CELL], ["Cell area", f"{a13:.4f} km²"], ["Measuring points", "16"], ["Pixels read", str(len(px13))],
        ["Density", fmt(d13, 6) + " MU per km²"],
    ]
    tr.extra["check"] = {
        "cell13": A1_CELL, "cell12": tok(c12), "density13": d13, "density12": d12,
        "samples13": [[gi13[i], gj13[i], v13[i].item()] for i in range(16)],
        "samples12": [[gi12[i], gj12[i], v12[i].item()] for i in range(64)],
        "children": [[tok(c), d] for c, d in kids],
    }
    tr.extra["attribution"] = ("Population counts: Global Rural-Urban Mapping Project, Version 1 (GRUMP v1): Population Count Grid, "
                               "CIESIN, IFPRI, The World Bank, CIAT, NASA SEDAC, doi:10.7927/H4VT1Q1H. "
                               f"Excerpt: the {len(px13)} pixel counts read by the 16 measuring points of the cell shown.")
    return tr.finish(view=[-2.669, -2.179, 4.826, 3.62])


build = build_a1
