"""MU calculation and level-six regional minimum."""

import collections
import math
import os
import s2sphere
from .covering import cover
from .geometry import overlaps, density

MODEL = "grump2000-s2java2011-l6min1"
# Density samples every level-15 cell inside each covering cell; cost grows as 4**(15 - level).
MAX_SAMPLES = int(os.environ.get("MU_MAX_SAMPLES", 4**11))


def round_mu(total):
    return max(1, math.floor(total + 0.5))


def region_result(pts, result):
    groups = collections.defaultdict(float)
    for cid, level, area, density in result["cells"]:
        cell = s2sphere.CellId(cid)
        if level >= 6:
            groups[cell.parent(6).id()] += area * density
        else:
            children = [child.id() for child in cell.children(6)]
            for child, _, overlap in overlaps(pts, children)[0]:
                if overlap > 1e-12:
                    groups[child] += overlap * density
    return (
        max(1, math.floor(sum((max(1, value) for value in groups.values())) + 0.5)),
        dict(groups),
    )


def mu_field(grump, points):
    cell_ids = cover(points)
    levels = [s2sphere.CellId(c).level() for c in cell_ids]
    samples = sum(4 ** (15 - level) for level in levels if level < 15)
    if samples > MAX_SAMPLES:
        raise ValueError(
            "The field is too large for this calculator "
            f"(covering needs {samples:,} density samples; limit {MAX_SAMPLES:,})."
        )
    intersections, area = overlaps(points, cell_ids)
    cells = []
    total = 0.0
    for cell_id, level, overlap in intersections:
        population = density(grump, cell_id)
        cells.append((cell_id, level, overlap, population))
        total += overlap * population
    result = dict(total=total, area=area, cells=cells)
    result["mu"], result["regions"] = region_result(points, result)
    result["regional_total"] = sum(
        max(1, value) for value in result["regions"].values()
    )
    return result
