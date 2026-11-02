# Sidecar Header Proxy

Minimal example of the **sidecar proxy** pattern: two containers in one
Pod, where container **B** (the app) sends every outbound HTTP request
through container **A** (a sidecar), and A rewrites the `Authorization`
header before forwarding the request to the real external API.

```
B --(placeholder Authorization + X-Service-Id)--> A (localhost:8080)
                                                    │
                                                    ├─ look up real access token in DB
                                                    │  (container_a/db.py — stubbed here)
                                                    │
                                                    └─ forward to EXTERNAL_BASE_URL
                                                       with Authorization replaced
```

B never holds the real token. It only knows *which* identity to act as
(`X-Service-Id`), and A is the only thing that knows how to turn that
into a real credential.

## Layout

```
sidecar-header-proxy/
├── container_a/        # the sidecar proxy
│   ├── main.py          # FastAPI app: catch-all route, swaps the header, forwards
│   └── db.py            # stand-in DB lookup (service_id -> access token), with a TTL cache
├── container_b/        # the demo app
│   └── main.py          # calls out through container_a instead of the real API directly
├── Dockerfile           # shared image for both containers (different uvicorn command each)
├── docker-compose.yml   # run both containers locally, like two Pod containers
└── k8s/pod.yaml         # same two containers as an actual k8s Pod
```

## Run it locally with docker compose

```bash
cd sidecar-header-proxy
docker compose up --build
```

In another terminal:

```bash
curl http://localhost:8000/call-external
```

B sends a request with `Authorization: Bearer this-will-be-replaced` and
`X-Service-Id: order-service`. A looks up `order-service` in its fake
DB table, swaps in `Bearer token-for-order-service`, and forwards to
`https://httpbin.org/anything` (which echoes back the headers it
received). The response's `upstream_saw.headers.Authorization` shows the
*replaced* token, not the one B sent — that's the whole point.

## Run it as a real k8s Pod

```bash
docker build -t sidecar-header-proxy:local .
kubectl apply -f k8s/pod.yaml
kubectl port-forward pod/sidecar-header-proxy-demo 8000:8000
curl http://localhost:8000/call-external
```

Note `PROXY_BASE_URL` in `k8s/pod.yaml` is `http://localhost:8080`, not
a service name — both containers share the Pod's network namespace, so
there's no DNS lookup involved (unlike the compose version, where each
service is its own network namespace and B has to address A by service
name, `http://a:8080`).

## Adapting this to a real auth gateway

- `container_a/db.py` is an in-memory dict + `asyncio.sleep` standing in
  for a real DB call. Swap it for an async driver (`asyncpg`, etc.) or
  for a call into an existing authgateway service.
- `X-Service-Id` is just one way for B to tell A which identity to use;
  it could instead be a client ID B already sends, or a mTLS identity,
  depending on what you trust B to assert about itself.
- The TTL cache in `db.py` matters once this is real — don't hit the DB
  (or a token-issuing endpoint) on every single outbound request.
- Error handling here is minimal (401 on unknown service, nothing on
  upstream timeouts) — a real version should turn upstream failures
  into proper 502/504 responses instead of letting exceptions bubble up.
