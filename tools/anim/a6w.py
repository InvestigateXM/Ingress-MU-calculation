"""Why cells have different sizes, part 2: the real grid on a globe, zooming in to Munich."""

from .common import *  # noqa: F401,F403

MUNICH = (48.137, 11.575)


def build(calc):
    proj = Ortho(*MUNICH)
    tr = Trace("a6w", "The real grid of cells", proj)
    tr.extra["map"] = "a6w"
    tr.extra["place"] = "The world"
    leaf = CellId.from_lat_lng(s2sphere.LatLng.from_degrees(*MUNICH))

    def grid_lines(level, group, nseg):
        """All edges of all cells of a level on the visible side of the globe, as short segments."""
        seen = set()
        cells = []
        for face in range(6):
            start = CellId.from_face_pos_level(face, 0, 0)
            if level == 0:
                cells.append(start)
            else:
                c = start.child_begin(level)
                end = start.child_end(level)
                while c != end:
                    cells.append(c)
                    c = c.next()
        n = 0
        for c in cells:
            v = cell_vecs(c.id())
            for i in range(4):
                a, b = v[i], v[(i + 1) % 4]
                key = tuple(sorted((tuple(np.round(a, 9)), tuple(np.round(b, 9)))))
                if key in seen:
                    continue
                seen.add(key)
                run, prev = [], None
                for p in edge_points(a, b, nseg) + [None]:
                    if p is not None and prev is not None and proj.visible(p) != proj.visible(prev):
                        dp, dq = float(np.dot(prev, proj.c)), float(np.dot(p, proj.c))
                        run.append(proj.vec(prev + (p - prev) * dp / (dp - dq), 0))  # where it meets the horizon
                    prev = p
                    if p is not None and proj.visible(p):
                        run.append(proj.vec(p, 0))
                        continue
                    if len(run) >= 2:  # an open line drawn as a there-and-back outline
                        tr.poly(f"{group}:{n}", run + run[-2:0:-1], group)
                        n += 1
                    run = []

    def cell_poly(cid, nseg, nd):
        v = cell_vecs(cid)
        pts = []
        for i in range(4):
            pts += [proj.vec(p, nd) for p in edge_points(v[i], v[(i + 1) % 4], nseg)[:-1]]
        return pts

    def around(level, radius_km, group, nseg, nd):
        """Cells of a level whose centre lies within radius_km of Munich, as polygons."""
        here = leaf.parent(level)
        todo, done = [here], {here.id()}
        c0 = ll_unit(*MUNICH)
        out = []
        while todo:
            c = todo.pop()
            ctr = sum(cell_vecs(c.id())) / 4
            if RE * math.acos(min(1.0, float(np.dot(ctr / np.linalg.norm(ctr), c0)))) > radius_km:
                continue
            out.append(c)
            for nb in c.get_all_neighbors(level):
                if nb.id() not in done:
                    done.add(nb.id())
                    todo.append(nb)
        for c in out:
            tr.poly(f"{group}:{c.to_token()}", cell_poly(c.id(), nseg, nd), group)
        return out

    grid_lines(0, "g0", 24)
    grid_lines(1, "g1", 12)
    grid_lines(2, "g2", 6)
    around(4, 2300, "c4", 6, 0)
    around(6, 420, "c6", 4, 1)
    around(8, 110, "c8", 2, 1)
    around(10, 28, "c10", 1, 2)
    hl = {lv: f"c{lv}:{leaf.parent(lv).to_token()}" for lv in (4, 6, 8, 10)}
    tr.dot("mu", proj.ll(*MUNICH))
    # a "Munich" label per zoom, a little above and right of the dot
    for i, w in enumerate((18000, 5200, 900, 230, 58)):
        tr.text(f"mt{i}", [round(w * 0.035, 2), round(-w * 0.03, 2)], "Munich", "mt", "start")

    area = lambda lv: 4 * math.pi * RE ** 2 / (6 * 4 ** lv)
    H = 2.12 * RE
    globe = [round(-H * 2 / 3, 1), round(-H / 2, 1), round(H * 4 / 3, 1), round(H, 1)]

    def view(w):
        return [round(-w / 2, 2), round(-w * 3 / 8, 2), round(w, 2), round(w * 3 / 4, 2)]

    tr.legend = {"p:cell12": "The 6 biggest cells (level 0)", "p:cell": "Smaller cells",
                 "p:hl": "The cell that contains Munich", "d:dot": "Munich"}
    tr.step("This grid is not made for your field. It is one fixed grid over the whole world. It starts with 6 giant "
            "cells, like the faces of a cube blown up into a ball.", {"@g0": "cell12", "mu": "dot", "mt0": "t"}, view=globe)
    tr.step("Each of them is cut into 4, and again: 24 cells at level 1, 96 at level 2. Every cell of every level has "
            "its fixed place, worked out in advance.", {"@g1": "cell", "@g2": "cell"}, view=globe)
    tr.step(f"Zoomed in on Europe: level 4. Each cell is about {area(4):,.0f} km². The orange one contains Munich.",
            {"@g1": "", "@c4": "cell", hl[4]: "hl", "mt0": "", "mt1": "t"}, view=view(5200))
    tr.step(f"Level 6, about {area(6):,.0f} km² per cell. Two more cuts turned each level-4 cell into 16 of these. "
            "Munich happens to lie close to the edge of its cell.",
            {"@c4": "", "@g2": "", "@g0": "", "@c6": "cell", hl[6]: "hl", "mt1": "", "mt2": "t"}, view=view(900))
    tr.step(f"Level 8, about {area(8):,.0f} km² per cell, roughly a city.",
            {"@c6": "", "@c8": "cell", hl[8]: "hl", "mt2": "", "mt3": "t"}, view=view(230))
    tr.step(f"Level 10, about {area(10):,.0f} km² per cell. Three more cuts give level 13, about {area(13):.1f} km², "
            "the smallest cells used for MU. Next: those smallest cells in Munich.",
            {"@c8": "", "@c10": "cell", hl[10]: "hl", "mt3": "", "mt4": "t"}, view=view(58))
    tr.extra["summary"] = [["Biggest cells", "6 (level 0)"], ["Cells at level 13", f"{6 * 4 ** 13:,}"],
                           ["Centre of the globe view", "Munich"]]
    return tr.finish(view=globe)
