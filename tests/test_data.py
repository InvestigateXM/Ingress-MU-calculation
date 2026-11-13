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
    for field in json.loads(Path(__file__).with_name("triangles.json").read_text()):
        result = mu_field(grump, field["points"])
        assert result["mu"] == field["mu"]
        assert len(result["regions"]) == field["regions"]
