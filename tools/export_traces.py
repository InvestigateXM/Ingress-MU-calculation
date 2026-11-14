"""Export the data files for site/how-it-works.html.

Every number shown by the animation page is computed here by the shipped
calculator (mu_calculator) for a fixed set of example fields and written to
site/traces/a1.json .. a5.json. The page itself only draws these files.

Usage (Linux; needs the population rasters, see README):

    GRUMP_DIR=/path/to/grump/bil python tools/export_traces.py [--out site/traces] [--check]

--check recomputes everything and compares it with the files in --out instead
of writing them. The export fails if an example no longer gives its expected MU.
The output is deterministic.
"""

import argparse
import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import s2sphere

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mu_calculator import tables  # noqa: E402
from mu_calculator.calculator import MODEL, mu_field  # noqa: E402
from mu_calculator.covering import cover  # noqa: E402
from mu_calculator.geometry import (  # noqa: E402
    D, RE, Grump, _clip, _normals, density, l15_centres, overlaps, sph_area, unit,
)

SCHEMA = 1
CellId = s2sphere.CellId

# Fixed examples. Coordinates are example values (E6 integers), not portals.
A1_CELL = "479e0b3c"           # level 13; its level-12 parent is 479e0b3
A2_FIELD = [(48181077, 11695339), (48176421, 11692789), (48179679, 11687153)]
A3_FIELD = [(48187299, 11734966), (48146757, 11674038), (48193616, 11650608)]
A4_FIELD = [(47954427, 11181220), (47914334, 11972899), (48434506, 11556379)]
A5_OUTER = [(36434464, -115350509), (35563567, -115358276), (36178156, -113532566)]
A5_INNER = [(36434464, -115350509), (35563567, -115358276), (36181777, -114759193)]
EXPECTED_MU = {"a2": 161, "a3": 16406, "a4": 952401, "a5_outer": 425012, "a5_inner": 846372}


# ---------------------------------------------------------------- geometry helpers

def ll_unit(lat, lng):
    la, ln = math.radians(lat), math.radians(lng)
    return np.array([math.cos(la) * math.cos(ln), math.cos(la) * math.sin(ln), math.sin(la)])


class Proj:
    """Gnomonic projection centred on (lat, lng); great circles become straight lines.

    Returns kilometres on the tangent plane, x to the east, y downwards (SVG).
    """

    def __init__(self, lat, lng):
        la, ln = math.radians(lat), math.radians(lng)
        self.c = ll_unit(lat, lng)
        self.e = np.array([-math.sin(ln), math.cos(ln), 0.0])
        self.n = np.array([-math.sin(la) * math.cos(ln), -math.sin(la) * math.sin(ln), math.cos(la)])
        self.lat, self.lng = lat, lng

    def vec(self, p):
        d = float(np.dot(p, self.c))
        return [round(RE * float(np.dot(p, self.e)) / d, 4), round(-RE * float(np.dot(p, self.n)) / d, 4)]

    def ll(self, lat, lng):
        return self.vec(ll_unit(lat, lng))


def cell_vecs(cid):
    cell = s2sphere.Cell(CellId(cid))
    return [np.array(list(cell.get_vertex(k))) for k in range(4)]


def cell_area_km2(cid):
    return s2sphere.Cell(CellId(cid)).exact_area() * RE ** 2


def tok(cid):
    return CellId(cid).to_token()


def cid_of(token):
    return CellId.from_token(token).id()


def clip_vecs(pts_e6, cid):
    """The polygon field ∩ cell (same operations as geometry.overlaps)."""
    poly = cell_vecs(cid)
    normals = _normals([unit(*p) for p in pts_e6])
    for n in normals:
        poly = _clip(poly, n)
        if not poly:
            break
    return poly


def deg(p):
    return [round(p[0] / 1e6, 6), round(p[1] / 1e6, 6)]


def fmt(x, d=3):
    return f"{x:,.{d}f}"


def nice(x):
    """Largest 1, 2 or 5 times a power of ten not above x."""
    e = 10 ** math.floor(math.log10(x))
    return max(m * e for m in (1, 2, 5) if m * e <= x)


def region_token(cid):
    return tok(CellId(cid).parent(6).id())


def round_half_up(x):
    return max(1, math.floor(x + 0.5))


# ---------------------------------------------------------------- trace builder

class Trace:
    def __init__(self, tid, title, proj):
        self.id, self.title, self.proj = tid, title, proj
        self.els, self.index, self.groups = [], {}, {}
        self.steps, self.tables, self.legend, self.extra = [], {}, {}, {}

    def add(self, eid, kind, geom, group=None, text=None):
        assert eid not in self.index, eid
        self.index[eid] = len(self.els)
        el = [eid, kind, geom]
        if text is not None:
            el.append(text)
        self.els.append(el)
        if group:
            self.groups.setdefault(group, []).append(eid)

    def poly(self, eid, pts, group=None):
        self.add(eid, "p", pts, group)

    def dot(self, eid, pt, group=None):
        self.add(eid, "d", pt, group)

    def line(self, eid, a, b, group=None):
        self.add(eid, "l", [a, b], group)

    def text(self, eid, pt, text, group=None, anchor=None):
        self.add(eid, "t", pt + ([anchor] if anchor else []), group, text)

    def step(self, caption, s=None, **kw):
        step = {"c": caption, "s": s or {}}
        step.update({k: v for k, v in kw.items() if v is not None})
        self.steps.append(step)

    def table(self, name, head, rows, fmts):
        self.tables[name] = {"h": head, "r": rows, "f": fmts}

    def finish(self, focus=None, scale_frac=0.22):
        pts = []
        for eid, kind, geom, *_ in self.els:
            if focus is not None and eid not in focus:
                continue
            if kind == "p" or kind == "l":
                pts += geom
            elif kind in "dt":
                pts.append(geom[:2])
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        w, h = x1 - x0, y1 - y0
        pad = 0.07 * max(w, h)
        w, h = w + 2 * pad, h + 2 * pad
        aspect = 4 / 3
        if w / h < aspect:
            w = h * aspect
        else:
            h = w / aspect
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        view = [round(cx - w / 2, 3), round(cy - h / 2, 3), round(w, 3), round(h, 3)]
        out = {
            "v": SCHEMA, "id": self.id, "title": self.title, "model": MODEL,
            "center": [round(self.proj.lat, 6), round(self.proj.lng, 6)],
            "view": view, "scale_km": nice(w * scale_frac),
            "legend": self.legend, "els": self.els, "groups": self.groups,
            "tables": self.tables, "steps": self.steps,
        }
        out.update(self.extra)
        return out


def cell_label(tr, eid, cid, proj, text, group=None):
    """A text label at the centre of a cell."""
    v = cell_vecs(cid)
    centre = sum(v) / 4
    tr.text(eid, proj.vec(centre / np.linalg.norm(centre)), text, group)


LEGEND_COMMON = {
    "field": "Field (triangle)",
    "wait": "Cell waiting in the queue",
    "poll": "Cell taken from the queue",
    "in": "Final cell, completely inside the field",
    "edge": "Final cell at level 13, cut by the field edge",
    "merged": "Final cell: all four children final",
    "kept": "Final coarse cell kept because of the budget",
    "miss": "Child cell that misses the field",
    "clip": "Part of a cell inside the field",
}


# ---------------------------------------------------------------- calculator access

class Calc:
    def __init__(self):
        folder = os.environ.get("GRUMP_DIR")
        if not folder:
            sys.exit("export_traces.py: set GRUMP_DIR to the extracted population rasters.")
        self.g = Grump(folder)
        self.g.density_table = tables.ensure_tables(self.g.folder)

    def field(self, pts):
        """The calculator's own result for a triangle, plus observer events."""
        events = []
        ids = cover(pts, observer=lambda e, **k: events.append((e, k)))
        assert ids == cover(pts), "observer changed the covering"
        r = mu_field(self.g, pts)
        assert [c[0] for c in r["cells"]] == ids, "covering differs from mu_field"
        cells = []
        for cid, level, ov, dens in r["cells"]:
            assert math.isclose(ov, overlaps(pts, [cid])[0][0][2], rel_tol=1e-12)
            cells.append({"id": cid, "t": tok(cid), "lv": level, "ov": ov, "d": dens,
                          "c": ov * dens, "area": cell_area_km2(cid), "reg": region_token(cid)})
        regions = {}
        for c in cells:
            regions[c["reg"]] = regions.get(c["reg"], 0.0) + c["ov"] * c["d"]
        total = sum(max(1, v) for v in regions.values())
        assert r["mu"] == round_half_up(total) and math.isclose(total, r["regional_total"], rel_tol=1e-12)
        return {"pts": pts, "ids": ids, "cells": cells, "regions": regions, "total": total,
                "mu": r["mu"], "area": r["area"], "events": events}

    def mean_density(self, cid):
        return float(density(self.g, cid))


def check_block(f):
    """The numbers the consistency test recomputes."""
    return {
        "points_e6": [list(p) for p in f["pts"]],
        "area_km2": f["area"],
        "cells": [[c["t"], c["lv"], c["ov"], c["d"]] for c in f["cells"]],
        "regions": [[k, v] for k, v in sorted(f["regions"].items())],
        "total": f["total"],
        "mu": f["mu"],
    }


def field_rows(f):
    return [[c["t"], c["lv"], c["area"], c["ov"], c["d"], c["c"], c["reg"]] for c in f["cells"]]


CELL_HEAD = ["Cell", "Level", "Cell km²", "Overlap km²", "Density", "Contribution", "Region"]
CELL_FMT = ["s", 0, 3, 5, 3, 3, "s"]


def coord_str(p):
    return f"{p[0] / 1e6:.6f}, {p[1] / 1e6:.6f}"


def portal_labels(tr, proj, pts, names="ABC"):
    for n, p in zip(names, pts):
        tr.dot(f"v{n}", proj.ll(p[0] / 1e6, p[1] / 1e6))
        tr.text(f"t{n}", proj.ll(p[0] / 1e6, p[1] / 1e6), n)


def finish_steps(tr, f, name_prefix, cap_regions, cap_round, tb_name):
    """Shared last two steps: region sums with the minimum, and the rounding."""
    regs = sorted(f["regions"].items())
    rows = []
    for tkn, v in regs:
        n = sum(1 for c in f["cells"] if c["reg"] == tkn)
        rows.append([tkn, n, v, max(1, v)])
    tr.table(tb_name, ["Region (level 6)", "Cells", "Sum of contributions", "After minimum of 1"], rows, ["s", 0, 3, 3])
    tr.step(cap_regions, {}, tb=[tb_name, len(rows), None])
    total = f["total"]
    tr.step(cap_round, {}, tb=[tb_name, len(rows), None],
            eq=f"round half up({fmt(total, 3)}) = floor({fmt(total, 3)} + 0.5) = {fmt(f['mu'], 0)} MU")


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
            "population counts at these 16 points, numbered here in enumeration order.", {"@d13": "dot", "@n13": "t"})
    tr.step(f"To find the pixel of a sample point, the point is moved half a pixel to the north and to the west (open circles). "
            f"The pixel that contains the moved point is the one that is read. Sample {demo + 1} lies in pixel "
            f"({pc}, {pr}), but its moved point lies in pixel ({gi13[demo]}, {gj13[demo]}), which is read. "
            f"{len(plain_diff)} of the 16 samples read a different pixel than the one containing them.",
            {"@sh": "shift", "@sl": "link", f"px:{pc}:{pr}": "plain", f"px:{gi13[demo]}:{gj13[demo]}": "read"})
    s = {f"px:{k[0]}:{k[1]}": "read" for k in px13}
    s.update({"@ln": "link", "@sh": "", "@sl": ""})
    tr.step(f"The 16 samples read {len(px13)} different pixels. Several samples can read the same pixel.", s)
    s = {f"pv:{k[0]}:{k[1]}": "t" for k in px13}
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
    s = {f"pv:{k[0]}:{k[1]}": "t" for k in px12}
    tr.step(f"Counts of the {len(px12)} pixels that are read by the 64 samples. Each sample counts once, so a pixel read by "
            f"several samples counts several times.", s, tb=["pixels", len(prow), None],
            eq=f"({' + '.join(f'{n12[k]}×{px12[k]:.3f}' for k in sorted(px12, key=lambda k: (k[1], k[0])))}) / 64 = {fmt(d12, 3)}")
    s = {"@pv": "", "@d12": "", "@kt": "t"}
    tr.step("Each of the four children averages 16 of the 64 samples. The mean of the four child densities is therefore "
            f"the density of the parent: {fmt(d12, 3)}. The level-12 cell has a different density than the level-13 cell "
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


# ---------------------------------------------------------------- shared helpers for a3..a5

STATE_OF = {"inside": "in", "max_level": "edge", "merged": "merged", "budget": "kept"}


def why_map(f):
    """Why each final cell is final; a cell made by the final normalisation is "merged"."""
    why = {k["cid"]: k["why"] for e, k in f["events"] if e == "result"}
    return {cid: why.get(cid, "merged") for cid in f["ids"]}


def bins(values, log=True):
    xs = [math.log10(max(v, 1e-9)) if log else v for v in values]
    lo, hi = min(xs), max(xs)
    return [min(9, int((x - lo) / (hi - lo) * 10)) if hi > lo else 0 for x in xs], (lo, hi)


def share(c):
    return c["ov"] / c["area"]


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
    tr.step(f"Merging does not change the result for a cell that lies completely inside the field: the overlap of the parent is "
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


# ---------------------------------------------------------------- animation 4

def circle_pts(proj, lat, lng, ang, n=72):
    """Points at angular distance ang around (lat, lng), projected."""
    c = ll_unit(lat, lng)
    a = np.cross(c, [0, 0, 1.0])
    a = a / np.linalg.norm(a) if np.linalg.norm(a) > 1e-9 else np.array([1.0, 0, 0])
    b = np.cross(c, a)
    return [proj.vec(math.cos(ang) * c + math.sin(ang) * (math.cos(t) * a + math.sin(t) * b))
            for t in (2 * math.pi * k / n for k in range(n))]


def build_a4(calc):
    pts = A4_FIELD
    f = calc.field(pts)
    assert f["mu"] == EXPECTED_MU["a4"], f["mu"]
    why = why_map(f)
    events = f["events"]
    lat0, lng0 = sum(p[0] for p in pts) / 3e6, sum(p[1] for p in pts) / 3e6
    proj = Proj(lat0, lng0)
    tr = Trace("a4", "The 20-cell budget", proj)
    tr.poly("fld", [proj.ll(p[0] / 1e6, p[1] / 1e6) for p in pts])
    start = events[0][1]
    assert events[0][0] == "start" and start["mode"] == "neighbors"
    axis = CellId(start["leaf"]).to_lat_lng()
    tr.poly("cap", circle_pts(proj, axis.lat().degrees, axis.lng().degrees, start["angle"]))
    seen = {}

    def ensure(cid):
        if cid not in seen:
            seen[cid] = f"c:{tok(cid)}"
            tr.poly(seen[cid], [proj.vec(v) for v in cell_vecs(cid)], "c")
        return seen[cid]

    by_id = {c["id"]: c for c in f["cells"]}
    polls = [k for e, k in events if e == "poll"]
    tr.legend = {"p:field": "Field (triangle)", "p:cap": "Bounding circle of the field", "p:wait": "Cell waiting in the queue",
                 "p:poll": "Cell taken from the queue now", "p:done": "Cell that has been split", "p:in": "Final: completely inside the field",
                 "p:edge": "Final: level 13", "p:kept": "Final: kept whole because of the budget", "p:miss": "Child that misses the field",
                 "p:clip": "Part of a cell inside the field", "p:heat": "Cell shaded by its density"}
    pos = 0

    def run_events(ops):
        """Apply push/result events up to the next poll to ops."""
        nonlocal pos
        while pos < len(events) and events[pos][0] not in ("poll", "normalize"):
            e, k = events[pos]
            if e == "push":
                ops[ensure(k["cid"])] = "wait"
            elif e == "result":
                ops[ensure(k["cid"])] = STATE_OF[k["why"]]
            pos += 1

    # initial step
    pos = 1
    ops = {}
    for cid in start["initial"]:
        ops[ensure(cid)] = "miss"
    run_events(ops)
    n_start = sum(1 for v in ops.values() if v != "miss")
    a_km = start["angle"] * RE
    tr.step(f"An example field of {f['area']:.1f} km² ({'; '.join(coord_str(p) for p in pts)}). The cells used to compute its MU "
            f"are chosen by a covering with a budget of 20 cells.", {"fld": "field"})
    tr.step(f"The bounding circle of the field has a radius of {a_km:.1f} km. From it the start level {start['level']} follows. "
            f"The covering starts with the cells of level {start['level']} around the cell corner nearest the centre of the circle; "
            f"{n_start} of the {len(start['initial'])} touch the field and wait in the queue.",
            dict({"cap": "cap"}, **ops))
    prev = None
    for n, p in enumerate(polls, 1):
        ops = {}
        if prev is not None and prev["state"] != "kept":
            ops[prev["el"]] = "done"
        el = ensure(p["cid"])
        ops[el] = "poll"
        touching = {c for c, _ in p["children"]}
        if p["expand"]:
            for ch in CellId(p["cid"]).children():
                ops[ensure(ch.id())] = "miss"
        run_events(ops)
        lvl = CellId(p["cid"]).level()
        k = len(p["children"])
        total = p["result"] + p["queue"] + k
        if k == 1:
            dec = "Only one child touches the field, so the cell is always split."
        elif p["expand"]:
            dec = f"{total} ≤ 20: the cell is split."
        else:
            dec = f"{total} > 20: the cell is kept whole."
        cap = (f"Poll {n} of {len(polls)}: cell {tok(p['cid'])}, level {lvl}, {k} of its 4 children {'touches' if k == 1 else 'touch'} the field. "
               f"Result {p['result']} + queue {p['queue']} + children {k} = {total}. {dec}")
        if n == 1:
            cap += " Cells with equal priority leave the queue in the order of a binary heap (see Method)."
        if not p["expand"]:
            ops[el] = "kept"
        tr.step(cap, ops, bud={"r": p["result"], "q": p["queue"], "k": k, "max": 20, "go": bool(p["expand"] or k == 1)})
        prev = {"el": el, "state": "kept" if not p["expand"] else "poll"}
    if prev and prev["state"] != "kept":
        pass
    cells = f["cells"]
    count = {}
    for c in cells:
        count[STATE_OF[why[c["id"]]]] = count.get(STATE_OF[why[c["id"]]], 0) + 1
    levels = {}
    for c in cells:
        levels[c["lv"]] = levels.get(c["lv"], 0) + 1
    lv_text = ", ".join(f"{v} at level {k}" for k, v in sorted(levels.items()))
    st = {"cap": ""}
    st.update({ensure(c["id"]): STATE_OF[why[c["id"]]] for c in cells})
    for cid, el in seen.items():
        if cid not in by_id:
            st[el] = ""
    nk = count.get("kept", 0)
    tr.step(f"The queue is empty. The covering has {len(cells)} cells ({lv_text}). {nk} of them were kept whole because the budget was "
            f"used up, {count.get('in', 0)} {'lies' if count.get('in', 0) == 1 else 'lie'} completely inside the field and {count.get('edge', 0)} "
            f"{'is' if count.get('edge', 0) == 1 else 'are'} at level 13.", st)
    areas = sorted(c["area"] for c in cells)
    tr.step(f"Cell size compared with field size: the field has {f['area']:.0f} km², the cells have {areas[0]:.0f} to {areas[-1]:.0f} km², "
            f"between 1/{f['area'] / areas[0]:.0f} and 1/{f['area'] / areas[-1]:.0f} of the field. The budget does not allow cells small enough "
            f"to follow the field edge.", {})
    bnd = [c for c in cells if why[c["id"]] != "inside"]
    for c in bnd:
        tr.poly(f"cp:{c['t']}", [proj.vec(v) for v in clip_vecs(pts, c["id"])], "cp")
        cell_label(tr, f"sh:{c['t']}", c["id"], proj, f"{share(c) * 100:.0f} %", "sh")
    low = min(bnd, key=share)
    inside_area = sum(c["ov"] for c in bnd)
    tot_area = sum(c["area"] for c in bnd)
    st = {f"cp:{c['t']}": "clip" for c in bnd}
    st.update({f"sh:{c['t']}": "t" for c in bnd})
    tr.step(f"Part of each cell inside the field (percentage of the cell area). {len(bnd)} cells are cut by the field edge. Together "
            f"they have {tot_area:,.0f} km², of which {inside_area:,.0f} km² ({inside_area / tot_area * 100:.0f} %) lie inside the field. "
            f"Cell {low['t']} has only {share(low) * 100:.0f} % inside.", st)
    vals, (lo, hi) = bins([c["d"] for c in cells])
    tr.extra["bins"] = {seen[c["id"]]: b for c, b in zip(cells, vals)}
    tr.extra["ramp"] = {"label": "Density", "min": min(c["d"] for c in cells), "max": max(c["d"] for c in cells), "log": True}
    for c in cells:
        cell_label(tr, f"dl:{c['t']}", c["id"], proj, fmt(c["d"], 0), "dl")
    st = {f"cp:{c['t']}": "" for c in bnd}
    st.update({f"sh:{c['t']}": "" for c in bnd})
    st.update({seen[c["id"]]: "heat" for c in cells})
    st.update({f"dl:{c['t']}": "t" for c in cells})
    nsamp = 4 ** (15 - low["lv"])
    tr.step(f"Density of each cell. It is the mean over all {nsamp:,} sample points of a level-{low['lv']} cell, inside and outside the "
            f"field. In cell {low['t']}, {100 - share(low) * 100:.0f} % of the area lies outside the field, but its density, "
            f"{fmt(low['d'], 1)}, is the density of the whole cell.", st)
    tr.table("cells", CELL_HEAD, field_rows(f), CELL_FMT)
    st = {f"dl:{c['t']}": "" for c in cells}
    st.update({seen[c["id"]]: STATE_OF[why[c["id"]]] for c in cells})
    st.update({f"cp:{c['t']}": "clip" for c in bnd})
    tr.step(f"Contribution of each cell = overlap × density. The overlaps add up to the area of the field, {f['area']:.3f} km².",
            st, tb=["cells", len(cells), None])
    finish_steps(tr, f, "a4",
                 f"Contributions are added per level-6 region. {len(f['regions'])} regions are touched; a region sum below 1 would be raised to 1, "
                 f"none is.", "The total is rounded once, half up.", "regions")
    tr.extra["summary"] = [
        ["Portals", "; ".join(coord_str(p) for p in pts)], ["Area", f"{f['area']:.4f} km²"],
        ["Start level", str(start["level"])], ["Polls", str(len(polls))],
        ["Covering", f"{len(cells)} cells ({lv_text})"], ["Kept whole by the budget", str(nk)],
        ["Sum of contributions", fmt(f["total"], 6)], ["MU", fmt(f["mu"], 0)],
    ]
    tr.extra["cells"] = {"head": CELL_HEAD, "rows": field_rows(f), "fmt": CELL_FMT}
    tr.extra["check"] = check_block(f)
    tr.extra["check"]["start"] = {"level": start["level"], "polls": len(polls), "budget": 20}
    return tr.finish(focus={"fld", "cap"} | {seen[c["id"]] for c in cells})


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
            f"same cell. The level-{domG['lv']} cell averages an area a quarter as large as the level-{domF['lv']} cell in F.",
            dict({"@G": "", "@qG": "t"}, **{f"pG:{tok(c)}": STATE_OF[w] for c, w, _ in partsG}), tb=["partsG", 4, None],
            eq=f"({' + '.join(fmt(dens[('G', p[0])], 1) for p in partsG)}) / 4 = {fmt(domG['d'], 1)}")
    tr.step(f"Same ground, different cell. F counts {domF['ov']:,.0f} km² of its area at the density of the level-{domF['lv']} cell, "
            f"{fmt(domF['d'], 1)}. G counts {domG['ov']:,.0f} km² at the density of the level-{domG['lv']} cell, {fmt(domG['d'], 1)}. "
            f"G is part of F, but the density that applies to this ground is {domG['d'] / domF['d']:.1f} times as large.",
            {"@pG": "", "@qG": "", "fF": "field", "tF3": "t"}, tb=["cmp", 2, None],
            eq=f"F: {domF['ov']:,.0f} km² × {fmt(domF['d'], 1)} = {domF['c']:,.0f}     G: {domG['ov']:,.0f} km² × {fmt(domG['d'], 1)} = {domG['c']:,.0f}")
    tr.step(f"Result: G earns {fG['mu']:,} MU and F earns {fF['mu']:,} MU. The covering depends on the size of the field, and with it "
            f"the cells whose densities are averaged for a given piece of ground.", {}, tb=["totals", 2, None],
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


# ---------------------------------------------------------------- main

BUILDERS = [("a1", build_a1), ("a2", build_a2), ("a3", build_a3), ("a4", build_a4), ("a5", build_a5)]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=str(ROOT / "site" / "traces"))
    ap.add_argument("--check", action="store_true", help="compare with the existing files instead of writing")
    ap.add_argument("only", nargs="*", help="trace ids (default: all)")
    args = ap.parse_args()
    out = Path(args.out)
    calc = Calc()
    bad = 0
    for name, fn in BUILDERS:
        if args.only and name not in args.only:
            continue
        text = json.dumps(fn(calc), ensure_ascii=False, separators=(",", ":")) + "\n"
        path = out / f"{name}.json"
        if args.check:
            same = path.is_file() and path.read_text(encoding="utf-8") == text
            print(f"{name}: {'unchanged' if same else 'DIFFERS'}")
            bad += not same
        else:
            out.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
            print(f"{name}: {len(text.encode('utf-8')) / 1024:.1f} KB")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
