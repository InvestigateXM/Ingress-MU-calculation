"""The committed animation data (site/traces/*.json) is internally consistent and not stale.

No population data is needed: coverings and overlaps are recomputed from the stored
coordinates, densities are taken from the files. Regenerate the files with
tools/export_traces.py when the covering rules change.
"""

import json
import math
from pathlib import Path

import numpy as np
import pytest
import s2sphere

from mu_calculator.calculator import MODEL
from mu_calculator.covering import cover
from mu_calculator.geometry import RE, _normals, overlaps, unit

TRACES = Path(__file__).resolve().parent.parent / "site" / "traces"
FILES = sorted(TRACES.glob("a*.json"))
LOAD = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in FILES}


def token_id(token):
    cid = s2sphere.CellId.from_token(token)
    assert cid.is_valid(), token
    return cid.id()


def field_blocks(tr):
    check = tr["check"]
    if "points_e6" in check:
        return [check]
    return [check[k] for k in ("outer", "inner") if k in check]


def test_expected_files_exist():
    assert set(LOAD) == {"a1", "a2", "a3", "a4", "a5"}


@pytest.mark.parametrize("name", sorted(LOAD))
def test_structure(name):
    tr = LOAD[name]
    assert tr["model"] == MODEL
    assert len((TRACES / f"{name}.json").read_bytes()) < 100_000
    ids = {e[0] for e in tr["els"]}
    assert len(ids) == len(tr["els"])
    for group in tr["groups"].values():
        assert set(group) <= ids
    for step in tr["steps"]:
        for key in step["s"]:
            assert key[1:] in tr["groups"] if key[0] == "@" else key in ids, key
        if "tb" in step:
            table = tr["tables"][step["tb"][0]]
            assert step["tb"][1] <= len(table["r"])
            assert all(len(r) == len(table["h"]) == len(table["f"]) for r in table["r"])
    text = (TRACES / f"{name}.json").read_text(encoding="utf-8")
    for forbidden in ("/mnt/", ":\\", "GRUMP_DIR"):
        assert forbidden not in text


@pytest.mark.parametrize("name", ["a2", "a3", "a4", "a5"])
def test_fields(name):
    for block in field_blocks(LOAD[name]):
        pts = [tuple(p) for p in block["points_e6"]]
        cells = block["cells"]
        ids = [token_id(c[0]) for c in cells]
        # the covering of the stored triangle is the stored covering (catches stale files)
        assert cover(pts) == ids
        for token, level, overlap, dens in cells:
            assert s2sphere.CellId.from_token(token).level() == level and 6 <= level <= 13
            assert dens >= 0
        # overlaps are the calculator's overlaps and add up to the area of the field
        recomputed, area = overlaps(pts, ids)
        assert math.isclose(area, block["area_km2"], rel_tol=1e-12)
        for (token, level, overlap, dens), (_, _, ov) in zip(cells, recomputed):
            assert math.isclose(overlap, ov, rel_tol=1e-9, abs_tol=1e-12)
        assert math.isclose(sum(c[2] for c in cells), area, rel_tol=1e-7)
        # contributions, regions with the minimum of 1, one rounding
        regions = {}
        for token, level, overlap, dens in cells:
            region = s2sphere.CellId.from_token(token).parent(6).to_token()
            regions[region] = regions.get(region, 0.0) + overlap * dens
        stored = dict((k, v) for k, v in block["regions"])
        assert set(stored) == set(regions)
        for k, v in regions.items():
            assert math.isclose(stored[k], v, rel_tol=1e-9, abs_tol=1e-9)
        total = sum(max(1, v) for v in regions.values())
        assert math.isclose(block["total"], total, rel_tol=1e-9)
        assert block["mu"] == max(1, math.floor(total + 0.5))
        # the table of covering cells shows the same contributions
    tr = LOAD[name]
    for key in ("cells", "cells2"):
        if key in tr:
            block = field_blocks(tr)[1 if key == "cells2" else 0]
            expected = {c[0]: c for c in block["cells"]}
            assert [r[0] for r in tr[key]["rows"]] == list(expected)
            for token, level, cell_km2, overlap, dens, contribution, region in tr[key]["rows"]:
                assert [token, level, overlap, dens] == expected[token]
                assert math.isclose(contribution, overlap * dens, rel_tol=1e-12)
                assert s2sphere.CellId.from_token(token).level() == level
                assert s2sphere.CellId.from_token(token).parent(6).to_token() == region


def test_summaries_state_the_mu():
    for name in ("a2", "a3", "a4"):
        mu = field_blocks(LOAD[name])[0]["mu"]
        assert ["MU", f"{mu:,}"] in LOAD[name]["summary"]
    outer, inner = field_blocks(LOAD["a5"])
    assert ["MU F / G", f"{outer['mu']:,} / {inner['mu']:,}"] in LOAD["a5"]["summary"]


def test_nested_fields_a5():
    outer, inner = field_blocks(LOAD["a5"])
    assert inner["mu"] > outer["mu"] and inner["area_km2"] < outer["area_km2"]
    assert inner["mu"] > 1.5 * outer["mu"]
    assert outer["area_km2"] < 100_000
    normals = _normals([unit(*p) for p in outer["points_e6"]])
    margins = []
    for p in inner["points_e6"]:
        v = unit(*p)
        d = [RE * math.asin(float(np.dot(n, v)) / float(np.linalg.norm(n))) for n in normals]
        assert min(d) > -1e-6          # inside or on the edge of the outer triangle
        if p not in outer["points_e6"]:
            margins.append(min(d))
    assert len(margins) == 1 and margins[0] > 1.0      # the third portal is clearly inside
    assert math.isclose(margins[0], LOAD["a5"]["check"]["margin_km"], rel_tol=1e-9)


def test_a4_budget_trace():
    tr = LOAD["a4"]
    assert tr["check"]["start"]["budget"] == 20
    polls = [s for s in tr["steps"] if "bud" in s]
    events = []
    cover(tr["check"]["points_e6"], observer=lambda e, **k: events.append((e, k)))
    actual = [k for e, k in events if e == "poll"]
    assert len(polls) == len(actual)
    assert len(polls) == tr["check"]["start"]["polls"]
    for s, event in zip(polls, actual):
        b = s["bud"]
        assert token_id(s["c"].split("cell ", 1)[1].split(",", 1)[0]) == event["cid"]
        assert (b["r"], b["q"], b["k"], b["go"]) == (
            event["result"], event["queue"], len(event["children"]), event["expand"])
        assert b["max"] == 20
        # a cell is split exactly when the three counts fit the budget (or has a single child)
        assert b["go"] == (b["k"] == 1 or b["r"] + b["q"] + b["k"] <= 20)


def test_a1_samples_and_licence_excerpt():
    c = LOAD["a1"]["check"]
    s13, s12 = c["samples13"], c["samples12"]
    assert len(s13) == 16 and len(s12) == 64
    assert math.isclose(math.fsum(v for _, _, v in s13) / 16, c["density13"], rel_tol=1e-12)
    assert math.isclose(math.fsum(v for _, _, v in s12) / 64, c["density12"], rel_tol=1e-12)
    assert math.isclose(sum(d for _, d in c["children"]) / 4, c["density12"], rel_tol=1e-12)
    assert dict(c["children"])[c["cell13"]] == c["density13"]
    # every pixel has one value; the level-13 samples read a subset of the level-12 pixels
    pixels = {}
    for col, row, v in s12:
        assert pixels.setdefault((col, row), v) == v
    assert all(pixels[(col, row)] == v for col, row, v in s13)
    # only the excerpt: the pixels of these two cells, a few dozen values at most
    assert len(pixels) <= 24
    assert s2sphere.CellId.from_token(c["cell12"]).id() == s2sphere.CellId.from_token(c["cell13"]).parent(12).id()
    # no other trace carries per-sample values
    for name, tr in LOAD.items():
        if name != "a1":
            assert "samples13" not in tr["check"] and "samples12" not in tr["check"]


def test_orientation_maps_match_trace_projections():
    folder = TRACES.parent / 'maps'
    size = 0
    for name, trace in LOAD.items():
        path = folder / (name + '.json')
        data = json.loads(path.read_text(encoding='utf-8'))
        size += path.stat().st_size
        assert data['center'] == trace['center'] and data['view'] == trace['view']
        assert data['features'] and data['labels']
        assert ('OpenStreetMap' if name <= 'a3' else 'Natural Earth') in data['source']
        x, y, w, h = data['view']
        for kind, coords, closed in data['features']:
            assert kind in ('road', 'rail', 'water', 'river', 'urban')
            assert len(coords) >= (4 if closed else 2)
            for a, b in coords:
                assert x - .001 <= a <= x + w + .001
                assert y - .001 <= b <= y + h + .001
    assert size < 70_000


def test_comparison_uses_the_actual_covering_cells():
    tr = LOAD['a5']
    for field, key in [('F', 'outer'), ('G', 'inner')]:
        c = tr['comparison'][field]
        block = tr['check'][key]
        cells = {row[0]: row for row in block['cells']}
        assert set(c['cover']) == {field + ':' + token for token in cells}
        token, level, overlap, dens = cells[c['token']]
        assert c['highlight'] == field + ':' + token
        assert (c['level'], c['overlap'], c['density']) == (level, overlap, dens)
        assert c['contribution'] == overlap * dens
