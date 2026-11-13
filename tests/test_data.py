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
