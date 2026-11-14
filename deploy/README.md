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

First start downloads the rasters and builds the global level-6 density table in
`population`, then checks the startup example. Allow roughly 8 to 10 minutes for
table preparation with six workers, plus download time; slower hosts need longer.
The HTTP listener and health check are unavailable until preparation completes.
Budget about 260 MB for archives, 3.2 GB for extracted rasters and less than 1 MB
for the density table and rebuild space. Derived tables stay in the volume and must not be included in an image.
Set `MU_TABLE_WORKERS` to reduce build CPU/memory usage (default up to six cores).
The table manifest fingerprints raster contents and sampling code; stale tables
are rebuilt automatically. Interrupted builds restart safely. `docker compose run
--rm mu build-tables` prepares the table without starting the API.

Field size has no sample cap. Detail responses include all cells and regions and
may be several MB. Keep proxy response limits large enough; bulk deadlines still
include the total time for all fields and queueing.
