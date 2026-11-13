import math
import itertools
import numpy as np
import pytest
import s2sphere
from mu_calculator import geometry
from mu_calculator.calculator import mu_field, round_mu, region_result
from mu_calculator.coordinates import parse_coordinates
from mu_calculator.covering import cover, normalize, JHeap
from mu_calculator.geometry import overlaps, unit, tri_area_km2, RE, Grump, density

TRIANGLE = ["52.324297,10.182664", "52.244048,10.167482", "52.295984,10.231064"]


def test_parse_formats_and_half_up():
    points = parse_coordinates(
        ["1.0000005,-2.0000005", {"lat": 1.1, "lng": -2}, "1,-2.1"]
    )
    assert points[0] == (1000001, -2000001)


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        ["0,0"] * 3,
        ["91,0", "1,1", "2,0"],
        ["NaN,0", "1,1", "2,0"],
        ["0,0", "0,1", "0,2"],
        ["0,0", "0,0.0000001", "1,1"],
    ],
)
def test_invalid(value):
    with pytest.raises(ValueError):
        parse_coordinates(value)


def test_rounding():
    assert [round_mu(x) for x in [0, 0.5, 1.49, 1.5, 2.5]] == [1, 1, 1, 2, 3]


def test_spherical_octant():
    assert tri_area_km2(
        [unit(0, 0), unit(0, 90000000), unit(90000000, 0)]
    ) == pytest.approx(math.pi / 2 * RE**2)


def test_overlap_conserves_area():
    pts = parse_coordinates(TRIANGLE)
    pieces, area = overlaps(pts, cover(pts))
    assert sum(x[2] for x in pieces) == pytest.approx(area, rel=1e-10)
    assert area == pytest.approx(16.3116, abs=0.0001)


def test_covering_order_and_bounds():
    points = parse_coordinates(TRIANGLE)
    expected = cover(points)
    for permutation in itertools.permutations(points):
        assert cover(permutation) == expected
    assert 0 < len(expected) <= 20
    assert all(s2sphere.CellId(x).level() <= 13 for x in expected)
    parent = s2sphere.CellId.from_lat_lng(s2sphere.LatLng.from_degrees(52, 10)).parent(
        8
    )
    assert normalize([c.id() for c in parent.children()]) == [parent.id()]


def test_java_heap_tie_order():
    heap = JHeap()
    for label in "abcd":
        heap.push((1, label))
    assert [heap.pop()[1] for _ in range(4)] == list("adcb")


def test_zero_density_regional_minimum():
    points = parse_coordinates(["0,-140", "0.1,-140", "0,-139.9"])
    pieces, _ = overlaps(points, cover(points))
    mu, regions = region_result(
        points, {"cells": [(cid, level, area, 0) for cid, level, area in pieces]}
    )
    assert mu == len(regions) == 2


def test_mosaic_sampling_and_cache_isolation(tmp_path):
    for country, count in [("aaa", 2), ("bbb", 3)]:
        (tmp_path / (country + "up00ag.hdr")).write_text(
            "NROWS 1\nNCOLS 1\nULXMAP 0.004166666666666667\nULYMAP 0.004166666666666667\n"
        )
        np.array([count], dtype="<f4").tofile(tmp_path / (country + "up00ag.bil"))
    g = Grump(str(tmp_path))
    assert g.sample([0], [1 / 120])[0] == 5
    assert g.sample([30], [30])[0] == 0
    assert Grump(str(tmp_path)).density_cache is not g.density_cache


def test_field_size_guard():
    points = parse_coordinates(["0,0", "0,120", "1,-120"])
    with pytest.raises(ValueError, match="too large"):
        mu_field(None, points)


def test_density_cache_is_bounded(tmp_path, monkeypatch):
    (tmp_path / "aaaup00ag.hdr").write_text(
        "NROWS 1\nNCOLS 1\nULXMAP 0.004166666666666667\nULYMAP 0.004166666666666667\n"
    )
    np.array([1], dtype="<f4").tofile(tmp_path / "aaaup00ag.bil")
    monkeypatch.setattr(geometry, "CACHE_LIMIT", 3)
    g = Grump(str(tmp_path))
    for n in range(10):
        density(g, s2sphere.CellId.from_face_pos_level(0, n, 15).id())
    assert len(g.density_cache) <= 3
