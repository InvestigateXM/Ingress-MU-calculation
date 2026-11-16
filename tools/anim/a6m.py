"""Why cells have different sizes, part 3: the real smallest cells near Munich; which four can be combined."""

from .common import *  # noqa: F401,F403

# The orientation map of "Big cells inside, small cells at the edge" (a3) is reused, so centre and view are its own.
CENTER = (48.175891, 11.686537)
VIEW = [-4.635, -3.074, 9.587, 7.19]


def build(calc):
    proj = Proj(*CENTER)
    tr = Trace("a6m", "The real smallest cells near Munich", proj)
    tr.extra["map"] = "a3"
    x0, y0, w, h = VIEW
    inside = lambda p, m=0.0: x0 - m <= p[0] <= x0 + w + m and y0 - m <= p[1] <= y0 + h + m
    poly = lambda cid: [proj.vec(v) for v in cell_vecs(cid)]

    def cells_in_view(level):
        start = CellId.from_lat_lng(s2sphere.LatLng.from_degrees(*CENTER)).parent(level)
        todo, seen, out = [start], {start.id()}, []
        while todo:
            c = todo.pop()
            if not any(inside(p, 0.6) for p in poly(c.id())):
                continue
            out.append(c)
            for nb in c.get_edge_neighbors():
                if nb.id() not in seen:
                    seen.add(nb.id())
                    todo.append(nb)
        return out

    c12 = cells_in_view(12)
    c13 = [k for c in c12 for k in c.children()]
    for c in c13:
        tr.poly(f"s:{c.to_token()}", poly(c.id()), "s")
    for c in c12:
        tr.poly(f"b:{c.to_token()}", poly(c.id()), "b")

    # one level-12 cell near the left of the view: its four quarters can be combined
    dist = lambda c, tx, ty: math.hypot(*(np.subtract(np.mean(poly(c.id()), axis=0), [tx, ty])))
    good = min(c12, key=lambda c: dist(c, x0 + w * 0.27, y0 + h * 0.5))
    kids = list(good.children())
    # a corner shared by four level-12 cells near the right: the four smallest cells touching it form a square
    key = lambda v: tuple(np.round(v, 9))
    corners = {}
    for c in c12:
        for v in cell_vecs(c.id()):
            corners.setdefault(key(v), []).append(c)
    target = np.array([x0 + w * 0.72, y0 + h * 0.5])
    vk, four = min(((k, cs) for k, cs in corners.items() if len(cs) == 4),
                   key=lambda kc: np.linalg.norm(np.subtract(proj.vec(np.array(kc[0])), target)))
    bad = [k for c in four for k in c.children() if any(key(v) == vk for v in cell_vecs(k.id()))]
    assert len(bad) == 4 and len({b.parent(12).id() for b in bad}) == 4
    assert all(any(inside(p) for p in poly(c.id())) for c in kids + bad)

    def below(cells, text, eid):
        pts = [p for c in cells for p in poly(c.id())]
        x = sum(p[0] for p in pts) / len(pts)
        y = max(p[1] for p in pts) + 0.35
        tr.text(eid, [round(x, 3), round(y, 3)], text, "tx")
    below(kids, "✓ one cell", "tok")
    below(bad, "✗ not a cell", "tbad")

    area = lambda lv: 4 * math.pi * RE ** 2 / (6 * 4 ** lv)
    ex = {13: "a few city blocks", 12: "a city district", 11: "a part of a town", 10: "a small town",
          9: "a large town", 8: "a city", 7: "a large city and its surroundings", 6: "a large region"}
    rows = [[lv, area(lv), ex[lv]] for lv in range(13, 5, -1)]
    tr.table("levels", ["Level", "Average area km²", "Example"], rows, [0, 2, "s"])
    tr.table("cells", ["Cell", "Level", "Area km²", "Role"],
             [[good.to_token(), 12, cell_area_km2(good.id()), "bigger cell"]]
             + [[k.to_token(), 13, cell_area_km2(k.id()), "its quarter"] for k in kids]
             + [[b.to_token(), 13, cell_area_km2(b.id()), f"quarter of {b.parent(12).to_token()}"] for b in bad],
             ["s", 0, 3, "s"])
    tr.legend = {"p:sub": "Smallest cell (level 13)", "p:cell12": "Next bigger cell (level 12)",
                 "p:hl": "One level-12 cell", "p:in": "Its four quarters: can be combined",
                 "p:hl2": "Four different level-12 cells", "p:kept": "A square of four that is not a cell"}
    tr.step(f"Up close, just north-east of Munich. These are the real smallest cells, level 13, about "
            f"{area(13):.1f} km² each. They are not squares on the map, but they fit together without gaps.",
            {"@s": "sub"})
    tr.step("Every four of them are the quarters of one level-12 cell (thick outlines). "
            "Which four belong together is fixed, like everything else in the grid.", {"@b": "cell12"})
    tr.step("These four are the quarters of one level-12 cell. So the game can combine them into that one bigger cell.",
            {f"b:{good.to_token()}": "hl", **{f"s:{k.to_token()}": "in" for k in kids}, "tok": "b"},
            tb=["cells", 5, None])
    tr.step("These four also form a square, but each belongs to a different level-12 cell (purple). "
            "No cell of the grid lies there, so they can never be combined.",
            {f"b:{good.to_token()}": "cell12", **{f"s:{k.to_token()}": "sub" for k in kids}, "tok": "",
             **{f"b:{c.to_token()}": "hl2" for c in four}, **{f"s:{b.to_token()}": "kept" for b in bad}, "tbad": "b"},
            tb=["cells", 9, None])
    tr.step(f"For MU the smallest cells have level 13. Level 12 is about {area(12):.0f} km², level 10 about "
            f"{area(10):.0f} km² and level 6 about {area(6):,.0f} km². A small field uses small cells, a big field "
            "can use bigger ones.",
            {**{f"b:{c.to_token()}": "cell12" for c in four}, **{f"s:{b.to_token()}": "sub" for b in bad}, "tbad": ""},
            tb=["levels", len(rows), None])
    tr.extra["summary"] = [["Smallest cell used for MU", f"level 13, about {area(13):.2f} km²"],
                           ["Cells drawn", f"{len(c13)} at level 13 in {len(c12)} at level 12"],
                           ["Combinable four", f"quarters of {good.to_token()}"],
                           ["Not combinable four", ", ".join(b.to_token() for b in bad)]]
    return tr.finish(view=VIEW)
