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
    # the box the game draws around the field: its lat/lng extent (S2's GetRectBound gives the same numbers)
    lat_lo, lat_hi = min(p[0] for p in pts) / 1e6, max(p[0] for p in pts) / 1e6
    lng_lo, lng_hi = min(p[1] for p in pts) / 1e6, max(p[1] for p in pts) / 1e6
    corners = [(lat_lo, lng_lo), (lat_lo, lng_hi), (lat_hi, lng_hi), (lat_hi, lng_lo)]
    box = []
    for (a1, b1), (a2, b2) in zip(corners, corners[1:] + corners[:1]):
        box += [proj.ll(a1 + (a2 - a1) * t / 8, b1 + (b2 - b1) * t / 8) for t in range(8)]
    tr.poly("bbox", box)
    ax = ll_unit(axis.lat().degrees, axis.lng().degrees)
    cap_ratio = [math.acos(max(-1, min(1, float(ax @ ll_unit(*c))))) / start["angle"] for c in corners]
    # the cap is centred on the middle of the box and reaches the farthest corners (2 of 4, up to float noise)
    assert max(cap_ratio) < 1 + 1e-6 and sorted(cap_ratio)[-2] > 0.999, cap_ratio
    seen = {}

    def ensure(cid):
        if cid not in seen:
            seen[cid] = f"c:{tok(cid)}"
            tr.poly(seen[cid], [proj.vec(v) for v in cell_vecs(cid)], "c")
        return seen[cid]

    by_id = {c["id"]: c for c in f["cells"]}
    polls = [k for e, k in events if e == "poll"]
    tr.legend = {"p:field": "Field (triangle)", "p:bbox": "Box around the field", "p:cap": "Circle around the box", "p:hl": "Cell in focus", "p:wait": "Cell waiting to be checked",
                 "p:poll": "Cell being checked now", "p:done": "Cell that has been split", "p:in": "Final: completely inside the field",
                 "p:edge": "Final: smallest size (level 13)", "p:kept": "Final: kept whole because of the budget",
                 "p:miss": "Quarter that misses the field",
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

    cells = f["cells"]
    count = {}
    for c in cells:
        count[STATE_OF[why[c["id"]]]] = count.get(STATE_OF[why[c["id"]]], 0) + 1
    nk = count.get("kept", 0)
    final_state = {ensure(c["id"]): STATE_OF[why[c["id"]]] for c in cells}
    levels = {}
    for c in cells:
        levels[c["lv"]] = levels.get(c["lv"], 0) + 1
    lv_text = ", ".join(f"{v} at level {k}" for k, v in sorted(levels.items()))

    # the full record of the checks, stored for the test (the steps below merge them)
    record = [{"cell": tok(p["cid"]), "result": p["result"], "queue": p["queue"],
               "children": [tok(c) for c, _ in p["children"]], "split": bool(p["expand"])} for p in polls]

    # steps 1 and 2: the field and the outcome
    tr.step(f"This example field covers {f['area']:,.0f} km² around Munich. How many MU is it worth?", {"fld": "field"})
    tr.step(f"A big field is described by at most 20 cells, so the cells are big and stick out of the field. "
            f"Here the field gets {len(cells)} cells.", dict(final_state))

    # step 3: the box and the circle
    pos = 1
    ops = {ek: "" for ek in final_state}
    tr.step("To choose the cells, the game first draws a box around the field, from its northernmost to its southernmost "
            "and westernmost to easternmost point, and then a circle around that box. This circle is not the smallest "
            "possible one, but its size decides how large the first cells are.",
            dict({"bbox": "bbox", "cap": "cap"}, **ops))

    # step 4: the start cells
    run_events(ops)
    start_els = [k for k, v in ops.items() if v not in ("", "miss")]
    n_start = len(start_els)
    a_km = start["angle"] * RE
    tr.step(f"The circle is {a_km:.0f} km in radius, so the game starts with cells of level {start['level']}. "
            f"It picks the {n_start} cells of that size that touch the field. These are the first cells to check.",
            {"bbox": "", **{k: "hl" for k in start_els}})

    # steps 5 to 8: the checks, merged into a few steps
    n_first = 6
    n_refuse = next(n for n, p in enumerate(polls, 1) if not p["expand"])
    assert len(polls[n_first - 1]["children"]) == 4 and polls[n_first - 1]["expand"]
    assert all(p["expand"] for p in polls[:n_refuse - 1])
    prev = None
    for lo, hi in [(1, n_first - 1), (n_first, n_first), (n_first + 1, n_refuse - 1), (n_refuse, n_refuse)]:
        ops = {k: "wait" for k in start_els} if prev is None else {}
        for n in range(lo, hi + 1):
            p = polls[n - 1]
            if prev is not None and prev["state"] != "kept":
                ops[prev["el"]] = "done"
            el = ensure(p["cid"])
            ops[el] = "poll"
            if p["expand"]:
                for ch in CellId(p["cid"]).children():
                    ops[ensure(ch.id())] = "miss"
            run_events(ops)
            if not p["expand"]:
                ops[el] = "kept"
            prev = {"el": el, "state": "kept" if not p["expand"] else "poll"}
        p = polls[hi - 1]
        k = len(p["children"])
        total = p["result"] + p["queue"] + k
        bud = {"r": p["result"], "q": p["queue"], "k": k, "max": 20, "go": bool(p["expand"] or k == 1), "n": hi}
        if hi == n_first - 1:
            cap = ("The game checks the waiting cells in a fixed order; the order itself is not important here. "
                   "Each cell is split into 4 quarters, and only the quarters that touch the field are kept. "
                   "A cell with just one such quarter is always split, since that adds no cell.")
            bud = None
        elif hi == n_first:
            cap = (f"The orange cell is being checked. All 4 of its quarters touch the field. The bar counts the cells the field would have after the split: "
                   f"finished (solid), waiting (outlined) and new quarters (dotted). {total} is within the limit of 20, so the split goes ahead.")
        elif hi == n_refuse - 1:
            cap = f"The game keeps splitting. After {hi} checks the bar has reached {total} of the 20 cells allowed."
        else:
            cap = (f"Splitting the next cell (hatched) would bring the total to {total}, over the limit of 20, so it stays whole. "
                   f"From here on, no cell is split any more.")
        tr.step(cap, ops, bud=bud)
    assert not any(p["expand"] for p in polls[n_refuse - 1:])
    last = polls[-1]
    st = {"cap": "", "bbox": ""}
    st.update(final_state)
    for cid, el in seen.items():
        if cid not in by_id:
            st[el] = ""
    tr.step(f"The remaining {len(polls) - n_refuse} cells are kept whole too. That gives the {len(cells)} cells: "
            f"{nk} kept whole because of the budget and {count.get('in', 0)} completely inside the field.", st)
    bnd = [c for c in cells if why[c["id"]] != "inside"]
    for c in bnd:
        tr.poly(f"cp:{c['t']}", [proj.vec(v) for v in clip_vecs(pts, c["id"])], "cp")
        cell_label(tr, f"sh:{c['t']}", c["id"], proj, f"{share(c) * 100:.0f} %", "sh")
    low = min(bnd, key=share)
    inside_area = sum(c["ov"] for c in bnd)
    tot_area = sum(c["area"] for c in bnd)
    st = {f"cp:{c['t']}": "clip" for c in bnd}
    st.update({f"sh:{c['t']}": "t" for c in bnd})
    st[seen[low["id"]]] = "hl"
    tr.step(f"Most cells stick out of the field. The numbers show how much of each cell lies inside the field. "
            f"The orange cell at the top has only {share(low) * 100:.0f} % inside. Across the {len(bnd)} cells cut by the edge, {inside_area / tot_area * 100:.0f} % of their area is inside.", st)
    vals, (lo, hi) = bins([c["d"] for c in cells])
    tr.extra["bins"] = {seen[c["id"]]: b for c, b in zip(cells, vals)}
    tr.extra["ramp"] = {"label": "Density", "min": min(c["d"] for c in cells), "max": max(c["d"] for c in cells), "log": True}
    for c in cells:
        cell_label(tr, f"dl:{c['t']}", c["id"], proj, fmt(c["d"], 0), "dl")
    st = {f"cp:{c['t']}": "" for c in bnd}
    st.update({f"sh:{c['t']}": "" for c in bnd})
    st.update({seen[c["id"]]: "heat" for c in cells})
    st.update({f"dl:{c['t']}": "t" for c in cells})
    tr.step(f"Each cell has one density (MU per km²), shown by its shade and number. It is the mean over the whole cell, "
            f"including the part outside the field. A cell with {100 - share(low) * 100:.0f} % outside the field still counts with its full density.", st)
    tr.table("cells", CELL_HEAD, field_rows(f), CELL_FMT)
    st = {f"dl:{c['t']}": "" for c in cells}
    st.update({seen[c["id"]]: STATE_OF[why[c["id"]]] for c in cells})
    st.update({f"cp:{c['t']}": "clip" for c in bnd})
    tr.step(f"Each cell gives (part inside the field) × (density). The table lists the contribution of every cell, in MU before rounding. "
            f"The parts inside add up to the whole field, {f['area']:,.0f} km².",
            st, tb=["cells", len(cells), None])
    finish_steps(tr, f, "a4",
                 f"The contributions are added up per large region ({len(f['regions'])} here), and each large region gives at least 1 MU. "
                 f"Both regions are far above that.", f"The total is rounded once, to whole MU: {fmt(f['mu'], 0)} MU.", "regions")
    tr.extra["summary"] = [
        ["Portals", "; ".join(coord_str(p) for p in pts)], ["Area", f"{f['area']:.4f} km²"],
        ["Start level", str(start["level"])], ["Cells checked", str(len(polls))],
        ["Covering", f"{len(cells)} cells ({lv_text})"], ["Kept whole by the budget", str(nk)],
        ["Sum of contributions", fmt(f["total"], 6)], ["MU", fmt(f["mu"], 0)],
    ]
    tr.extra["cells"] = {"head": CELL_HEAD, "rows": field_rows(f), "fmt": CELL_FMT}
    tr.extra["check"] = check_block(f)
    tr.extra["check"]["start"] = {"level": start["level"], "polls": len(polls), "budget": 20}
    tr.extra["check"]["polls"] = record
    return tr.finish(focus={"fld", "cap", "bbox"} | {seen[c["id"]] for c in cells})


build = build_a4
