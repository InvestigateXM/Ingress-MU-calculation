import json
import os
from pathlib import Path
import pytest
from mu_calculator import Grump, mu_field


@pytest.mark.skipif(
    not os.environ.get("GRUMP_DIR"),
    reason="Set GRUMP_DIR to extracted population rasters.",
)
def test_fixed_triangles():
    grump = Grump()
    from mu_calculator.tables import ensure_tables
    grump.density_table = ensure_tables(grump.folder)
    for field in json.loads(Path(__file__).with_name("triangles.json").read_text()):
        result = mu_field(grump, field["points"])
        assert result["mu"] == field["mu"]
        assert len(result["regions"]) == field["regions"]


@pytest.mark.skipif(not os.environ.get("GRUMP_DIR"), reason="Population rasters required.")
def test_large_triangle():
    grump = Grump()
    from mu_calculator.tables import ensure_tables
    grump.density_table = ensure_tables(grump.folder)
    result = mu_field(grump, [(-9011934,13410663), (22905822,33272151), (-596665,35028782)])
    assert result["mu"] == 76732083
    assert result["total"] == pytest.approx(76732083.15944749, abs=1e-7)

@pytest.mark.skipif(not os.environ.get("GRUMP_DIR"), reason="Population rasters required.")
def test_multilevel_direct_bits():
    import numpy as np
    import s2sphere as s2
    from mu_calculator.geometry import l15_centres
    from mu_calculator.tables import tile_values
    g = Grump()
    rng = np.random.default_rng(418)
    for lat, lon in [(52,10), (-4,24), (28,77), (0,-100)]:
        parent = s2.CellId.from_lat_lng(s2.LatLng.from_degrees(lat,lon)).parent(6)
        raw = g.sample(*l15_centres(parent.id())).reshape(512,512)
        for level in range(6,12):
            values = tile_values(parent, raw, level)
            for index in rng.integers(0, len(values), 3):
                child = parent.child_begin(level).advance(int(index))
                direct = np.float64(g.sample(*l15_centres(child.id())).mean())
                assert values[index].tobytes() == direct.tobytes()


@pytest.mark.skipif(not os.environ.get("MU_TEST_TABLE_DIR"), reason="Prepared multilevel tables required.")
def test_multilevel_mu():
    from mu_calculator.tables import fingerprint, load_table
    folder = os.environ['MU_TEST_TABLE_DIR']
    signature = fingerprint(folder)
    arrays = {l: load_table(folder, signature, l) for l in range(6,12)}
    assert all(a is not None for a in arrays.values())
    grump = Grump(folder)
    for field in json.loads(Path(__file__).with_name('triangles.json').read_text())[:3]:
        results = []
        for maximum in (6,11):
            grump.density_table = {l:a for l,a in arrays.items() if l <= maximum}
            grump.density_cache.clear()
            results.append(mu_field(grump, field['points']))
        assert results[0] == results[1]
