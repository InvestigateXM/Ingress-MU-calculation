"""Animation 4."""

from .common import *  # noqa: F401,F403
from .common import _clip, _normals  # noqa: F401


# ---------------------------------------------------------------- animation 4

def circle_pts(proj, lat, lng, ang, n=72):
    """Points at angular distance ang around (lat, lng), projected."""
    c = ll_unit(lat, lng)
    a = np.cross(c, [0, 0, 1.0])
    a = a / np.linalg.norm(a) if np.linalg.norm(a) > 1e-9 else np.array([1.0, 0, 0])
    b = np.cross(c, a)
    return [proj.vec(math.cos(ang) * c + math.sin(ang) * (math.cos(t) * a + math.sin(t) * b))
            for t in (2 * math.pi * k / n for k in range(n))]


def build_a4(calc):
    pts = A4_FIELD
    f = calc.field(pts)
    assert f["mu"] == EXPECTED_MU["a4"], f["mu"]
    why = why_map(f)
    events = f["events"]
    lat0, lng0 = sum(p[0] for p in pts) / 3e6, sum(p[1] for p in pts) / 3e6
    proj = Proj(lat0, lng0)
    tr = Trace("a4", "The 20-cell budget", proj)
    tr.poly("fld", [proj.ll(p[0] / 1e6, p[1] / 1e6) for p in pts])
    start = events[0][1]
    assert events[0][0] == "start" and start["mode"] == "neighbors"
    axis = CellId(start["leaf"]).to_lat_lng()
    tr.poly("cap", circle_pts(proj, axis.lat().degrees, axis.lng().degrees, start["angle"]))
    seen = {}

    def ensure(cid):
        if cid not in seen:
            seen[cid] = f"c:{tok(cid)}"
            tr.poly(seen[cid], [proj.vec(v) for v in cell_vecs(cid)], "c")
        return seen[cid]

    by_id = {c["id"]: c for c in f["cells"]}
    polls = [k for e, k in events if e == "poll"]
    tr.legend = {"p:field": "Field (triangle)", "p:cap": "Bounding circle of the field", "p:wait": "Cell waiting in the queue",
                 "p:poll": "Cell taken from the queue now", "p:done": "Cell that has been split", "p:in": "Final: completely inside the field",
                 "p:edge": "Final: level 13", "p:kept": "Final: kept whole because of the budget", "p:miss": "Child that misses the field",
                 "p:clip": "Part of a cell inside the field", "p:heat": "Cell shaded by its density"}
    pos = 0

    def run_events(ops):
        """Apply push/result events up to the next poll to ops."""
        nonlocal pos
        while pos < len(events) and events[pos][0] not in ("poll", "normalize"):
            e, k = events[pos]
            if e == "push":
                ops[ensure(k["cid"])] = "wait"
            elif e == "result":
                ops[ensure(k["cid"])] = STATE_OF[k["why"]]
            pos += 1

    # initial step
    pos = 1
    ops = {}
    for cid in start["initial"]:
        ops[ensure(cid)] = "miss"
    run_events(ops)
    n_start = sum(1 for v in ops.values() if v != "miss")
    a_km = start["angle"] * RE
    tr.step(f"An example field of {f['area']:.1f} km² ({'; '.join(coord_str(p) for p in pts)}). The cells used to compute its MU "
            f"are chosen by a covering with a budget of 20 cells.", {"fld": "field"})
    tr.step(f"The bounding circle of the field has a radius of {a_km:.1f} km. From it the start level {start['level']} follows. "
            f"The covering starts with the cells of level {start['level']} around the cell corner nearest the centre of the circle; "
            f"{n_start} of the {len(start['initial'])} touch the field and wait in the queue.",
            dict({"cap": "cap"}, **ops))
    prev = None
    for n, p in enumerate(polls, 1):
        ops = {}
        if prev is not None and prev["state"] != "kept":
            ops[prev["el"]] = "done"
        el = ensure(p["cid"])
        ops[el] = "poll"
        touching = {c for c, _ in p["children"]}
        if p["expand"]:
            for ch in CellId(p["cid"]).children():
                ops[ensure(ch.id())] = "miss"
        run_events(ops)
        lvl = CellId(p["cid"]).level()
        k = len(p["children"])
        total = p["result"] + p["queue"] + k
        if k == 1:
            dec = "Only one child touches the field, so the cell is always split."
        elif p["expand"]:
            dec = f"{total} ≤ 20: the cell is split."
        else:
            dec = f"{total} > 20: the cell is kept whole."
        cap = (f"Poll {n} of {len(polls)}: cell {tok(p['cid'])}, level {lvl}, {k} of its 4 children {'touches' if k == 1 else 'touch'} the field. "
               f"Result {p['result']} + queue {p['queue']} + children {k} = {total}. {dec}")
        if n == 1:
            cap += " Cells with equal priority leave the queue in the order of a binary heap (see Method)."
        if not p["expand"]:
            ops[el] = "kept"
        tr.step(cap, ops, bud={"r": p["result"], "q": p["queue"], "k": k, "max": 20, "go": bool(p["expand"] or k == 1)})
        prev = {"el": el, "state": "kept" if not p["expand"] else "poll"}
    if prev and prev["state"] != "kept":
        pass
    cells = f["cells"]
    count = {}
    for c in cells:
        count[STATE_OF[why[c["id"]]]] = count.get(STATE_OF[why[c["id"]]], 0) + 1
    levels = {}
    for c in cells:
        levels[c["lv"]] = levels.get(c["lv"], 0) + 1
    lv_text = ", ".join(f"{v} at level {k}" for k, v in sorted(levels.items()))
    st = {"cap": ""}
    st.update({ensure(c["id"]): STATE_OF[why[c["id"]]] for c in cells})
    for cid, el in seen.items():
        if cid not in by_id:
            st[el] = ""
    nk = count.get("kept", 0)
    tr.step(f"The queue is empty. The covering has {len(cells)} cells ({lv_text}). {nk} of them were kept whole because the budget was "
            f"used up, {count.get('in', 0)} {'lies' if count.get('in', 0) == 1 else 'lie'} completely inside the field and {count.get('edge', 0)} "
            f"{'is' if count.get('edge', 0) == 1 else 'are'} at level 13.", st)
    areas = sorted(c["area"] for c in cells)
    tr.step(f"Cell size compared with field size: the field has {f['area']:.0f} km², the cells have {areas[0]:.0f} to {areas[-1]:.0f} km², "
            f"between 1/{f['area'] / areas[0]:.0f} and 1/{f['area'] / areas[-1]:.0f} of the field. The budget does not allow cells small enough "
            f"to follow the field edge.", {})
    bnd = [c for c in cells if why[c["id"]] != "inside"]
    for c in bnd:
        tr.poly(f"cp:{c['t']}", [proj.vec(v) for v in clip_vecs(pts, c["id"])], "cp")
        cell_label(tr, f"sh:{c['t']}", c["id"], proj, f"{share(c) * 100:.0f} %", "sh")
    low = min(bnd, key=share)
    inside_area = sum(c["ov"] for c in bnd)
    tot_area = sum(c["area"] for c in bnd)
    st = {f"cp:{c['t']}": "clip" for c in bnd}
    st.update({f"sh:{c['t']}": "t" for c in bnd})
    tr.step(f"Part of each cell inside the field (percentage of the cell area). {len(bnd)} cells are cut by the field edge. Together "
            f"they have {tot_area:,.0f} km², of which {inside_area:,.0f} km² ({inside_area / tot_area * 100:.0f} %) lie inside the field. "
            f"Cell {low['t']} has only {share(low) * 100:.0f} % inside.", st)
    vals, (lo, hi) = bins([c["d"] for c in cells])
    tr.extra["bins"] = {seen[c["id"]]: b for c, b in zip(cells, vals)}
    tr.extra["ramp"] = {"label": "Density", "min": min(c["d"] for c in cells), "max": max(c["d"] for c in cells), "log": True}
    for c in cells:
        cell_label(tr, f"dl:{c['t']}", c["id"], proj, fmt(c["d"], 0), "dl")
    st = {f"cp:{c['t']}": "" for c in bnd}
    st.update({f"sh:{c['t']}": "" for c in bnd})
    st.update({seen[c["id"]]: "heat" for c in cells})
    st.update({f"dl:{c['t']}": "t" for c in cells})
    nsamp = 4 ** (15 - low["lv"])
    tr.step(f"Density of each cell. It is the mean over all {nsamp:,} sample points of a level-{low['lv']} cell, inside and outside the "
            f"field. In cell {low['t']}, {100 - share(low) * 100:.0f} % of the area lies outside the field, but its density, "
            f"{fmt(low['d'], 1)}, is the density of the whole cell.", st)
    tr.table("cells", CELL_HEAD, field_rows(f), CELL_FMT)
    st = {f"dl:{c['t']}": "" for c in cells}
    st.update({seen[c["id"]]: STATE_OF[why[c["id"]]] for c in cells})
    st.update({f"cp:{c['t']}": "clip" for c in bnd})
    tr.step(f"Contribution of each cell = overlap × density. The overlaps add up to the area of the field, {f['area']:.3f} km².",
            st, tb=["cells", len(cells), None])
    finish_steps(tr, f, "a4",
                 f"Contributions are added per level-6 region. {len(f['regions'])} regions are touched; a region sum below 1 would be raised to 1, "
                 f"none is.", "The total is rounded once, half up.", "regions")
    tr.extra["summary"] = [
        ["Portals", "; ".join(coord_str(p) for p in pts)], ["Area", f"{f['area']:.4f} km²"],
        ["Start level", str(start["level"])], ["Polls", str(len(polls))],
        ["Covering", f"{len(cells)} cells ({lv_text})"], ["Kept whole by the budget", str(nk)],
        ["Sum of contributions", fmt(f["total"], 6)], ["MU", fmt(f["mu"], 0)],
    ]
    tr.extra["cells"] = {"head": CELL_HEAD, "rows": field_rows(f), "fmt": CELL_FMT}
    tr.extra["check"] = check_block(f)
    tr.extra["check"]["start"] = {"level": start["level"], "polls": len(polls), "budget": 20}
    return tr.finish(focus={"fld", "cap"} | {seen[c["id"]] for c in cells})


build = build_a4
