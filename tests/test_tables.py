import json
import numpy as np
import pytest
from mu_calculator import tables
from mu_calculator.geometry import Grump, density


def test_atomic_table_and_invalidation(tmp_path, monkeypatch):
    folder = tmp_path / "bil"
    folder.mkdir()
    header = folder / "aaaup00ag.hdr"
    header.write_text("NROWS 1\nNCOLS 1\nULXMAP 0.004166666666666667\nULYMAP 0.004166666666666667\n")
    raster = folder / "aaaup00ag.bil"
    np.array([7], dtype="<f4").tofile(raster)
    monkeypatch.setattr(tables, "COUNT", 2)
    a = tables.ensure_tables(folder, workers=1)
    assert isinstance(a, np.memmap)
    g = Grump(str(folder))
    for index in range(2):
        cid = (2 * index + 1) << 48
        assert a[index].tobytes() == np.float64(density(g, cid)).tobytes()
    assert tables.load_table(folder) is not None
    np.array([9], dtype="<f4").tofile(raster)
    assert tables.load_table(folder) is None
    b = tables.ensure_tables(folder, workers=1)
    assert len(b) == 2
    info = json.loads(tables.table_path(folder).read_text())
    assert info["bytes"] == 144


def test_table_lookup():
    for i in (0, 4095, 4096, 24575):
        assert tables.lookup(np.arange(24576, dtype=float), (2*i+1)<<48) == i
