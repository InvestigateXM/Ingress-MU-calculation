"""Simple made-up example of a smaller field inside a bigger one that earns more MU."""

from .common import *  # noqa: F401,F403


def shoelace(p):
    return abs(sum(p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1] for i in range(len(p)))) / 2


def clip_box(poly, x0, y0, x1, y1):
    """Sutherland-Hodgman clip of a polygon to an axis-parallel box."""
    def cut(poly, inside, cross):
        out = []
        for i in range(len(poly)):
            a, b = poly[i - 1], poly[i]
            if inside(b):
                if not inside(a):
                    out.append(cross(a, b))
                out.append(b)
            elif inside(a):
                out.append(cross(a, b))
        return out
    X = lambda x: lambda a, b: (x, a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0]))
    Y = lambda y: lambda a, b: (a[0] + (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]), y)
    for inside, cross in [(lambda p: p[0] >= x0, X(x0)), (lambda p: p[0] <= x1, X(x1)),
                          (lambda p: p[1] >= y0, Y(y0)), (lambda p: p[1] <= y1, Y(y1))]:
        poly = cut(poly, inside, cross)
        if not poly:
            return []
    return poly


def build(calc):
    # Geometry in km, y down. The big cell is 6 km x 6 km, split into four 3 km x 3 km quarters.
    S = 3.0
    quarters = {"TL": (0, 0, 0), "TR": (S, 0, 1000), "BL": (0, S, 0), "BR": (S, S, 0)}   # corner, density
    # F: apex inside the dense quarter, wide side over the empty ones. G: the part of F in the dense quarter.
    F = [(5.4, 1.9), (1.4, 0.65), (1.4, 3.15)]
    G = [(5.4, 1.9), (3.0, 1.15), (3.0, 2.65)]
    dens_of = lambda r: quarters[r][2]
    area_F, area_G = shoelace(F), shoelace(G)
    in_dense = shoelace(clip_box(F, S, 0, 2 * S, S))
    mean = sum(q[2] for q in quarters.values()) / 4
    assert (round(area_F, 6), round(area_G, 6), round(in_dense, 6), mean) == (5.0, 1.8, 1.8, 250.0)
    assert math.isclose(shoelace(clip_box(G, S, 0, 2 * S, S)), area_G)       # G lies in the dense quarter
    mu_F, mu_G = round(area_F * mean, 6), round(area_G * 1000, 6)
    assert (mu_F, mu_G) == (1250.0, 1800.0) and mu_G > mu_F and area_G < area_F

    tr = Trace("a5g", "A smaller field with more MU, simple example", Proj(0.0, 0.0))
    tr.extra["schematic"] = True
    tr.poly("big", [(0, 0), (2 * S, 0), (2 * S, 2 * S), (0, 2 * S)])
    tr.extra["bins"] = {}
    for r, (x, y, d) in quarters.items():
        tr.poly(f"q{r}", [(x, y), (x + S, y), (x + S, y + S), (x, y + S)], "q")
        tr.extra["bins"][f"q{r}"] = 9 if d else 0
        tr.text(f"d{r}", [x + S / 2, y + 0.45], f"{d:,}", "d")
    tr.extra["ramp"] = {"label": "Density (MU per km²)", "min": 0, "max": 1000, "log": False}
    tr.poly("aF", F)
    tr.poly("aG", G)
    tr.poly("fF", F)
    tr.poly("fG", G)
    tr.text("lF", [2.3, 1.9], "F")
    tr.text("lG", [4.0, 1.9], "G")
    tr.text("mean", [S, S], "250", "mean")
    tr.legend = {"p:field": "Field F (big)", "p:field2": "Field G (small)",
                 "p:cell12": "The big cell (four quarters)", "p:clip": "Area that is counted"}
    tr.table("totals", ["Field", "Area km²", "Cell used", "Density", "MU"],
             [["F (big)", area_F, "the big cell", mean, mu_F], ["G (small)", area_G, "the dense quarter", 1000, mu_G]],
             ["s", 1, "s", 0, 0])

    tr.step("G lies inside F. Which of the two fields earns more MU?",
            {"fF": "field", "fG": "field2", "lF": "b", "lG": "b"})
    tr.step("Both fields stand on the same ground. Imagine a big square cell made of four quarters. One quarter is a city with "
            "1,000 MU per km². The other three are empty (0). The density of a cell is the MU per km² it holds.",
            {"@q": "heat", "@d": "t", "big": "cell12"})
    tr.step(f"F is big, so it has to use the whole big cell. Its density is the mean of its four quarters, 250. "
            f"F covers {area_F:.1f} km², so it earns {mu_F:,.0f} MU. Most of that area is empty, but the city is averaged into it.",
            {"@q": "fade", "@d": "", "mean": "b", "aF": "clip", "fG": "", "lG": ""},
            eq=f"mean = (1,000 + 0 + 0 + 0) / 4 = 250\nF: {area_F:.1f} km² × 250 = {mu_F:,.0f} MU")
    tr.step(f"G is small enough to use the city quarter on its own, with density 1,000. G covers {area_G:.1f} km², "
            f"so it earns {mu_G:,.0f} MU: more than F, although G is smaller and lies inside F.",
            {"aF": "", "aG": "clip", "mean": "", "qTR": "heat", "fG": "field2", "lG": "b", "dTR": "t", "lF": ""},
            eq=f"G: {area_G:.1f} km² × 1,000 = {mu_G:,.0f} MU")
    tr.step("Same city, different cell. F counts it at 250 because F has to use a big cell. G counts it at 1,000 because "
            "G can use a small one. Bigger fields have to use bigger cells.",
            {"aG": "", "aF": "", "@q": "fade", "qTR": "heat", "dTR": "", "fF": "field", "lF": "b"},
            tb=["totals", 2, None],
            eq=f"F: {area_F:.1f} km² × 250 = {mu_F:,.0f} MU\nG: {area_G:.1f} km² × 1,000 = {mu_G:,.0f} MU")
    tr.extra["summary"] = [["Area F / G", f"{area_F:.1f} / {area_G:.1f} km²"],
                           ["Density used F / G", f"{mean:.0f} / 1,000 MU per km²"],
                           ["MU F / G", f"{mu_F:,.0f} / {mu_G:,.0f}"]]
    return tr.finish(focus={"big"})


