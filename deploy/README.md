Run Caddy on the host with DNS pointing at it and ports 80/443 open:

```caddyfile
api.investigatexm.com {
    reverse_proxy 127.0.0.1:8000
}
```

Run `docker compose up -d --build`. Caddy obtains TLS certificates automatically.
The Compose port is bound to loopback. Enforce any public rate limits at your
reverse proxy or edge service; return 429 with Retry-After when throttling.
Allow at least 30 seconds for upstream responses. Keep credentials in `.env` locally.

First start downloads the rasters and prepares levels 6 through `MU_TABLE_MAX_LEVEL`
(integer 6-11, default 6) in `population`, then checks the startup example.
Level 6 is sufficient for correctness. Higher levels accelerate cold sampling.
Allow about 9 to 10 minutes for the build with six workers (any number of levels
takes one pass over the rasters), plus download time; slower hosts need longer.
Every start also reads and hashes the 3.2 GB of rasters (seconds on local disk,
about 20 s over a slow mount). The HTTP listener and health check
are unavailable until all configured tables are ready. Keep the initial health
check grace period generous (the image allows 180 minutes).

Budget at least 5 GB for the volume: about 260 MB of archives, 3.2 GB of rasters,
up to 268 MB of tables and another 268 MB for replacement, plus slack. Old
fingerprinted generations add further space. Derived tables stay in the volume.
Set `MU_TABLE_WORKERS` to reduce build CPU use (default 6 in `docker-compose.yml`; up to six cores otherwise). Private
build memory is about 55 MiB per worker plus about 85 MiB for the parent, at any
level. Workers also map the rasters, so process monitors show up to 3 GiB per
worker; these are shared, reclaimable file pages, not private memory. The mapped
tables (up to 256 MiB at level 11) are file-backed as well. See the main README
for the size and speed table and for what was not measured.

Manifests validate raster identity, explicit sampling version and file checksums.
The fingerprint upgrade rebuilds legacy level-6 tables once. Raising the setting
builds only missing levels; lowering it preserves but ignores higher tables.
Interrupted builds resume verified parent tiles. Run `docker compose run --rm mu
build-tables` with the same settings and volume to prepare without the API.
After changing `.env`, recreate with `docker compose up -d --force-recreate`.

Field size has no sample cap. Detail responses include all cells and regions and
may be several MB. Keep proxy response limits large enough; bulk deadlines still
include the total time for all fields and queueing.
