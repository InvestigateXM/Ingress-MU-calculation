"""Animation 1."""

from .common import *  # noqa: F401,F403
from .common import _clip, _normals  # noqa: F401


# ---------------------------------------------------------------- animation 1

def build_a1(calc):
    g = calc.g
    c13 = cid_of(A1_CELL)
    c12 = CellId(c13).parent(12).id()
    lat0, lng0 = [x.degrees for x in (CellId(c12).to_lat_lng().lat(), CellId(c12).to_lat_lng().lng())]
    proj = Proj(lat0, lng0)
    tr = Trace("a1", "Pixel grid and cell density", proj)

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

    cols = [k[0] for k in px12]
    rows = [k[1] for k in px12]
    c_lo, c_hi, r_lo, r_hi = min(cols) - 1, max(cols) + 1, min(rows) - 1, max(rows) + 1

    def pix_poly(col, row):
        w, e = -180 + col * D, -180 + (col + 1) * D
        n, s = 90 - row * D, 90 - (row + 1) * D
        return [proj.ll(n, w), proj.ll(n, e), proj.ll(s, e), proj.ll(s, w)]

    for row in range(r_lo, r_hi + 1):
        for col in range(c_lo, c_hi + 1):
            tr.poly(f"px:{col}:{row}", pix_poly(col, row), "px")
    for (col, row) in sorted(px12, key=lambda k: (k[1], k[0])):
        n, w = 90 - (row + 0.5) * D, -180 + (col + 0.5) * D
        tr.text(f"pv:{col}:{row}", proj.ll(n, w), f"{px12[(col, row)]:.0f}", "pv")

    def poly_of(cid):
        return [proj.vec(v) for v in cell_vecs(cid)]

    tr.poly("c12", poly_of(c12))
    for cid, dens in kids:
        tr.poly(f"k:{tok(cid)}", poly_of(cid))
        cell_label(tr, f"kt:{tok(cid)}", cid, proj, fmt(dens, 1), "kt")
    tr.poly("c13", poly_of(c13))
    for i in range(16):
        sub = CellId.from_lat_lng(s2sphere.LatLng.from_degrees(float(la13[i]), float(lo13[i]))).parent(15).id()
        tr.poly(f"s15:{i}", poly_of(sub), "s15")
    shifted = []
    plain_diff = []
    for i in range(16):
        p = proj.ll(float(la13[i]), float(lo13[i]))
        tr.dot(f"d13:{i}", p, "d13")
        tr.text(f"n13:{i}", [p[0] + 0.035, p[1] - 0.035], str(i + 1), "n13")
        sp = proj.ll(float(la13[i]) + D / 2, float(lo13[i]) - D / 2)
        shifted.append(sp)
        tr.dot(f"sh:{i}", sp, "sh")
        tr.line(f"sl:{i}", p, sp, "sl")
        key = (gi13[i], gj13[i])
        tr.line(f"ln:{i}", p, proj.ll(90 - (key[1] + 0.5) * D, -180 + (key[0] + 0.5) * D), "ln")
        pc, pr = math.floor((float(lo13[i]) + 180) / D), math.floor((90 - float(la13[i])) / D)
        if (pc, pr) != key:
            plain_diff.append(i)
    for i in range(64):
        tr.dot(f"d12:{i}", proj.ll(float(la12[i]), float(lo12[i])), "d12")
    demo = plain_diff[0]
    pc, pr = math.floor((float(lo13[demo]) + 180) / D), math.floor((90 - float(la13[demo])) / D)

    # tables
    tr.table("samples", ["Sample", "Pixel column", "Pixel row", "Count"],
             [[i + 1, gi13[i], gj13[i], v13[i].item()] for i in range(16)], [0, 0, 0, 4])
    n12 = {}
    for k in zip(gi12, gj12):
        n12[k] = n12.get(k, 0) + 1
    prow = [[k[0], k[1], n12[k], v, n12[k] * v] for k, v in sorted(px12.items(), key=lambda kv: (kv[0][1], kv[0][0]))]
    tr.table("pixels", ["Column", "Row", "Samples (of 64)", "Count", "Samples × count"], prow, [0, 0, 0, 4, 3])
    tr.table("children", ["Level-13 cell", "Density"],
             [[tok(c), d] for c, d in kids] + [[tok(c12) + " (parent)", d12]], ["s", 3])
    levels = []
    for lv in range(13, 5, -1):
        levels.append([lv, 4 ** (15 - lv), 6 * 4 ** lv, 4 * math.pi * RE ** 2 / (6 * 4 ** lv)])
    tr.table("levels", ["Cell level", "Samples per cell", "Cells on the sphere", "Average cell area km²"],
             levels, [0, 0, 0, 2])

    tr.legend = {"p:grid": "Pixel of the 30 arc-second grid", "p:read": "Pixel that is read", "p:plain": "Pixel that contains the point itself",
                 "p:hl": "Level-13 cell", "p:cell": "Cell of level 13", "p:cell12": "Level-12 parent cell",
                 "d:dot": "Sample point (centre of a level-15 cell)", "d:shift": "Sample point moved half a pixel north and west"}
    h_km = D * math.pi / 180 * RE
    w_km = h_km * math.cos(math.radians(lat0))
    a13, a12 = cell_area_km2(c13), cell_area_km2(c12)
    s, S = {}, {}
    tr.step(f"GRUMP v1 stores population counts on a grid of 30 arc-second pixels, 1/120 degree on a side. At 48.2° N a pixel is "
            f"{h_km:.2f} km tall and {w_km:.2f} km wide. Only the grid lines are shown; the count of a pixel is shown later "
            f"for the pixels that are read.", {"@px": "grid"})
    tr.step(f"The smallest covering cell is an S2 cell of level 13. This one, {A1_CELL}, has an area of {a13:.2f} km². "
            f"Its edges are great-circle arcs and do not follow the pixel grid.", {"c13": "hl"})
    tr.step("A level-13 cell contains 16 level-15 cells, 4 × 4.", {"@s15": "sub"})
    tr.step("The centres of the 16 level-15 cells are the sample points. The density of the cell is the mean of the "
            "population counts at these 16 points. Focus or hover over a point for its sample number and count.", {"@d13": "dot"}, tb=["samples", 16, None])
    tr.step(f"To find the pixel of a sample point, the point is moved half a pixel to the north and to the west (open circle for sample {demo + 1}). "
            f"The pixel that contains the moved point is the one that is read. Sample {demo + 1} lies in pixel "
            f"({pc}, {pr}), but its moved point lies in pixel ({gi13[demo]}, {gj13[demo]}), which is read. "
            f"{len(plain_diff)} of the 16 samples read a different pixel than the one containing them.",
            {"@d13": "", f"d13:{demo}": "dot", f"sh:{demo}": "shift", f"sl:{demo}": "link", f"px:{pc}:{pr}": "plain", f"px:{gi13[demo]}:{gj13[demo]}": "read"})
    s = {f"px:{k[0]}:{k[1]}": "read" for k in px13}
    s = {"@px": "grid", **s, "@d13": "dot", "@sh": "", "@sl": ""}
    tr.step(f"The 16 samples read {len(px13)} different pixels. Several samples can read the same pixel.", s)
    s = {"@d13": "", **{f"pv:{k[0]}:{k[1]}": "t" for k in px13}}
    tr.step("Excerpt of the population data: the count of each pixel that is read (rounded in the drawing, exact values "
            "in the table). The counts differ strongly between these pixels.",
            s, tb=["samples", 16, None])
    tr.step(f"The density of cell {A1_CELL} is the mean of the 16 counts.", {}, tb=["samples", 16, None],
            eq=f"({' + '.join(fmt(x, 3) for x in v13.tolist())}) / 16 = {fmt(d13, 3)}")
    s = {"@s15": "", "@d13": "", "@n13": "", "@sh": "", "@sl": "", "@ln": "", "@px": "grid", "@pv": "",
         "c13": "", "c12": "cell12", "@d12": "dot"}
    for k in px12:
        s[f"px:{k[0]}:{k[1]}"] = "read"
    for cid, _ in kids:
        s[f"k:{tok(cid)}"] = "cell" if cid != c13 else "hl"
    s.update({"@pv": ""})
    tr.step(f"The parent, cell {tok(c12)} at level 12 ({a12:.2f} km²), consists of four level-13 cells and contains 64 level-15 cells. "
            f"The same procedure with 64 sample points reads {len(px12)} pixels.", s)
    s = {"@d12": "", **{f"pv:{k[0]}:{k[1]}": "t" for k in px12}}
    tr.step(f"Counts of the {len(px12)} pixels that are read by the 64 samples. Each sample counts once, so a pixel read by "
            f"several samples counts several times.", s, tb=["pixels", len(prow), None],
            eq=f"({' + '.join(f'{n12[k]}×{px12[k]:.3f}' for k in sorted(px12, key=lambda k: (k[1], k[0])))}) / 64 = {fmt(d12, 3)}")
    s = {"@pv": "", "@d12": "", "@kt": "t"}
    tr.step("Each of the four children averages 16 of the 64 samples. The mean of the four child densities is therefore "
            f"the density of the parent mathematically (floating-point summation can differ in the last bits): {fmt(d12, 3)}. The level-12 cell has a different density than the level-13 cell "
            f"{A1_CELL} ({fmt(d13, 3)}).", s, tb=["children", 5, None],
            eq=f"({' + '.join(fmt(d, 3) for _, d in kids)}) / 4 = {fmt(d12, 3)}")
    tr.step("The same holds at every level: a cell of level L averages the 4^(15−L) level-15 centres inside it. "
            "Coarser cells therefore average over a larger area, whatever part of it a field covers.", {}, tb=["levels", len(levels), None])
    tr.extra["summary"] = [
        ["Cell (level 13)", A1_CELL], ["Cell area", f"{a13:.4f} km²"], ["Samples", "16"], ["Pixels read", str(len(px13))],
        ["Density, level 13", fmt(d13, 6)], ["Parent (level 12)", tok(c12)], ["Parent area", f"{a12:.4f} km²"],
        ["Samples", "64"], ["Pixels read", str(len(px12))], ["Density, level 12", fmt(d12, 6)],
    ]
    tr.extra["check"] = {
        "cell13": A1_CELL, "cell12": tok(c12), "density13": d13, "density12": d12,
        "samples13": [[gi13[i], gj13[i], v13[i].item()] for i in range(16)],
        "samples12": [[gi12[i], gj12[i], v12[i].item()] for i in range(64)],
        "children": [[tok(c), d] for c, d in kids],
    }
    tr.extra["attribution"] = ("Population counts: Global Rural-Urban Mapping Project, Version 1 (GRUMP v1): Population Count Grid, "
                               "CIESIN, IFPRI, The World Bank, CIAT, NASA SEDAC, doi:10.7927/H4VT1Q1H. "
                               f"Excerpt: the {len(px12)} pixel values read by the samples of these two cells.")
    return tr.finish(focus={"c12"} | {f"px:{k[0]}:{k[1]}" for k in px12})


build = build_a1
