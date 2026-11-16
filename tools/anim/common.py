"""Shared helpers for the trace builders: projection, Trace, calculator access."""

import argparse
import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import s2sphere

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from mu_calculator import tables  # noqa: E402
from mu_calculator.calculator import MODEL, mu_field, region_result  # noqa: E402
from mu_calculator.covering import cover  # noqa: E402
from mu_calculator.geometry import (  # noqa: E402
    D, RE, Grump, _clip, _normals, density, l15_centres, overlaps, sph_area, unit,
)

SCHEMA = 1
DATA = ROOT / "tools" / "trace_data.json"
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

    def finish(self, focus=None, scale_frac=0.22, view=None):
        """view: force [x, y, w, h], e.g. to share another trace's orientation map (extra["map"])."""
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
        if view is None:
            view = [round(cx - w / 2, 3), round(cy - h / 2, 3), round(w, 3), round(h, 3)]
        else:
            w = view[2]
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


class _ReplayGrump:
    """Answers pixel reads from the recorded excerpt (tools/trace_data.json)."""

    def __init__(self, pixels):
        self.pixels = pixels
        self.folder = None

    pix = Grump.pix

    def sample(self, lat, lng):
        gi, gj = self.pix(np.atleast_1d(np.asarray(lat, float)), np.atleast_1d(np.asarray(lng, float)))
        try:
            return np.array([self.pixels[(int(a), int(b))] for a, b in zip(gi, gj)])
        except KeyError as e:
            sys.exit(f"export_traces.py: pixel {e} is not in the recorded data; export with GRUMP_DIR once.")


class ReplayCalc(Calc):
    """Calc without the population rasters: densities and pixel values come from a
    recorded file that a GRUMP export writes (--record). Coverings, overlaps, regions
    and rounding are still computed by the shipped calculator code."""

    def __init__(self, path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.densities = data["densities"]
        self.g = _ReplayGrump({(a, b): v for a, b, v in data["pixels"]})

    def mean_density(self, cid):
        try:
            return self.densities[tok(cid)]
        except KeyError:
            sys.exit(f"export_traces.py: density of {tok(cid)} is not in the recorded data; export with GRUMP_DIR once.")

    def field(self, pts):
        events = []
        ids = cover(pts, observer=lambda e, **k: events.append((e, k)))
        assert ids == cover(pts), "observer changed the covering"
        inter, area = overlaps(pts, ids)
        r = {"cells": [(cid, lv, ov, self.mean_density(cid)) for cid, lv, ov in inter]}
        mu, regs = region_result(pts, r)
        cells = []
        for cid, level, ov, dens in r["cells"]:
            cells.append({"id": cid, "t": tok(cid), "lv": level, "ov": ov, "d": dens,
                          "c": ov * dens, "area": cell_area_km2(cid), "reg": region_token(cid)})
        regions = {}
        for c in cells:
            regions[c["reg"]] = regions.get(c["reg"], 0.0) + c["ov"] * c["d"]
        total = sum(max(1, v) for v in regions.values())
        assert mu == round_half_up(total)
        return {"pts": pts, "ids": ids, "cells": cells, "regions": regions, "total": total,
                "mu": mu, "area": area, "events": events}


class RecordingCalc(Calc):
    """Calc on the rasters that remembers every density and pixel the builders use."""

    def __init__(self):
        super().__init__()
        self.densities, self.pixels = {}, {}
        sample = self.g.sample

        def recording_sample(lat, lng):
            vals = sample(lat, lng)
            gi, gj = self.g.pix(np.atleast_1d(np.asarray(lat, float)), np.atleast_1d(np.asarray(lng, float)))
            for a, b, v in zip(gi.tolist(), gj.tolist(), np.atleast_1d(vals).tolist()):
                self.pixels[(a, b)] = v
            return vals
        self.g.sample = recording_sample

    def mean_density(self, cid):
        d = super().mean_density(cid)
        self.densities[tok(cid)] = d
        return d

    def field(self, pts):
        f = super().field(pts)
        for c in f["cells"]:
            self.densities[c["t"]] = c["d"]
        return f

    def write(self, path):
        data = {"note": "Densities and pixel counts used by tools/export_traces.py (GRUMP v1 excerpt).",
                "densities": dict(sorted(self.densities.items())),
                "pixels": [[a, b, v] for (a, b), v in sorted(self.pixels.items())]}
        Path(path).write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8", newline="\n")


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


