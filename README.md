# Ingress MU Calculator

Calculate Mind Units from three portal coordinates. This is an independent empirical reconstruction, not affiliated with or endorsed by Niantic. Results for very large fields (roughly a million km² and more) are likely but not confirmed to be correct in every case.

The model uses GRUMP v1 year-2000 UN-adjusted counts, historical 2011 S2 covering with minimum level 6, spherical overlap areas and a minimum of one MU per level-6 region. See [the method](docs/METHOD.md).

## Quick start

Use Docker with Linux containers:

```sh
cp .env.example .env
# Fill in Earthdata username and password in .env.
docker compose up --build
```

Create a free [NASA Earthdata account](https://urs.earthdata.nasa.gov/) and approve the SEDAC application under Applications > Authorized Apps. First startup downloads 232 country archives and extracts 234 raster pairs into the named `population` volume. Allow several GB for archives and about 3.2 GB for extracted files. The repository and image contain no population rasters or derived density tables. Completed archives and extracted files are reused; interrupted archives restart. Extraction checks ZIP CRCs; every startup checks required file sizes. The container runs as non-root and publishes localhost port 8000.

```sh
docker compose run --rm mu calc "52.324297,10.182664" "52.244048,10.167482" "52.295984,10.231064"
```

Expected MU: **3046**. Startup builds a global level-6 density table and checks this triangle before accepting requests. The listener (including `/health`) is unavailable until these steps finish. See [HTTPS deployment](deploy/README.md).

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
| Field size | No size or density-sample cap; all valid spherical triangles are supported |
| Request deadline | 20 seconds; single 504; bulk items get `ok:false,error:"deadline exceeded"` |
| Invalid JSON, shape or coordinates | Single 400; coordinate errors remain per-item in bulk |
| Unexpected failure | Generic 500 JSON error |
| CORS | Origin `*`; GET/POST/OPTIONS |
| Rate limiting | Enforce at reverse proxy/edge; return 429 with Retry-After |

Errors: `{"error":"message","model":"grump2000-s2java2011-min6-l6min1"}`.
Limits are configurable with `MU_BODY_LIMIT`, `MU_BULK_LIMIT` and `MU_TIME_BUDGET`. `MU_MAX_SAMPLES` has been removed. Level-6 densities are read from a memory-mapped table; finer covering cells are sampled on demand with a per-mosaic cache flushed at 100,000 entries. Detail includes every covering cell and region, without truncation; enormous fields can produce several MB of JSON.

The minimum level takes precedence over the soft 20-cell covering budget. Cells below level 6 must be expanded even when the budget is exceeded; mandatory single-child refinement may continue beyond level 6.

### Density table lifecycle

After download, `serve`, `calc` and `build-tables` automatically build a missing or stale table beside `bil/`. Run `python -m mu_calculator build-tables` to prepare it explicitly. Allow roughly 8?10 minutes for table preparation on a six-worker desktop, plus download time; slower machines can take substantially longer. The global level-6 table has 24,576 float64 values (196,736 bytes including its NumPy header), plus a small JSON manifest and lock file. Allow additional space for one temporary table during rebuild; obsolete fingerprinted tables can be removed when no process uses them. No derived data are shipped in the repository or image.

Each value independently samples its cell's level-15 centers in contiguous IJ order and applies the original NumPy float64 mean. Parent values are never reconstructed from child means. A SHA-256 fingerprint covers ordered raster names and contents, sampling/reduction code and table version. Raster hashing runs at startup. Builders hold an OS lock, use bounded chunks and publish the finished table and manifest by atomic rename. Interrupted builds restart; an incomplete or stale table is never served. `MU_TABLE_WORKERS` controls build parallelism (default up to six CPU cores); request serving uses one worker.

One calculation worker owns an in-process per-mosaic density cache. Deadlines include queue time. A running calculation may finish after its HTTP deadline; expired queued calculations are discarded before they start.

## Website

`site/` contains the static calculator and method pages published at `https://mu.investigatexm.com` through GitHub Pages. `python site/build.py` (requires `pip install markdown`) renders `docs/METHOD.md` into `site/_site/`. For local testing, serve that directory and open it with `?api=http://localhost:8000`.

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
