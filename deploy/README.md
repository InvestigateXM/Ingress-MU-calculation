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
