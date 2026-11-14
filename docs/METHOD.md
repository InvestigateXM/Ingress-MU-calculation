# How Mind Units (MU) for an Ingress control field are calculated

This document describes, step by step, how the number of Mind Units (MU) awarded for a control field can be computed from the three portal coordinates of the field. The raster, sampling, covering-queue, overlap and aggregation rules are specified below. Exact S2 boundary behaviour is defined by the versioned primitives identified in section 4; those primitives must be reused or ported for an exact re-implementation.

The method is an independent empirical reconstruction; it is not official and is not affiliated with Niantic. It builds on Gordon Ludlow's [Reverse Engineering MU](https://gordonludlow.com/ingress/reverse-engineering-mu/), which was the starting point for this work.

## Contents

1. Summary
2. Population data (GRUMP v1)
3. S2 geometry background
4. The covering of the triangle
5. Cell density
6. Overlap area
7. Regional minimum and final rounding
8. Worked example
9. Implementation pitfalls
10. Known limitations and scope
11. References

---

## 1. Summary

### Input

Three portal positions, each a pair of integers `(latE6, lngE6)`: latitude and longitude in degrees multiplied by 1,000,000 and kept as integers. A coordinate such as `52.324297` is `52324297`. Nothing else about the field (portal levels, agent, faction, link order, vertex order) is used.

### Output

One integer, `MU >= 1`.

### Formula

```
T         the spherical triangle with the three portals as vertices
C(T)      the covering of T by S2 cells (section 4)

density(C)   = mean of the population-count raster value at the centre of
               every level-15 S2 cell inside the cell C           (section 5)
area(T, C)   = spherical area of (T intersected with C), in km^2,
               Earth radius 6371.01 km                              (section 6)

region_sum(R) = sum of area(T, C) * density(C) over all covering cells C
                with ancestor(C, 6) = R
                (every covering cell has level >= 6, section 4)

MU(T) = max(1, floor( sum over regions R of max(1, region_sum(R)) + 0.5 ))
```

A region `R` is a level-6 S2 cell that contains at least one covering cell. A covering cell is never coarser than level 6, so each covering cell belongs to exactly one region: itself (level 6) or its level-6 ancestor (finer cells).

The raster value is used directly as "MU per km^2". It is a population count per raster pixel and is not divided by the pixel area.

### Order of steps

The order is part of the definition. Changing it changes results.

1. Convert the three E6 coordinates to unit vectors on the sphere.
2. Compute the S2 covering of the triangle (section 4).
3. For every covering cell, compute its density (section 5).
4. For every covering cell, compute the overlap area with the triangle (section 6).
5. Multiply, and add up the products per level-6 S2 region.
6. Raise each region's sum to at least 1.
7. Add the regions, round once (round half up), and enforce an overall minimum of 1 (section 7).

### Fixed parameters

| Quantity | Value |
|---|---|
| Coordinate precision | integer E6 degrees |
| Earth radius | 6371.01 km (sphere) |
| Covering: maximum cells | 20 (a work budget that the minimum level overrides) |
| Covering: maximum level | 13 |
| Covering: minimum level | 6 |
| Covering: level modulus | 1 |
| Density sampling level | 15 |
| Region level | 6 |
| Raster grid spacing `D` | 1/120 degree (30 arc-seconds) |
| Arithmetic | IEEE-754 double precision throughout |

---

## 2. Population data (GRUMP v1)

### Dataset

The population source is the **Global Rural-Urban Mapping Project, Version 1 (GRUMPv1): Population Count Grid**, produced by CIESIN (Columbia University) with IFPRI, the World Bank and CIAT, and distributed by the NASA Socioeconomic Data and Applications Center (SEDAC). The product provides gridded population counts for 1990, 1995 and 2000 at 30 arc-second resolution (about 1 km at the equator).

The calculation uses:

* the **year 2000** grid,
* the variant **adjusted to UN country totals** ("counts adjusted to match UN country totals"), not the unadjusted variant,
* the **count** grid, not the density grid,
* the **per-country** archives in **BIL** format.

Other years, the unadjusted counts (`up00g`), the density grids and other population products give different numbers and are not equivalent.

### Obtaining the data

Register for a free [NASA Earthdata Login](https://urs.earthdata.nasa.gov/). Open the [GRUMPv1 Population Count Grid in Earthdata Search](https://search.earthdata.nasa.gov/search/granules?p=C3540929345-ESDIS), select the country-level year-2000, 30 arc-second BIL granules, and use their download links after authentication. Authorize the data-access application if prompted. The [collection metadata](https://cmr.earthdata.nasa.gov/search/concepts/C3540929345-ESDIS.umm_json) supplies the current access link; the legacy SEDAC catalogue URL is not a download instruction. Per-country archives are named like `<iso3>_grumpv1_pcount_00_bil_30.zip`, where `<iso3>` is the lower-case ISO 3166 alpha-3 country code. Each archive contains, among other files, for the year 2000:

```
<iso3>up00ag.bil    adjusted counts (the file that is used)
<iso3>up00ag.hdr    its header (the file that is used)
<iso3>up00g.bil     unadjusted counts (NOT used)
<iso3>up00g.hdr     unadjusted header (NOT used)
```

Only the files whose names end in `up00ag.bil` and `up00ag.hdr` are used. Archives for continents and for the whole globe also exist (two-letter prefixes); they must not be mixed in, because they would be summed on top of the country files (see below). Use the country files only.

The [NASA collection use constraints](https://cmr.earthdata.nasa.gov/search/concepts/C3540929345-ESDIS.umm_json) reserve copyright to Columbia University, IFPRI, The World Bank and CIAT. Commercial use, non-free resale and redistribution require explicit written permission from those rights holders. Reports, publications, new datasets, derived products and services must acknowledge them. Download the rasters from the distributor unless permission for redistribution has been obtained; the code licence does not cover them.

### File format

Each `.hdr` is a text file of `KEY value` lines separated by whitespace. Example (one country):

```
BYTEORDER      I
LAYOUT         BIL
NROWS          1200
NCOLS          1320
NBANDS         1
NBITS          32
BANDROWBYTES   5280
TOTALROWBYTES  5280
PIXELTYPE      FLOAT
ULXMAP         5.00416666666665
ULYMAP         55.9958333332933
XDIM           0.0083333333333
YDIM           0.0083333333333
NODATA         -3.4028235e+038
```

The fields that matter:

| Field | Meaning |
|---|---|
| `NROWS`, `NCOLS` | raster size in pixels |
| `ULXMAP`, `ULYMAP` | longitude and latitude of the **centre** of the upper-left pixel, in degrees |
| `BYTEORDER I` | little-endian ("Intel") |
| `NBITS 32`, `PIXELTYPE FLOAT` | 32-bit IEEE floating point |
| `NODATA` | the no-data sentinel, about -3.4e38 |

The `.bil` file is the raw array: `NROWS x NCOLS` values of little-endian float32, row-major, first row at the top (north), first column at the left (west). With a single band, "band interleaved by line" is the same as plain row-major storage. The file size is exactly `NROWS * NCOLS * 4` bytes (for the example, 1200 * 1320 * 4 = 6,336,000 bytes). The pixel size is taken as exactly `D = 1/120` degree for every raster; the `XDIM`/`YDIM` values in the header are not used.

Pixels over water, and pixels outside a country, hold either the no-data sentinel or `0`, depending on the file. A value is **valid** if it is greater than `-1e30`. A valid value of `0` is a real zero.

### Global pixel grid

All rasters are placed on one global grid with spacing `D = 1/120` degree: 43,200 columns (longitude -180 to +180) and 21,600 rows (latitude +90 down to -90). A raster's position on the global grid is derived from its header:

```
col_origin = round( (ULXMAP - D/2 + 180) / D )
row_origin = round( (90 - (ULYMAP + D/2)) / D )
```

`ULXMAP - D/2` is the west edge of the first pixel and `ULYMAP + D/2` is its north edge. The `round` means nearest integer, ties to even (Python rounding). It removes the small decimal truncation in the header values (for example `5.00416666666665`), so the origin is an exact integer. For the example header: `col_origin = 22200`, `row_origin = 4080`.

### Pixel lookup for a sample point

For a sample at latitude `lat` and longitude `lng` in degrees, the global pixel indices are

```
col_global = floor( (lng - D/2 + 180) / D )
row_global = floor( (90 - (lat + D/2)) / D )
```

and for each raster

```
col = col_global - col_origin
row = row_global - row_origin
```

The lookup is deliberately shifted by half a pixel. Written with the fractional global pixel position `fx = (lng + 180)/D` and `fy = (90 - lat)/D` it is `col_global = floor(fx - 0.5)` and `row_global = floor(fy - 0.5)`, whereas a plain lookup would be `floor(fx)` and `floor(fy)`. Equivalently, the pixel used is the one whose centre is the nearest lattice centre at or to the west of the point, and at or to the north of it. This offset is part of the method; a conventional "pixel containing the point" lookup gives different values near the edges of populated areas.

### Mosaic of the country rasters

The country rasters overlap: the bounding box of a large country can cover the territory of its neighbours, and the neighbour's pixels there hold `0` rather than the no-data value. A mosaic therefore must not take "the first raster that has a value" or "the last one". The rule is:

```
count(lat, lng) = sum over all country rasters r of v_r   for every r where
                  (row, col) is inside r and v_r > -1e30
```

The valid values of all rasters that cover the pixel are **added**. Over foreign land a raster contributes `0`, so the sum equals the value of the country that actually has data there. A point that no raster covers has count `0`. Values are read as float32 and accumulated as float64, in ascending raster-header filename order. No longitude wrapping or global-index clamping is applied in pixel lookup; an index outside every raster contributes zero.

The mosaic must be built from the country files only. Adding continental or global files would add those totals on top of the country values.

### Raw counts as density

The sampled `count` is used as the density in MU per km^2 as it is. It is not divided by the area of the pixel (well under 1 km^2 at mid-latitudes), and no unit conversion is applied.

### Citation and how to obtain it

Dataset citation:

Center for International Earth Science Information Network (CIESIN), Columbia University; International Food Policy Research Institute (IFPRI); The World Bank; and Centro Internacional de Agricultura Tropical (CIAT). 2011. *Global Rural-Urban Mapping Project, Version 1 (GRUMPv1): Population Count Grid*. Palisades, NY: NASA Socioeconomic Data and Applications Center (SEDAC). [doi:10.7927/H4VT1Q1H](https://doi.org/10.7927/H4VT1Q1H).

NASA's [dataset record](https://data.nasa.gov/dataset/global-rural-urban-mapping-project-version-1-grumpv1-population-count-grid) confirms the creators, title, year, SEDAC attribution and DOI. Use the Earthdata Search link above for downloads.

---

## 3. S2 geometry background

S2 is Google's library for indexing the sphere. Only the parts needed here are described. Everything is in double precision except the integer cell ids.

### Cube faces and the three coordinate systems

The sphere is projected onto the six faces of a cube centred at the origin. Face `f` in `0..5` is centred on the axes `+X, +Y, +Z, -X, -Y, -Z` respectively. On each face there are three coordinate systems:

| Name | Range | Meaning |
|---|---|---|
| `(u, v)` | `[-1, 1]` | position on the cube face (plane through the cube face, before warping) |
| `(s, t)` | `[0, 1]` | "cell-space" coordinates after a non-linear warp that makes cell sizes more uniform |
| `(i, j)` | `0 .. 2^30 - 1` | integer coordinates of the finest ("leaf", level 30) cells, `i = floor(2^30 * s)` |

The warp used by S2 is the **quadratic** projection:

```
st_to_uv(s) = (4*s*s - 1) / 3             if s >= 0.5
            = (1 - 4*(1 - s)^2) / 3       if s <  0.5

uv_to_st(u) = 0.5 * sqrt(1 + 3*u)         if u >= 0
            = 1 - 0.5 * sqrt(1 - 3*u)     if u <  0
```

(The 2011 Java source writes the same functions with `s` in `[-1, 1]`.)

### From a face position to a point on the sphere

```
face_uv_to_xyz(face, u, v):
  face 0: ( 1,  u,  v)
  face 1: (-u,  1,  v)
  face 2: (-u, -v,  1)
  face 3: (-1, -v, -u)
  face 4: ( v, -1, -u)
  face 5: ( v,  u, -1)
```

The result is a direction, not necessarily of unit length. Latitude and longitude follow from it without normalising:

```
lat = atan2(z, sqrt(x*x + y*y))
lng = atan2(y, x)
```

The inverse: the face is the axis with the largest absolute component, plus 3 if that component is negative. On an exact tie prefer Z over Y over X; then

```
face 0: u =  y/x   v =  z/x
face 1: u = -x/y   v =  z/y
face 2: u = -x/z   v = -y/z
face 3: u =  z/x   v =  y/x
face 4: u =  z/y   v = -x/y
face 5: u = -y/z   v = -x/z
```

A unit vector from a coordinate pair: `(cos(lat)*cos(lng), cos(lat)*sin(lng), sin(lat))` with `lat`, `lng` in radians, `radians = (E6 / 1e6) * pi / 180`.

### Cell ids

An S2 cell is a quadrilateral region of the sphere identified by a 64-bit unsigned integer:

```
bits 63..61   face (0..5)
bits 60..1    Hilbert-curve position, 2 bits per level, most significant level first
lowest set bit (a marker) at bit position 2*(30 - level)
```

For a cell at level `L` the id is `face << 61 | pos(L levels) << (61 - 2L) | 1 << (60 - 2L)`. Level 0 is a whole cube face; level 30 is a leaf cell (marker in bit 0). Properties used below:

```
lsb(id)      = id & -id                       lowest set bit
level(id)    = 30 - (index of lsb(id)) / 2
parent(id, L)= (id & -m) | m   with m = 1 << (2*(30 - L))
children(id) = id - lsb + (2*k + 1) * (lsb >> 2),  k = 0..3     (in ascending id order)
contains(a,b)= a - lsb(a) + 1 <= b <= a + lsb(a) - 1
```

The ids of the four children of a cell are in the order in which the Hilbert curve visits them, which is also ascending numeric order. The **token** of a cell is the id as 16 hexadecimal digits with trailing zeros removed (for example `47affd`).

### The Hilbert curve

The position of a leaf cell `(face, i, j)` is built level by level from the most significant bit down. Every cell has an orientation `o` in `0..3`; bit 0 of `o` means "i and j swapped", bit 1 means "bits inverted". The orientation of the face cell is `face & 1`. At each level take the next bit of `i` and of `j`, form `ij = (ibit << 1) | jbit`, look up the position `p` of that sub-cell along the curve, and update the orientation:

```
IJ_TO_POS[o][ij]:             o=0: 0 1 3 2    o=1: 0 3 1 2    o=2: 2 3 1 0    o=3: 2 1 3 0
POS_TO_IJ[o][p]  (inverse):   o=0: 0 1 3 2    o=1: 0 2 3 1    o=2: 3 2 0 1    o=3: 3 1 0 2
POS_TO_ORIENTATION_XOR[p]:    p=0: 1   p=1: 0   p=2: 0   p=3: 3

encode(face, i, j):
    o = face & 1;  pos = 0
    for k = 29 down to 0:
        p   = IJ_TO_POS[o][ ((i >> k) & 1) << 1 | ((j >> k) & 1) ]
        pos = (pos << 2) | p
        o   = o XOR POS_TO_ORIENTATION_XOR[p]
    return (face << 61) | (pos << 1) | 1

decode(id):                                   -> face, level, lower-left leaf coordinates
    face = id >> 61;  level = level(id)
    o = face & 1;  i = j = 0
    for k = 0 .. level-1:
        p  = (id >> (59 - 2*k)) & 3
        ij = POS_TO_IJ[o][p]
        i  = (i << 1) | (ij >> 1);  j = (j << 1) | (ij & 1)
        o  = o XOR POS_TO_ORIENTATION_XOR[p]
    i0 = i << (30 - level);  j0 = j << (30 - level)
```

`(i0, j0)` is the lower-left corner of the cell in leaf units; the cell is the square `[i0, i0 + sz) x [j0, j0 + sz)` with `sz = 2^(30 - level)`.

A point to a leaf cell: find `face`, `(u, v)` as above, then `i = clamp(floor(2^30 * uv_to_st(u)), 0, 2^30 - 1)` and the same for `j`, then `encode`.

### Cell centres and corners

For a cell with lower-left corner `(i0, j0)` and size `sz`:

```
s = (i0 + sz/2) / 2^30         t = (j0 + sz/2) / 2^30
u = st_to_uv(s)                v = st_to_uv(t)
centre = face_uv_to_xyz(face, u, v)           (then lat/lng via atan2 as above)

corner k=0..3: (i,j) = (i0, j0), (i0+sz, j0), (i0+sz, j0+sz), (i0, j0+sz)
               s = i / 2^30, t = j / 2^30, u = st_to_uv(s), v = st_to_uv(t)
               unit vector = normalise(face_uv_to_xyz(face, u, v))
```

All four edges of a cell are great-circle arcs (they lie in planes through the origin), so a cell is a convex spherical quadrilateral.

### Levels and sizes

Level `L` divides the sphere into `6 * 4^L` cells. The average area is the sphere area divided by that number; cells of one level vary in area by up to a factor of about 2.1.

| Level | Cells | Average area (R = 6371.01 km) | Typical edge | Role here |
|---|---|---|---|---|
| 6 | 24,576 | about 20,755 km^2 | about 140 km | region (regional minimum); coarsest level of a covering cell |
| 9 | 1,572,864 | about 324 km^2 | about 18 km | start level in the worked example (section 8) |
| 12 | 100,663,296 | about 5.07 km^2 | about 2.3 km | |
| 13 | 402,653,184 | about 1.267 km^2 | about 1.1 km | finest level of the covering |
| 15 | 6,442,450,944 | about 0.0792 km^2 | about 280 m | density sampling level |

A cell at level `L <= 15` contains `4^(15 - L)` level-15 cells.

### Vertex neighbours

For a leaf cell `c` and a level `L < 30`, `vertex_neighbors(c, L)` returns the cells of level `L` around the grid vertex of the level-`L` lattice that is closest to `c` (normally four cells, three if the vertex is a cube corner). With `(face, i, j)` the leaf coordinates of `c`:

```
half = 2^(30 - (L+1));   size = 2*half
if (i & half) != 0:  ioff = +size;  isame = (i + size) < 2^30
else:                ioff = -size;  isame = (i - size) >= 0
same for j -> joff, jsame

output, in this order:
  1. parent(c, L)
  2. parent(cell_at(face, i + ioff, j),        L)       (wrapped to the adjacent face if !isame)
  3. parent(cell_at(face, i,        j + joff), L)       (wrapped if !jsame)
  4. parent(cell_at(face, i + ioff, j + joff), L)       only if isame or jsame
```

When an offset leaves the face, the neighbouring leaf cell is found on the adjacent face: clamp the offset `(i, j)` to `[-1, 2^30]`, set `u = ((2*i + 1) - 2^30) / 2^30` and `v = ((2*j + 1) - 2^30) / 2^30` (the coordinates are used directly as `(u, v)`, as in the S2 sources), convert `face_uv_to_xyz(face, u, v)` to a point and find its adjacent face and new `(u, v)` using the inverse face formulas. For this wrapping operation only, use the linear inverse `s = (u+1)/2`, `t = (v+1)/2`, then clamp `floor(2^30*s)` and `floor(2^30*t)` to `0..2^30-1` and encode. Do not apply `uv_to_st` in this wrapping step. The order of the four results matters because it is the insertion order of the initial candidates in section 4.

---

## 4. The covering of the triangle

The covering decides which cells are sampled for density. Because the density of a cell applies to the whole cell, even a part of the cell far outside the triangle, a different covering gives a different MU.

The covering heuristic follows class `S2RegionCoverer` at [Java S2 commit c28f287b996c0cedc5516a0426fbd49f6c9611ec](https://github.com/google/s2-geometry-library-java/tree/c28f287b996c0cedc5516a0426fbd49f6c9611ec) (2011, Apache License 2.0). The shipped implementation ports its queue and refinement rules, but obtains the loop predicates, loop normalisation, cap bound and initial vertex neighbours from **s2geometry 0.14.0** (the C++ library Python bindings). Clipped-cell corners and density-grid decoding use **s2sphere 0.2.5**; the bulk interior-area path uses s2geometry corners (section 6). The geometry primitives are therefore not an unmodified execution of the 2011 Java library.

### Region and parameters

The region is the triangle as an S2 loop: the three unit vectors in order, normalised so that the loop encloses the smaller of the two regions it bounds (the loop is inverted if its area exceeds 2*pi). Each edge is the great-circle arc between its vertices. The result does not depend on the order or direction in which the vertices are given.

```
max_cells = 20     max_level = 13     min_level = 6     level_mod = 1
```

With `level_mod = 1` every cell has up to `4` children (`max_children_shift = 2`); the level-modulus rules of the original code (several levels per expansion step, rounding the start level to the modulus) never apply and are left out below.

`min_level = 6` is the level of the regions (section 7). It takes priority over `max_cells`: a cell coarser than level 6 is never part of the result, even if that makes the covering larger than 20 cells. `max_cells` limits only the refinement of cells that are already at level 6 or finer. The rules in which `min_level` appears are collected here and repeated at the steps they belong to:

1. **Start level.** The start level (below) is not raised to `min_level`. If it is between 1 and 5, the initial candidates are coarser than level 6; if it is 0, the six face cells are the initial candidates.
2. **Terminal flag.** A candidate is terminal only if its level is at least `min_level` (and it is at the maximum level or lies completely inside the triangle). A cell coarser than level 6 is never terminal, even when it lies completely inside the triangle.
3. **All-terminal shortcut.** The rule that sends a candidate itself to the result when all four of its children are terminal applies only to candidates of level 6 or finer.
4. **Main loop.** A candidate coarser than level 6 is always expanded, whatever the number of cells already in the result and the queue. The budget test applies only to candidates of level 6 or finer.
5. **Result.** Consequently no cell of the result is coarser than level 6. The final normalisation does not merge four siblings into a parent coarser than level 6.

Because of rules 2 and 4 the result of a large field is dominated by level-6 cells, and its size is not bounded by `max_cells` (the covering of the field in section 8 has 195 cells). A covering under which no cell coarser than level 6 would arise is not affected by the rules: small and medium fields give the same covering as without a minimum level.

### Region predicates

The coverer needs three region operations:

* `may_intersect(cell)`: true if the triangle and the cell have a common point. The original library may return true for a few non-intersecting cells; with an exact test the answer is the geometric one.
* `contains(cell)`: true if the cell lies completely inside the triangle.
* `cap_bound()`: a bounding cap (see below).

For ordinary convex triangles, clipping against the three inward half-spaces (section 6) describes geometric intersection, and testing all four corners describes containment. These tests are explanatory, not exact substitutes for the shipped S2 predicates: conservative bounds and robust boundary handling can affect candidate selection.

The exact primitive calls used by the shipped coverer are:

```python
import s2geometry as s2  # version 0.14.0
loop = s2.S2Loop([s2.S2LatLng.FromE6(lat, lng).ToPoint()
                  for lat, lng in points_e6])
loop.Normalize()
cap = loop.GetCapBound()
may_intersect = loop.MayIntersect(s2.S2Cell(cell_id))
contains = loop.Contains(s2.S2Cell(cell_id))
leaf = s2.S2CellId(cap.center())
    # Once the starting level is known:
initial_cells = leaf.GetVertexNeighbors(level)
```

A port that implements S2 itself must reproduce these primitives, including robust predicates and conservative bounds, from the [versioned S2 source](https://github.com/google/s2geometry/tree/v0.14.0/src/s2). In particular, `s2loop.cc`, `s2latlng_rect_bounder.cc`, `s2latlng_rect.cc`, `s2predicates.cc`, and `s2cell_id.cc` define boundary behaviour that the geometric outline below does not fully specify.

#### Bounding cap

The following is a geometric outline. For exact floating-point bounds use `loop.GetCapBound()` above, including S2's conservative rectangle expansion.

1. Compute the bounding latitude/longitude rectangle of the triangle: the latitude interval spans the latitudes of the vertices, extended where the interior of an edge reaches a latitude beyond its endpoints (for an edge with plane normal `n = a x b`, the extreme-latitude points of its great circle are `+m` and `-m` with `m = z_axis - (z_axis . n) n / |n|^2`; include a point if it lies strictly between `a` and `b` on the arc); the longitude interval is the shortest interval containing the vertex longitudes. A triangle containing a pole gets a latitude range up to the pole and the full longitude range.
2. Candidate cap A: axis = unit vector at the rectangle's centre (`lat = (lo + hi)/2`, `lng = centre of the longitude interval`); height `h_A` = largest `0.5 * |axis - corner|^2` over the four rectangle corners (a cap's "height" is `1 - cos(angular radius)`).
3. Candidate cap B: axis = north pole if `lat_lo + lat_hi >= 0`, else south pole; angular radius `pi/2 - lat_lo` (north) or `pi/2 + lat_hi` (south); height `h_B = 2 * sin^2(radius / 2)`. In S2 0.14.0 the pole radius is first multiplied by `1 + 2*epsilon`, where `epsilon = 2^-52`.
4. Use A if its longitude span is at most pi and `h_A < h_B`; otherwise use B.
5. The shipped coverer computes `a = acos(clamp(1 - h, -1, 1))`. Although `2 * asin(sqrt(h / 2))` is mathematically equivalent, it need not give the same floating-point start level near a boundary.

### Starting level

```
K     = 2*sqrt(2) / 3                       minimum-width constant of the quadratic projection
x     = K / (2 * a)
level = floor(log2(x))                      round DOWN; computed from the floating-point exponent
level = clamp(level, 0, 30)                 (level = 30 if 2*a <= 0)
level = min(level, max_level, 29)           = min(level, 13)
```

The result is not raised to `min_level`; the minimum level has no influence on this step. With `x = K / (2a)`: `level = 0` for `x < 2` (cap radius `a` above about 0.2357 rad, 1,500 km); `level = 1` to `5` for `2 <= x < 64` (`a` above `K/128`, about 0.00737 rad or 47 km); and `level >= 6` for smaller caps.

`level` is the finest level at which every cell is guaranteed to be at least as wide as the cap's diameter, so the cap contains at most one cell vertex. In the original Java code this is `S2Projections.MIN_WIDTH.getMaxLevel(2 * cap.angle().radians())`, with the derivative `sqrt(2)/3` of the width metric and `getMaxLevel(value) = floor(log2(2 * deriv / value))`. Rounding up instead of down starts one level too fine for some triangles and changes the result.

### Initial candidates

```
if max_cells >= 4 and level > 0:
    leaf = leaf cell containing the cap axis
    for c in vertex_neighbors(leaf, level):          # order as in section 3
        add_candidate(new_candidate(c))
else:
    for face in 0..5:
        add_candidate(new_candidate(face cell))
```

For all fields small enough to have `level > 0`, the start is the (usually four) level-`level` cells around the cell vertex nearest the cap centre. The six-face start applies only when the cap is so large that `level` is 0.

The start level is compared with 0, not with `min_level`. For `level` from 1 to 5 the initial candidates are cells coarser than level 6; they are not terminal (see below), so they are expanded level by level until level 6 is reached. For `level = 0` the six face cells are candidates, and `new_candidate` drops those that do not intersect the triangle. A field that lies on one cube face leaves a single face candidate.

### Candidates

A candidate holds a cell, a terminal flag, and the list of children that intersect the triangle.

```
new_candidate(cell):
    if not may_intersect(cell): return null
    terminal = false
    if cell.level >= min_level:
        terminal = (cell.level + 1 > max_level) or contains(cell)
    return {cell, terminal, children = []}
```

With `max_level = 13` and `min_level = 6`, cells of level 13 are terminal, and so is any cell of level 6 to 13 that lies completely inside the triangle. A cell of level 0 to 5 is never terminal, not even when it lies completely inside the triangle (`contains` is not evaluated for it): it is always subdivided, because a cell coarser than level 6 cannot be part of the result.

```
add_candidate(c):
    if c is null: return
    if c.terminal: result.append(c.cell); return
    # expand exactly one level (the same for cells coarser than min_level)
    num_terminals = 0
    for child in c.cell.children (ascending id order):
        cc = new_candidate(child)
        if cc != null:
            c.children.append(cc)
            if cc.terminal: num_terminals += 1
    if c.children is empty: return                       # nothing intersects: drop it
    if num_terminals == 4 and c.cell.level >= min_level: # all four children terminal
        c.terminal = true
        add_candidate(c)                                 # -> the parent goes to the result
    else:
        priority = -( (( (c.cell.level << 2) + len(c.children) ) << 2) + num_terminals )
        queue.add(entry(priority, c))
```

Candidates coarser than `min_level` take the same path as all others, with two consequences. Their children are created by `new_candidate`, so a child is terminal only if it is at level 6 or finer (the children of a level-5 candidate are the first that can be terminal, when they lie completely inside the triangle) and the children counts, terminal counts and priority are computed exactly as before. The all-terminal shortcut is skipped for them (`c.cell.level >= min_level` is false), because it would put a cell coarser than level 6 into the result; such a candidate always goes to the queue. For a candidate of level 6 or finer nothing changes.

### Priority

```
priority = -( ((level * 4 + n_children) * 4) + n_terminal_children )
```

where `level` is the candidate cell's level, `n_children` the number of its children that intersect the triangle (1..4), and `n_terminal_children` how many of those are terminal (0..4). The queue always returns the entry with the **highest** priority value first, which means: lower level (larger cells) first; at equal level fewer intersecting children first; then fewer terminal children first.

### Main loop

```
while queue not empty:
    c = queue.poll()                                     # highest priority
    if c.cell.level < min_level
       or len(c.children) == 1
       or len(result) + queue.size() + len(c.children) <= max_cells:
        for child in c.children (in stored order):
            add_candidate(child)
    else:
        c.terminal = true
        add_candidate(c)                                 # keep the coarse cell: result.append
```

`queue.size()` is evaluated after `c` has been removed. A candidate coarser than level 6 is always expanded; the budget is not consulted for it, so it can never be kept as a result cell. A candidate of level 6 or finer with a single intersecting child is always expanded. Otherwise it is expanded only if the cells that would then exist (already in the result, still waiting in the queue, and the children of `c`) fit within 20. If not, `c` itself is kept as a final, coarse cell.

Two properties follow for fields whose forced expansion fills the budget:

* The forced expansion of the coarse candidates puts cells into the result (terminal children) and into the queue (the other children). Once `len(result) + queue.size() + 2` exceeds 20, the budget test fails for every remaining candidate of level 6 or finer that has two or more children, and each of them is kept as it is, at its own level. Candidates with exactly one intersecting child are still expanded, one level per step, until a candidate with two or more children, or a terminal cell, is reached; this is how some boundary cells of a large field end up at levels 7 to 10.
* Nothing removes a cell once it is in the result, and `max_cells` limits only the optional refinement. The result therefore contains at least one cell inside every level-6 cell that the triangle intersects, can hold far more than 20 cells, and spans at most 24,576 regions (the number of level-6 cells on the sphere).

### The priority queue and ties

Many candidates have exactly the same priority (compare the table in section 8). Which of them is polled first decides which one is later kept as a coarse cell when the budget runs out, so tie behaviour is part of the algorithm. The Java code uses `java.util.PriorityQueue` with a comparator that compares only the priority value:

```
compare(x, y) = +1 if x.priority < y.priority
                -1 if x.priority > y.priority
                 0 otherwise
```

so the "smallest" element, which is removed first, is the one with the largest priority value. `PriorityQueue` is an array-based binary min-heap, and it is neither a stable queue nor ordered by insertion or cell id for equal elements. Equal entries come out in the order produced by the heap operations. To reproduce it, implement the heap exactly as follows (array `q`, size `n`, 0-based; `x` and `e` are entries):

```
add(x):                                    # "siftUp"
    k = n;  n += 1
    while k > 0:
        parent = (k - 1) >> 1;  e = q[parent]
        if compare(x, e) >= 0: break       # stop at an equal or smaller parent
        q[k] = e;  k = parent
    q[k] = x

poll():
    result = q[0]
    n -= 1;  x = q[n]                      # last element is moved to the root
    if n > 0:                              # "siftDown"
        k = 0;  half = n >> 1
        while k < half:
            child = 2*k + 1;  c = q[child];  right = child + 1
            if right < n and compare(c, q[right]) > 0:
                child = right;  c = q[child]      # take the right child only if strictly smaller
            if compare(x, c) <= 0: break          # stop at an equal or smaller child
            q[k] = c;  k = child
        q[k] = x
    return result
```

Points that must be replicated:

* the stopping tests are `>= 0` when sifting up and `<= 0` when sifting down, so comparisons stop on equality (the queue as a whole remains unstable);
* when sifting down, the left child is preferred unless the right child is strictly smaller;
* the last array element, not the next in insertion order, replaces the root on `poll`;
* the insertion order of equal entries is the order of `add_candidate` calls: first the initial candidates (vertex-neighbour order), then, after each poll, the expanded children in ascending id order, each of which may enqueue itself.

A FIFO queue, a LIFO queue, a stable sort, or ordering by cell id gives different results for equal priorities (see section 8 for an example in which the choice changes the final MU).

### Final normalisation

The cells in `result` are put through a cell-union normalisation, the same operation as the `S2CellUnion` constructor performs, with one restriction: four siblings are merged into their parent only if the parent is at level `min_level` or finer (with `level_mod = 1` there is no further expansion step):

```
sort the ids ascending (remove duplicates)
output = []
for id in ids:
    if output not empty and contains(output.last, id): continue         # already covered
    while output not empty and contains(id, output.last): pop output    # id covers earlier cells
    while len(output) >= 3 and level(id) > min_level:                   # parent level >= min_level
        # the last three outputs plus id are the four children of one parent?
        p = parent(id)
        if all(level(o) == level(id) and parent(o) == p for o in last three of output):
            drop the last three;  id = parent(id)
        else: break
    output.append(id)
```

The restriction keeps the result free of cells coarser than level 6: four level-6 siblings are never merged into a level-5 cell. (Merging without the restriction and then replacing every cell coarser than level 6 by its level-6 descendants gives the same list.) Face cells are excluded by the same test.

The result is the covering `C(T)`: a sorted list of disjoint cells of levels 6 to 13. Small and medium fields have mixed levels and usually fewer than 20 cells; large fields have many more, mostly level-6 cells.

### Why current S2 versions can give a different covering

The covering is not a mathematical property of the triangle; it is the output of a heuristic with a work budget. Current versions of the S2 library are not guaranteed to follow the 2011 heuristic: the way the initial candidate cells are chosen (a different starting set, or a different start level) and the way candidates of equal priority are ordered (an ordering by memory address, which the 2011 Java source comments mention for the original C++ code, is not reproducible at all) can differ. Either difference can change which candidates are still waiting when the budget of 20 cells is reached, and therefore which cells end up as coarse cells in the result. Since each cell's density is applied to the whole cell, a different cell set gives a different MU, by a few units for small fields and by more for fields whose coarse cells straddle strongly different densities. The reference refinement and heap behaviour used here follows the 2011 Java code, with the geometry primitives specified above; a re-implementation must reproduce that combination rather than call a current library's `GetCovering`.

---

## 5. Cell density

For a covering cell `C` of level `L` (`6 <= L <= 13`, section 4):

1. Enumerate **all** `4^(15 - L)` level-15 cells inside `C`: 16 for a level-13 cell, 64 for level 12, 256 for level 11, and so on, up to `4^9 = 262,144` for a level-6 cell.
2. For each of them compute the centre (section 3) as `(lat, lng)` in degrees.
3. Look up the raster value at the centre (section 2: shifted pixel, sum over rasters, `0` where nothing is valid).
4. `density(C)` is the plain arithmetic mean of those values.

Enumeration of the level-15 centres of a cell with lower-left corner `(i0, j0)` and level `L` on face `f`:

```
sz = 2^15            (size of a level-15 cell in leaf units)
n  = 2^(15 - L)
for a in 0..n-1:                          # outer loop
  for b in 0..n-1:                        # inner loop
    s = (i0 + a*sz + sz/2) / 2^30        t = (j0 + b*sz + sz/2) / 2^30
    u = st_to_uv(s)                      v = st_to_uv(t)
    (x, y, z) = face_uv_to_xyz(f, u, v)
    lat = degrees(atan2(z, sqrt(x*x + y*y)));   lng = degrees(atan2(y, x))
```

Accumulate the sampled values as float64 and divide by `n*n`; the shipped implementation uses NumPy's float64 `mean` (NumPy 2.5.4). Implementations with a different reduction order may differ in the last floating-point bits.

The samples are not weighted, are not restricted to the part of the cell inside the triangle, and are not taken only at the cell's own centre. The whole cell is sampled, whatever small fraction of it the triangle covers.

### Implementation note: precomputing level-6 densities

A large field has hundreds or thousands of level-6 covering cells (section 8), and each needs `262,144` samples. The sphere has 24,576 level-6 cells, so a table of all level-6 densities is small (24,576 float64 values, 192 KiB), but it covers `24,576 * 262,144 = 6,442,450,944` samples, every level-15 cell of the sphere, and is worth building once instead of sampling at request time. The same applies to the finer levels of the covering, whose tables grow by a factor of 4 per level (level 13: 402,653,184 cells).

A precomputed table gives bit-identical results only if every entry is computed as above: the same level-15 centres in the same order (outer loop `a`, inner loop `b`), the same raster lookup and the same reduction (the float64 mean of the contiguous sample vector of that cell). Deriving a cell's mean from the sums or means of its children, or from partial sums over larger tiles, is mathematically equal but changes the order of the floating-point additions and can differ in the last bits of the density. Each table entry must therefore be reduced directly from its own samples.

---

## 6. Overlap area

For each covering cell `C` the contribution needs `area(T, C)`, the spherical area of the intersection of the triangle and the cell. Both are bounded by great-circle arcs, and both are convex, so the intersection is a convex spherical polygon.

### Triangle half-spaces

With unit vectors `v0, v1, v2`:

```
c   = v0 + v1 + v2
n_k = v_k x v_(k+1 mod 3);   if not (n_k . c > 0):  n_k = -n_k         (k = 0, 1, 2)
```

A point `x` is inside the triangle if `n_k . x >= 0` for all three `k`. (This assumes the triangle is smaller than a hemisphere.)

### Clipping

Take the four corner unit vectors of the cell, in the order `k = 0..3` of section 3, as a polygon and clip it successively by `n_0`, `n_1`, `n_2` (Sutherland-Hodgman on the sphere):

```
clip(poly, n):
    out = []
    for each edge a -> b of poly (b is the next vertex, cyclically):
        da = n . a;   db = n . b
        if da >= 0: out.append(a)
        if (da >= 0) != (db >= 0):
            p = a + (b - a) * (da / (da - db))
            out.append( p / |p| )
    return out
```

If the polygon becomes empty, the overlap is `0`. Interpolating along the chord and normalising places the new vertex on the great-circle arc.

### Area

For the clipped polygon `p_0 .. p_(m-1)` (`m >= 3`), split it into the fan of triangles `(p_0, p_i, p_(i+1))` and add up the solid angle of each (Van Oosterom and Strackee):

```
omega(a, b, c) = 2 * atan2( | a . (b x c) | , 1 + a.b + b.c + c.a )

area_km2 = ( sum of omega over the fan ) * 6371.01^2
```

For coverings with at least 1,000 cells, the shipped implementation first obtains the four unit corner vectors of every cell from s2geometry 0.14.0. A cell is classified as entirely inside when all four corners have non-negative dot products with all three triangle normals (computed by NumPy matrix multiplication). Its area is then computed without clipping, using the same two-triangle fan formula with NumPy float64 vector operations (`sum` for dot products, `cross` and `arctan2`). Other cells follow the clipping procedure above with s2sphere corners. This bulk path can differ from scalar clipping in the last floating-point bits.

For `m < 3` the area is `0`. The sum of the overlaps of all covering cells equals the area of the triangle, up to rounding, because the covering cells are disjoint and cover the triangle. The contribution of the cell is `area_km2 * density(C)`; contributions are not rounded.

An earth radius of 6371.01 km is used; the mean radius 6371.0088 km, planar areas, Web Mercator areas and ellipsoidal areas give different values.

---

## 7. Regional minimum and final rounding

### Grouping

Every covering cell contributes `area_km2 * density(C)` to exactly one **region**, the level-6 S2 cell that contains it. Because no covering cell is coarser than level 6 (section 4), a covering cell lies completely inside one level-6 cell: for a level-6 cell that is the cell itself, for a finer cell it is its level-6 ancestor. Cells are never split among several regions, and no overlap threshold applies. The region exists because the covering cell exists, even if the computed overlap area is zero or extremely small.

```
region_sum[R] += area(T, C) * density(C)        for every covering cell C, R = ancestor(C, 6)
```

Initialise each region sum to float64 zero when its first covering cell is encountered. Process covering cells in ascending id order and add the final region values in ascending region id order, matching the shipped accumulation order.

Here `ancestor(C, 6) = C` for a cell of level 6. A region can receive several covering cells (the first example of section 8 has a region with nine); in the second example of section 8 every region receives exactly one.

### Minimum

```
region_value[R] = max(1, region_sum[R])
```

The minimum of 1 applies to each level-6 region that has an entry, not to each covering cell. A region that the field touches but with zero population still contributes `1`. A field whose covering cells lie in two regions therefore awards at least 2.

### Sum and rounding

```
total = sum over regions of region_value[R]
MU    = max(1, floor(total + 0.5))
```

The rounding happens once, on the total; regions are not rounded individually. It is "round half up" (Java's `Math.round` for non-negative values). Many languages round halves to even by default (for example Python's `round`), and must not be used here.

---

## 8. Worked example

Triangle (latitude, longitude in degrees; E6 integers in brackets):

```
A  52.324297, 10.182664   (52324297, 10182664)
B  52.244048, 10.167482   (52244048, 10167482)
C  52.295984, 10.231064   (52295984, 10231064)
```

The result is **3046 MU**. The following calculation applies the rules of sections 4 to 7.

### Step 1: unit vectors, triangle area

```
A = (0.6015646679308121, 0.10805066978352817, 0.7914827875934022)
B = (0.6026838364843697, 0.10808684945383003, 0.7906259711239105)
C = (0.6018580014895433, 0.1086282524941088,  0.7911806676120752)
spherical area of the triangle = 16.311625962717194 km^2 (R = 6371.01 km)
```

### Step 2: covering

Bounding rectangle: latitude 52.244048 .. 52.324297, longitude 10.167482 .. 10.231064 (the edge bulge does not exceed the vertex extremes at this precision). Cap A (rectangle centre): axis = (0.60207869, 0.10832317, 0.79105457), height `h = 3.0287e-7`, angular radius `a = 7.78296e-4` rad.

```
x     = K / (2a) = 0.9428090 / 0.00155659 = 605.69
level = floor(log2(605.69)) = floor(9.2424) = 9
```

The leaf cell at the cap axis is `47afffc2bd4433cb`. Its level-9 vertex neighbours, in order: `47affc`, `47a554`, `47b004`, `47baac`. These four are the initial candidates, all with priority `-148` (level 9, one intersecting child, no terminal child). The start level 9 is finer than `min_level = 6`, and every cell polled in the trace has level 9 to 12, so none of the minimum-level rules of this section takes effect: the trace and the covering are the same with and without the minimum level.

Queue trace (priority = `-(((level*4 + children)*4) + terminal children)`; "result before" is the result size before the cell is polled; "queue after" the queue size after the poll):

| # | Polled cell | Level | Priority | Children | Terminal children | Result before | Queue after | Action |
|---|---|---|---|---|---|---|---|---|
| 1 | `47affc` | 9 | -148 | 1 | 0 | 0 | 3 | expand |
| 2 | `47baac` | 9 | -148 | 1 | 0 | 0 | 3 | expand |
| 3 | `47a554` | 9 | -148 | 1 | 0 | 0 | 3 | expand |
| 4 | `47b004` | 9 | -148 | 1 | 0 | 0 | 3 | expand |
| 5 | `47a555` | 10 | -164 | 1 | 0 | 0 | 3 | expand |
| 6 | `47baab` | 10 | -164 | 1 | 0 | 0 | 3 | expand |
| 7 | `47b001` | 10 | -168 | 2 | 0 | 0 | 3 | expand |
| 8 | `47afff` | 10 | -168 | 2 | 0 | 0 | 4 | expand |
| 9 | `47b001c` | 11 | -180 | 1 | 0 | 0 | 5 | expand |
| 10 | `47a5554` | 11 | -180 | 1 | 0 | 0 | 5 | expand |
| 11 | `47affe4` | 11 | -180 | 1 | 0 | 0 | 5 | expand |
| 12 | `47baaac` | 11 | -180 | 1 | 0 | 0 | 5 | expand |
| 13 | `47b0004` | 11 | -184 | 2 | 0 | 0 | 5 | expand |
| 14 | `47afffc` | 11 | -192 | 4 | 0 | 0 | 6 | expand |
| 15 | `47afff9` | 12 | -197 | 1 | 1 | 2 | 7 | expand |
| 16 | `47b0003` | 12 | -202 | 2 | 2 | 3 | 6 | expand |
| 17 | `47baaab` | 12 | -202 | 2 | 2 | 5 | 5 | expand |
| 18 | `47b0001` | 12 | -202 | 2 | 2 | 7 | 4 | expand |
| 19 | `47affe3` | 12 | -207 | 3 | 3 | 9 | 3 | expand |
| 20 | `47b001d` | 12 | -207 | 3 | 3 | 12 | 2 | expand |
| 21 | `47afffb` | 12 | -207 | 3 | 3 | 15 | 1 | expand |
| 22 | `47a5555` | 12 | -207 | 3 | 3 | 18 | 0 | keep (18 + 0 + 3 > 20) |

The result of cell 14 includes two cells (`47afffd`, `47affff`) that lie entirely inside the triangle and went straight into the result as level-12 terminals. Steps 1 to 4 show ties: the four level-9 candidates all have priority -148 and leave the queue in the order `47affc`, `47baac`, `47a554`, `47b004`, which is neither insertion order nor id order but follows from the heap rules above (pushed order: `47affc`, `47a554`, `47b004`, `47baac`).

The last four polls (steps 19 to 22) tie at priority -207. The heap returns them in the order `47affe3`, `47b001d`, `47afffb`, `47a5555` (pushed in the order `47b001d`, `47a5555`, `47affe3`, `47afffb`). The first three still fit into the budget and are replaced by their three level-13 children each. For the last one the budget is exceeded (18 cells in the result plus 3 children is 21), so `47a5555` stays as a level-12 cell. The covering has 19 cells; normalisation changes nothing.

### Steps 3 to 5: cells, densities, overlaps, contributions

Cells sorted by id. "Samples" is the number of level-15 centres averaged. Numbers are rounded for display; the calculation uses full double precision.

| Cell token | Level | Samples | Overlap area (km^2) | Density | Contribution | Level-6 region |
|---|---|---|---|---|---|---|
| `47a5555` | 12 | 64 | 1.115324194 | 113.514419 | 126.605378 | `47a5` |
| `47affe24` | 13 | 16 | 0.007949411586 | 219.4737625 | 1.74468727 | `47af` |
| `47affe2c` | 13 | 16 | 0.9212071949 | 219.50037 | 202.20532 | `47af` |
| `47affe34` | 13 | 16 | 0.2944598427 | 219.4966764 | 64.6329568 | `47af` |
| `47afff94` | 13 | 16 | 0.0366537628 | 219.6704636 | 8.05174907 | `47af` |
| `47afffac` | 13 | 16 | 8.948665797e-07 | 219.5978546 | 0.000196510781 | `47af` |
| `47afffb4` | 13 | 16 | 0.7466252347 | 219.624649 | 163.977305 | `47af` |
| `47afffbc` | 13 | 16 | 0.5444138187 | 219.6502113 | 119.58061 | `47af` |
| `47afffd` | 12 | 64 | 4.583006978 | 211.8741232 | 971.020585 | `47af` |
| `47affff` | 12 | 64 | 3.678382323 | 211.9710822 | 779.710682 | `47af` |
| `47b00004` | 13 | 16 | 0.4157567082 | 145.5967634 | 60.5328311 | `47b1` |
| `47b0001c` | 13 | 16 | 0.5670646823 | 55.85966516 | 31.6760433 | `47b1` |
| `47b00024` | 13 | 16 | 0.718439957 | 52.567662 | 37.7667088 | `47b1` |
| `47b0002c` | 13 | 16 | 0.8698824984 | 164.408179 | 143.015798 | `47b1` |
| `47b001c4` | 13 | 16 | 0.008210712775 | 218.203023 | 1.79160235 | `47b1` |
| `47b001d4` | 13 | 16 | 1.021392274 | 209.0568979 | 213.5291 | `47b1` |
| `47b001dc` | 13 | 16 | 0.4100627442 | 219.4648962 | 89.9943776 | `47b1` |
| `47baaaac` | 13 | 16 | 0.2645160678 | 92.40697551 | 24.4431298 | `47bb` |
| `47baaab4` | 13 | 16 | 0.1082766624 | 52.15740728 | 5.64742998 | `47bb` |

The overlap areas sum to 16.31162596304 km^2, equal to the triangle area up to rounding.

### One density in detail

Cell `47afffac` (level 13, face 2, lower-left leaf coordinates `i0 = 101056512`, `j0 = 435683328`, cell size `2^17 = 131072`) has 16 level-15 centres. The first in enumeration order (`a = 0`, `b = 0`, shown in the last row of the geographically ordered table below):

```
s = (101056512 + 16384) / 2^30 = 0.0941314697265625
t = (435683328 + 16384) / 2^30 = 0.4057769775390625
u = st_to_uv(s) = -0.7607970588530103       (s < 0.5: (1 - 4*(1-s)^2) / 3)
v = st_to_uv(t) = -0.13746800056348243
face 2: (x, y, z) = (-u, -v, 1) = (0.7607970588530103, 0.13746800056348243, 1)
lat = atan2(1, hypot(0.76080, 0.13747)) = 52.291787 deg
lng = atan2(0.13747, 0.76080)            = 10.242232 deg
```

All sixteen centres, with the shifted pixel lookup (`col_global`, `row_global`) and the summed raster value (the raster of the country in which the cell lies holds the value; the other rasters whose extent includes the pixel hold `0`):

| lat | lng | col_global | row_global | count |
|---|---|---|---|---|
| 52.300517 | 10.234564 | 22827 | 4523 | 219.6274261 |
| 52.300209 | 10.238092 | 22828 | 4523 | 219.6274261 |
| 52.299901 | 10.241619 | 22828 | 4523 | 219.6274261 |
| 52.299592 | 10.245147 | 22828 | 4523 | 219.6274261 |
| 52.297915 | 10.233593 | 22827 | 4523 | 219.6274261 |
| 52.297607 | 10.237121 | 22827 | 4523 | 219.6274261 |
| 52.297299 | 10.240648 | 22828 | 4523 | 219.6274261 |
| 52.296991 | 10.244175 | 22828 | 4523 | 219.6274261 |
| 52.295314 | 10.232623 | 22827 | 4524 | 219.5682831 |
| 52.295005 | 10.236150 | 22827 | 4524 | 219.5682831 |
| 52.294697 | 10.239676 | 22828 | 4524 | 219.5682831 |
| 52.294389 | 10.243203 | 22828 | 4524 | 219.5682831 |
| 52.292712 | 10.231652 | 22827 | 4524 | 219.5682831 |
| 52.292404 | 10.235179 | 22827 | 4524 | 219.5682831 |
| 52.292096 | 10.238705 | 22828 | 4524 | 219.5682831 |
| 52.291787 | 10.242232 | 22828 | 4524 | 219.5682831 |

For the centre derived above (last row of the table): `col_global = floor((10.242232 - 0.0041667 + 180)/0.0083333) = 22828` (a plain lookup `floor((10.242232 + 180)/D)` would give `22829`), `row_global = floor((90 - (52.291787 + 0.0041667))/D) = 4524`. In the raster whose header is given in section 2 (`col_origin = 22200`, `row_origin = 4080`) this is local column 628, local row 444.

Mean of the 16 values: `density = 219.5978546142578`.

### Step 6: regions, minimum, rounding

| Region | Sum of contributions | After `max(1, .)` |
|---|---|---|
| `47a5` | 126.605378 | 126.605378 |
| `47af` | 2310.924092 | 2310.924092 |
| `47b1` | 578.306461 | 578.306461 |
| `47bb` | 30.090560 | 30.090560 |

```
total = 3045.9264910228035
MU    = max(1, floor(3045.9264910228035 + 0.5)) = 3046
```

No region needed the minimum here. For a field in an empty area, or one that merely touches a second region, the minimum of 1 per region dominates.

### Sensitivity of this example to the details of the covering

The same triangle and raster mosaic, with densities recomputed for each covering:

| Variation | Cell kept as coarse level-12 cell | MU |
|---|---|---|
| Specified method (start from cap vertex neighbours, Java heap ties) | `47a5555` | 3046 |
| Start level rounded up (level 10) instead of down (level 9) | `47b001d` | 3033 |
| Same start, LIFO ties or ascending cell-id ties | `47b001d` | 3033 |
| Same start, FIFO ties | `47afffb` | 3057 |
| Same start, descending cell-id ties | `47a5555` | 3046 |
| Start from the six faces instead of the cap | `47b001d` | 3033 |

The last four ties at priority -207 (steps 19 to 22) decide which of four candidates is kept as a coarse cell; each choice puts a different set of cells into the covering and gives a different MU. The minimum level does not change the MU or final covering in any row for this triangle. The cap-start variants poll only cells of level 9 or finer. The six-face variant starts at level 0 and also polls coarser cells; the mandatory expansion below level 6 leaves its final covering unchanged.

### Second example: a large field

Triangle:

```
A   -9.011934, 13.410663   (-9011934, 13410663)
B   22.905822, 33.272151   (22905822, 33272151)
C   -0.596665, 35.028782   (-596665, 35028782)
```

The result is **76,732,083 MU** (unrounded total 76,732,083.15944749). The calculation uses `min_level = 6`, with every density computed directly from its own level-15 samples. Only totals are listed; a per-cell table would have 195 rows.

| Quantity | Value |
|---|---|
| Spherical area of the triangle (R = 6371.01 km) | 3,335,091.41545603 km^2 (crosses the equator, entirely on cube face 0) |
| Bounding cap | height `h = 0.05593545`, angular radius `a = 0.33605009` rad (about 2,141 km) |
| `x = K / (2a)` and start level | `x = 1.40278`, `level = floor(log2(x)) = 0`: the six face cells are the initial candidates, only face 0 survives `new_candidate` |
| Queue polls | 198, of which 96 are candidates of level 0 to 5 (1, 2, 5, 8, 21, 59 at levels 0 to 5); all of them are expanded |
| Covering cells | 195: 183 at level 6, 7 at level 7, 2 at level 8, 2 at level 9, 1 at level 10 |
| Level-6 regions | 195, each with exactly one covering cell; the 12 cells of levels 7 to 10 come from level-6 candidates with a single intersecting child, which are always expanded |
| Level-15 samples | 48,473,088 in total; 262,144 for each level-6 cell, 4^9 |
| Cell densities | from 0.0166 to 1,260.72 |
| Sum of the overlap areas | 3,335,091.415456031 km^2, equal to the triangle area |
| Sum of `max(1, region_sum)` | 76,732,083.15944749 (no region is below 1, so the minimum adds nothing) |
| `floor(total + 0.5)` | 76,732,083 |

For comparison, the covering with `min_level = 0` has 20 cells (1 at level 3, 10 at level 4, 6 at level 5, 2 at level 6, 1 at level 7) and gives 73,584,003.10539615, i.e. 73,584,003 MU (see section 9).

---

## 9. Implementation pitfalls

Each item lists what goes wrong when the step is done differently.

* **Using a current S2 library's covering.** The initial cells and the ordering of equal-priority candidates can differ from the specified algorithm. The set of cells that carry density changes, and with it the MU (section 4).
* **Rounding the start level up.** `floor(log2(K / (2a)))` must round down. Rounding up starts one level too fine for some triangles and yields a different covering.
* **Breaking priority ties by insertion order, cell id or randomly.** Ties are common (several level-12 or level-13 candidates with equal child counts). The binary-heap behaviour, including its stopping conditions and the replacement of the root by the last array element, has to be reproduced exactly.
* **Starting from the six faces when `level > 0`.** The face start is the fallback only for very large caps.
* **Using `min_level = 0`.** The covering of a large field then keeps cells coarser than level 6 and stays near 20 cells. For the field of the second example in section 8 (3.3 million km^2) this gives 20 cells of levels 3 to 7 and 73,584,003 MU (with each coarse cell's overlap distributed over its level-6 descendants), instead of 195 cells and 76,732,083 MU: 3,148,080 MU (4.1 %) too little. Fields whose covering has no cell coarser than level 6, which includes small and medium fields, are not affected.
* **Treating `max_cells = 20` as a hard limit for large fields.** The minimum level overrides it: candidates coarser than level 6 are always expanded, and cells of level 6 or finer are kept whole once the budget is used up. Stopping at 20 cells, or subdividing a finished 20-cell covering down to level 6, gives a different set of cells and different densities.
* **Raising the start level to `min_level`.** The start level is not clamped. A field with start level 0 starts from the six faces, one with start level 1 to 5 from the four cells of that level; starting from four level-6 cells around the cap axis covers only part of a large field.
* **Letting a coarse candidate become terminal.** A cell coarser than level 6 is not terminal even if it lies completely inside the triangle, and the all-four-children-terminal shortcut does not apply to it. Otherwise cells coarser than level 6 enter the result.
* **Merging level-6 siblings into a level-5 parent in the final normalisation.** A merge is allowed only if the parent is at level 6 or finer.
* **Using a different bounding cap.** The cap is derived from the loop's latitude/longitude bounding rectangle (centre or pole axis, whichever gives the smaller cap). The minimum enclosing circle of the three vertices, the centroid or the circumcircle gives a different axis and angle, hence a different start cell and level.
* **Leaving out the final normalisation.** Without merging four sibling cells into their parent (and dropping contained cells), the cell list, and the cell densities used, can differ from the specified result.
* **Mixing up rasters.** Using the unadjusted counts (`up00g`), a density product, another year or another dataset yields different values nearly everywhere.
* **Dividing the count by the pixel area.** The raw count is the density. Dividing it by the pixel area changes every value.
* **Looking up the pixel that contains the point.** The lookup is shifted by half a pixel (north-west). Near the edges of populated areas a plain lookup picks a neighbouring pixel with a different count.
* **Letting a raster overwrite another.** Where country rasters overlap, a neighbour's `0` must not replace a positive value, and a no-data value must be skipped rather than added. Valid values are summed.
* **Including continent or global archives in the mosaic.** They duplicate the country data and, when summed, multiply the density.
* **Treating no-data as a large negative number in the sum.** Values at or below `-1e30` must be excluded before accumulating.
* **Sampling only the cell centre, or only the part of the cell inside the triangle.** The density is the unweighted mean over every level-15 centre of the entire cell.
* **Weighting the mean by the overlap or by the cell shape.** The mean is a plain average; each of the `4^(15-L)` centres counts equally.
* **Planar or ellipsoidal areas, or another radius.** The areas are spherical with R = 6371.01 km. A planar approximation, Web Mercator, WGS-84 ellipsoid areas or R = 6371.0088 km move results by amounts that are visible after rounding.
* **Approximating the cell/triangle intersection.** The cell edges are great circles, not lines of constant latitude/longitude and not straight lines in a map projection. Use the half-space clipping of section 6.
* **Applying the minimum of 1 to each covering cell, or only to the total.** The minimum applies per level-6 region, after summing the cells of that region and before the final rounding.
* **Rounding each region or each cell.** Only the total is rounded, once.
* **Python's `round`, or any round-half-to-even.** Use `floor(x + 0.5)`.
* **Ignoring regions with zero population.** A region that has covering cells contributes at least 1 regardless of its population.
* **Floating-point shortcuts.** Using single precision for the sums or for the unit vectors can change results, particularly for the tiny overlap areas of cells that the triangle only touches.

---

## 10. Known limitations and scope

* **Data vintage.** The population grid is from the year 2000. It is a count grid that is used as a density without any area normalisation. It does not describe current population.
* **Data licence.** Commercial use, non-free resale and redistribution require explicit written permission from the rights holders; attribution is required for derived products and services (section 2).
* **Whole-cell density.** The density is a property of the covering cell, not of the triangle. A triangle that overlaps a small part of a cell takes that cell's full density, including populated areas outside the triangle.
* **Dependence on the exact covering.** Because the covering is a budget-limited heuristic with ties, the results are sensitive to the exact algorithm (section 8). The heuristic follows the 2011 Java library with the geometry primitives and versions specified in section 4.
* **Numerically borderline cases.** Level selection uses `floor(log2(.))` of a floating-point value, region predicates compare cell edges with triangle edges, and the heap ties depend on exact equality of integer priorities. Triangles that fall within floating-point noise of such a boundary may be computed differently by implementations that differ in rounding, for example in the way the bounding rectangle or the cap is computed. Final rounding of an exact half-integer total is a matter of convention (half up is used).
* **Covering size and cost for large fields.** The minimum level 6 overrides `max_cells` (section 4), so the covering of a large field can have hundreds or thousands of cells across at most 24,576 level-6 regions; finer boundary cells can make the cell count exceed the region count. Each level-6 cell needs 262,144 density samples (section 5). Precompute the level-6 densities if many large fields are evaluated.
* **Poles and the antimeridian.** The description is the generic S2 procedure (bounding rectangle with pole handling, cube-face coordinates, face-wrap in the vertex-neighbour step). Special behaviour for triangles that contain a pole, cross the 180-degree meridian, or lie close to cube-face edges is not examined here beyond that.
* **Large fields.** The procedure is defined for any triangle smaller than a hemisphere. The second example of section 8 (3.3 million km^2, entirely within cube face 0) is computed with the rules of sections 4 to 7. Fields that cross cube-face edges or contain a pole at that size are covered only by the generic procedure of the previous item. For very large fields, those whose covering consists mainly of level-6 cells (often from a few hundred thousand km^2, depending on shape and position), the rules given here, in particular the minimum covering level 6, are likely but not confirmed to be correct in every case; individual results may differ from the value the game awards.
* **Degenerate input.** Triangles with two identical or collinear vertices, or antipodal vertices, are not addressed.

---

## 11. References

### Population data

* Center for International Earth Science Information Network (CIESIN), Columbia University; International Food Policy Research Institute (IFPRI); The World Bank; Centro Internacional de Agricultura Tropical (CIAT). 2011. *Global Rural-Urban Mapping Project, Version 1 (GRUMPv1): Population Count Grid.* Palisades, NY: NASA Socioeconomic Data and Applications Center (SEDAC). [doi:10.7927/H4VT1Q1H](https://doi.org/10.7927/H4VT1Q1H). [NASA metadata and use constraints](https://cmr.earthdata.nasa.gov/search/concepts/C3540929345-ESDIS.umm_json). [Earthdata Search download access](https://search.earthdata.nasa.gov/search/granules?p=C3540929345-ESDIS).
* NASA Earthdata (free registration, required for download): `https://urs.earthdata.nasa.gov/`.

### Prior work

* Gordon Ludlow. Reverse Engineering MU. `https://gordonludlow.com/ingress/reverse-engineering-mu/`. The basis on which this reconstruction was developed.

### S2 library and documentation

* Google S2 Geometry Library, Java, snapshot of 2011 used for the covering: `https://github.com/google/s2-geometry-library-java`, commit `c28f287b996c0cedc5516a0426fbd49f6c9611ec` (Apache License 2.0). Relevant sources: `S2RegionCoverer.java`, `S2CellId.java`, `S2CellUnion.java`, `S2Projections.java`, `S2Cap.java`, `S2Loop.java`, `S2LatLngRect.java`, `S2.java` (`Metric.getMaxLevel`).
* Google S2 Geometry Library (current C++ reference implementation): `https://github.com/google/s2geometry`.
* [S2 developer guide](https://s2geometry.io/devguide/) and [cell hierarchy and coordinate systems](https://s2geometry.io/devguide/s2cell_hierarchy.html).
* Van Oosterom, A. and Strackee, J. 1983. The solid angle of a plane triangle. *IEEE Transactions on Biomedical Engineering* BME-30(2), 125-126 (formula for the solid angle of a spherical triangle).
