# Ingress MU Calculator

Calculate Mind Units from three portal coordinates. This is an independent empirical reconstruction, not affiliated with or endorsed by Niantic. Results for very large fields (from a few hundred thousand km²) are likely but not confirmed to be correct in every case.

The model uses GRUMP v1 year-2000 UN-adjusted counts, historical 2011 S2 covering with minimum level 6, spherical overlap areas and a minimum of one MU per level-6 region. See [the method](docs/METHOD.md).

## Quick start

Use Docker with Linux containers:

```sh
cp .env.example .env
# Fill in Earthdata username and password in .env.
docker compose up --build
```

Create a free [NASA Earthdata account](https://urs.earthdata.nasa.gov/) and approve the SEDAC application under Applications > Authorized Apps. First startup downloads 232 country archives and extracts 234 raster pairs into the named `population` volume. The archives take about 260 MB and the extracted files about 3.2 GB. The repository and image contain no population rasters or derived density tables. Completed archives and extracted files are reused; interrupted archives restart. Extraction checks ZIP CRCs; every startup checks required file sizes. The container runs as non-root and publishes localhost port 8000.

```sh
docker compose run --rm mu calc "52.324297,10.182664" "52.244048,10.167482" "52.295984,10.231064"
```

Expected MU: **3046**. Startup prepares the configured density tables and checks this triangle before accepting requests. The listener (including `/health`) is unavailable until these steps finish. See [HTTPS deployment](deploy/README.md).

For development, use Linux Python 3.12 and `pip install -e .`. Set `GRUMP_DATA` to a directory containing `bil/`, then run `python -m mu_calculator serve`. Missing files are downloaded. Credentials come only from environment variables; Compose reads `.env`. `GRUMP_DIR` overrides the calculator's extracted-raster location, while startup checks completeness under `GRUMP_DATA`.

Download selected countries independently:

```sh
python -m mu_calculator.download --directory /data/grump lux mlt
```

The `s2geometry` wheel is published for x86-64 Linux and macOS only, so the image is built for `linux/amd64` (emulated on ARM hosts).

## API

Public base: `https://api.investigatexm.com`. Browser documentation and client: `https://mu.investigatexm.com`. Local base: `http://localhost:8000`.

Points are strings `"latitude,longitude"` or objects `{"lat":52.324297,"lng":10.182664}`. Exactly three distinct points must form a nonzero spherical triangle. Latitude is -90..90; longitude is -180..180. Coordinates round half-up to six decimal places before calculation.

`POST /getMU` accepts:

```json
{"coordinates":["52.324297,10.182664","52.244048,10.167482","52.295984,10.231064"]}
```

Equivalent GET:

```text
/getMU?c=52.324297,10.182664&c=52.244048,10.167482&c=52.295984,10.231064
```

Response:

```json
{
  "mu":3046,
  "area_km2":16.311625962717194,
  "coordinates":["52.324297, 10.182664","52.244048, 10.167482","52.295984, 10.231064"],
  "model":"grump2000-s2java2011-min6-l6min1"
}
```

Add `?detail=1` or JSON `"detail":true` for these additional fields:

- `raw_mu`: total before regional minimums.
- `regional_total_mu`: total after regional minimums, before rounding.
- `regions`: objects with `s2_token`, `raw_mu`, `minimum_applied_mu`.
- `cells`: objects with `s2_id` (decimal string), `s2_token`, `level`, `overlap_km2`, `density`, `raw_mu`.

The query flag overrides the body flag. False/0 disables detail.

`POST /getMUbulk` accepts:

```json
{
  "fields":[
    {"id":"field-1","coordinates":["52.324297,10.182664","52.244048,10.167482","52.295984,10.231064"]},
    ["0,0","0,0","0,0"]
  ],
  "detail":false
}
```

Response:

```json
{
  "count":2,
  "results":[
    {"index":0,"id":"field-1","ok":true,"mu":3046,"area_km2":16.311625962717194,"coordinates":["52.324297, 10.182664","52.244048, 10.167482","52.295984, 10.231064"]},
    {"index":1,"ok":false,"error":"The three coordinates must be distinct at six decimal places."}
  ],
  "model":"grump2000-s2java2011-min6-l6min1"
}
```

Order is preserved; `id` is echoed only when supplied. Successful items include normalized coordinates and requested detail fields. No batch sum is returned.

| Endpoint or rule | Behavior |
| --- | --- |
| `GET /health` | `{"ok":true,"rasters":234,"model":"grump2000-s2java2011-min6-l6min1"}` after startup self-test |
| `GET /` | JSON description, documentation links and model |
| `GET /docs` | Generated interactive API documentation |
| Request body | 32,768 bytes; 413 above this, including streamed bodies |
| Bulk | 1–50 fields; otherwise 400 |
| Field size | No size cap; every valid spherical triangle is accepted, within the request deadline |
| Request deadline | 20 seconds; single 504; bulk items get `ok:false,error:"deadline exceeded"` |
| Invalid JSON, shape or coordinates | Single 400; coordinate errors remain per-item in bulk |
| Unexpected failure | Generic 500 JSON error |
| CORS | Origin `*`; GET/POST/OPTIONS |
| Rate limiting | Enforce at reverse proxy/edge; return 429 with Retry-After |

Errors: `{"error":"message","model":"grump2000-s2java2011-min6-l6min1"}`.
Limits are configurable with `MU_BODY_LIMIT`, `MU_BULK_LIMIT` and `MU_TIME_BUDGET`. Configured precomputed densities are read from memory-mapped tables; other covering cells are sampled on demand with a per-mosaic cache flushed at 100,000 entries. Detail includes every covering cell and region, without truncation; enormous fields can produce several MB of JSON.

The minimum level takes precedence over the soft 20-cell covering budget. Cells below level 6 must be expanded even when the budget is exceeded; mandatory single-child refinement may continue beyond level 6.

### Density table lifecycle

After download, `serve`, `calc` and `build-tables` prepare missing or stale tables beside `bil/`. Run `python -m mu_calculator build-tables` to prepare them explicitly. No derived data are shipped in the repository or image.

`MU_TABLE_MAX_LEVEL` selects the highest precomputed S2 density level: an integer from 6 to 11, default 6. Levels 6 through the selected level are prepared before serving; other levels are sampled on demand with the existing bounded cache. Invalid values fail at startup. Level 6 is sufficient for correctness; this option changes preparation, disk use and cold request speed, not calculation results.

| Maximum level | Cumulative table size | Median time per field, side about 10 / 58 / 192 / 576 km |
|---:|---:|---:|
| 6 | 0.19 MiB | 55 / 140 / 652 / 714 ms |
| 7 | 0.94 MiB | 11 / 14 / 30 / 18 ms |
| 8 | 3.94 MiB | 11 / 15 / 16 / 9 ms |
| 9 | 15.94 MiB | 11 / 13 / 10 / 9 ms |
| 10 | 63.94 MiB | 11 / 12 / 10 / 9 ms |
| 11 | 255.94 MiB | 11 / 7 / 11 / 8 ms |

Sizes exclude NumPy headers and manifests (about 130 bytes per table and 0.4 KB per manifest). The times are medians of eight random fields per size on a six-core desktop, with the rasters in the operating system's page cache and the density cache cleared before each field; the spread between fields is of the same order as the differences between levels 8 and 11. Level 7 removes most of the cost, and levels above 8 add little. Reading rasters from cold storage is slower, and repeated requests in the same area are served from the density cache.

Raising the setting builds only the missing levels; existing tables are not rewritten. Lowering it leaves higher tables on disk but ignores them. Recreate the container after changing `.env` (`docker compose up -d --force-recreate`). Any build is one pass over the rasters that samples every level-15 cell once, so it takes about 9 to 10 minutes on six workers (measured: 9.0 minutes for level 6, 8.4 for levels 7-8, 9.8 for levels 8-11) whether it adds one level or several; slower machines and storage take longer. At level 11 allow about 268 MB for tables plus another 268 MB while a replacement is built; budget at least 5 GB for the population volume including rasters, archives and slack. Obsolete fingerprinted generations consume additional space and can be removed when no process uses them.

Each value uses its cell's level-15 samples in contiguous IJ order and the same NumPy float64 mean. A shared pass repacks raw samples into independent contiguous vectors; parent values are never reconstructed from child means. A SHA-256 fingerprint covers ordered raster names and contents, an explicit sampling/table semantics version and numerical dependency versions. Changes to sampling semantics require updating that version; comments and docstrings do not invalidate tables. Every manifest validates the level, layout version, shape, dtype, file size and content checksum. All raster files (about 3.2 GB) are read and hashed at every start; this is most of the start-up time when the tables exist (about 20 s in the test setup, which read the rasters through a WSL drive mount at about 210 MB/s; SHA-256 itself runs at about 1.4 GB/s). Builders hold an OS lock, bound pending work, reserve disk space for each table before writing, checkpoint verified parent tiles and publish each completed table and manifest by atomic rename. Interrupted builds resume from verified checkpoints; incomplete or stale tables are never served. Request serving uses one worker.

Build memory, measured with six workers at levels 6 to 11: each worker holds about 55 MiB of private memory and the parent process about 85 MiB, about 0.4 GiB in total at any setting, including the default. Every worker also memory-maps the rasters, so each shows up to 3 GiB resident and the proportional sizes add up to about 3.7 GiB. These are shared, clean file pages that the kernel can reclaim, not private allocations; on a host with less memory than the rasters the build is slower because pages are read again. The finished tables are memory-mapped as well (up to 256 MiB at level 11, file-backed) and are read in full when they are validated at start-up. `MU_TABLE_WORKERS` controls build parallelism (default up to six CPU cores) and thereby CPU use and about 55 MiB of private memory per worker; build time with fewer workers and behaviour under a container memory limit were not measured.

One calculation worker owns an in-process per-mosaic density cache. Deadlines include queue time. A running calculation may finish after its HTTP deadline; expired queued calculations are discarded before they start.

## Website

`site/` contains the static calculator, method, "How it works" and API pages published at `https://mu.investigatexm.com` through GitHub Pages. `python site/build.py` (requires `pip install markdown`) renders `docs/METHOD.md` into `site/_site/`. For local testing, serve that directory and open it with `?api=http://localhost:8000`.

The "How it works" page (`site/how-it-works.html`, `site/how-it-works.js`) shows five step-by-step animations on fixed example fields. Everything they show is computed by the calculator and committed as data files in `site/traces/`; the page makes no API calls. Regenerate the files after a change of the covering or calculation rules with `GRUMP_DIR=/path/to/bil python tools/export_traces.py` (Linux, needs the population rasters; `--check` compares with the committed files instead of writing). The export stops if an example no longer gives its expected MU. `tests/test_traces.py` checks the committed files without population data. The first animation contains a small excerpt of the population data (13 pixel values) with attribution; no other raster values are published.

## Tests

```sh
pip install pytest httpx
python -m pytest -q
GRUMP_DIR=/absolute/path/to/grump/bil python -m pytest -q
```

Tests cover parsing, rounding, heap ties, covering, spherical areas, mosaic sampling, regional minimums, API limits and deadlines. The optional raster test uses seven fixed triangles at varied scales and regions.

## Data and license

Code: [Apache-2.0](LICENSE). The covering logic follows the 2011 Google [s2-geometry-library-java](https://github.com/google/s2-geometry-library-java) S2RegionCoverer and Java priority queue ordering. See [NOTICE](NOTICE) for attribution and modifications.

Population data have separate terms and are not covered by the code license. The [NASA collection use constraints](https://cmr.earthdata.nasa.gov/search/concepts/C3540929345-ESDIS.umm_json) reserve copyright to Columbia University, IFPRI, The World Bank and CIAT; restrict commercial use, non-free resale and redistribution without explicit written permission; and require attribution for derived products and services. Consult those terms before use or redistribution. The calculator downloads data locally and does not serve raster files.

Citation: Center for International Earth Science Information Network (CIESIN), Columbia University; International Food Policy Research Institute (IFPRI); The World Bank; and Centro Internacional de Agricultura Tropical (CIAT). 2011. *Global Rural-Urban Mapping Project, Version 1 (GRUMPv1): Population Count Grid*. Palisades, NY: NASA Socioeconomic Data and Applications Center (SEDAC). [doi:10.7927/H4VT1Q1H](https://doi.org/10.7927/H4VT1Q1H).

The calculator uses year-2000 UN-adjusted 30 arc-second BIL country files.

### Animation orientation maps

The How it works page includes small, static vector orientation maps, embedded
in the built HTML without external tiles or map requests. Maps 1–3 contain
© OpenStreetMap contributors data under ODbL 1.0; maps 4–5 use Natural Earth
1:10m public-domain data. These map databases have their own licences, separately
from the calculator code. See [sources, licences and downloadable extracts](site/maps/README.md)
and [NOTICE](NOTICE). Urban outlines are orientation features, not the GRUMP
year-2000 counts. Regenerate with `python tools/extract_maps.py --cache /path/to/map-cache`
(optional extraction dependencies: `pyshp shapely`), then `python site/build.py`.
