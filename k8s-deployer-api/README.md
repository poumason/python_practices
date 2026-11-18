# k8s Deployment Manager API

A FastAPI service that actually talks to the Kubernetes API: `POST /deployments`
creates a real Deployment and hands back its name, `DELETE /deployments/{name}`
removes it again. Comes with a Helm chart to deploy the API itself, including
the ServiceAccount/Role/RoleBinding it needs to be allowed to do that.

```
client --(POST /deployments)--> k8s-deployer-api --(k8s API, as its ServiceAccount)--> creates a Deployment
       <--(name, namespace, uid)--                  in the SAME namespace the API itself runs in
```

The API is only ever allowed to manage Deployments in its **own** namespace —
RBAC is `Role` + `RoleBinding`, not `ClusterRole`. There's no `namespace`
field in the request body on purpose.

## Layout

```
k8s-deployer-api/
├── app/
│   ├── main.py                       # FastAPI: POST /deployments, DELETE /deployments/{name}, /healthz
│   ├── k8s_client.py                 # k8s config loading + create/delete calls
│   ├── models.py                     # request/response schemas
│   └── templates/
│       └── default_deployment.yaml.j2  # default Deployment manifest (python:3.12-slim container)
├── Dockerfile
├── requirements.txt
└── helm/k8s-deployer-api/
    ├── Chart.yaml
    ├── values.yaml
    └── templates/
        ├── serviceaccount.yaml
        ├── role.yaml                # apps/deployments: get/list/create/delete/watch, namespace-scoped
        ├── rolebinding.yaml
        ├── deployment.yaml          # the API's own Deployment
        └── service.yaml
```

## API

### `POST /deployments`

```json
{
  "name": "my-demo",       // optional — auto-generated as demo-<8 hex chars> if omitted
  "image": "python:3.12-slim",  // optional — falls back to DEFAULT_IMAGE env var
  "replicas": 1              // optional, default 1
}
```

Renders `app/templates/default_deployment.yaml.j2` and calls
`AppsV1Api().create_namespaced_deployment(...)`. The default manifest's
container runs `python3 -m http.server 8000`, since a bare `python` image has
nothing to run on its own and would otherwise crash-loop.

Response:

```json
{"name": "my-demo", "namespace": "default", "uid": "...", "image": "python:3.12-slim", "replicas": 1}
```

### `DELETE /deployments/{name}`

Deletes that Deployment in the API's own namespace. Returns 404 if it doesn't
exist.

```json
{"name": "my-demo", "namespace": "default", "deleted": true}
```

## Run it locally against your current kubeconfig context

This talks to whatever cluster `kubectl config current-context` points at,
using whatever permissions that context already has — nothing in the Helm
chart's RBAC applies here, since you're not running inside the cluster.

```bash
cd k8s-deployer-api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
POD_NAMESPACE=default DEFAULT_IMAGE=python:3.12-slim uvicorn app.main:app --port 8010
```

```bash
curl -X POST http://localhost:8010/deployments -H "Content-Type: application/json" -d '{}'
kubectl get deploy -n default -l created-by=k8s-deployer-api

curl -X DELETE http://localhost:8010/deployments/<name-from-the-response>
kubectl get deploy -n default -l created-by=k8s-deployer-api   # gone
```

(`POD_NAMESPACE` mirrors what the Helm chart injects via the Downward API when
running in-cluster — see `app/k8s_client.get_current_namespace()`. Without it,
locally it falls back to the current kubeconfig context's namespace, or
`default`.)

## Deploy with Helm

```bash
docker build -t k8s-deployer-api:local .
helm install deployer ./helm/k8s-deployer-api --namespace demo --create-namespace
kubectl port-forward svc/deployer-k8s-deployer-api 8000:80 -n demo
```

```bash
curl -X POST http://localhost:8000/deployments -d '{}' -H "Content-Type: application/json"
```

`helm template`/`helm lint` both pass; `helm template` output shows the Role
is scoped to `demo` (the release namespace) and the Deployment's
`POD_NAMESPACE` env var comes from the Downward API (`metadata.namespace`),
so the pod always knows which namespace it's allowed to act in.

### Expose it via Ingress (for manually poking it from a browser)

Needs an ingress controller already running in the cluster (e.g. ingress-nginx)
and, if using `kind`, `extraPortMappings` for 80/443 in the kind config so the
host can actually reach it — `fastapi.localhost` resolves to `127.0.0.1` on
its own in modern browsers/`curl`, no `/etc/hosts` edit needed.

```bash
docker build -t k8s-deployer-api:local .
kind load docker-image k8s-deployer-api:local   # kind nodes can't see your local docker images otherwise

helm upgrade --install deployer ./helm/k8s-deployer-api \
  --namespace dev --create-namespace \
  --set ingress.enabled=true \
  --set image.repository=k8s-deployer-api --set image.tag=local
```

Then open `http://fastapi.localhost/docs` in a browser — FastAPI's built-in
Swagger UI — to call `POST /deployments` / `DELETE /deployments/{name}`
by hand. `ingress.host` in `values.yaml` controls the hostname if you want
something other than `fastapi.localhost`.

## RBAC notes

- `templates/role.yaml` only grants `get/list/create/delete/watch` on
  `apps/deployments`, scoped to `Release.Namespace`. No wildcards, no other
  resources, no `ClusterRole`.
- If you need this to manage Deployments across multiple namespaces, you'd
  swap `Role`/`RoleBinding` for `ClusterRole`/`ClusterRoleBinding` and let the
  request body specify a target namespace — not implemented here, since the
  example is deliberately kept to "manage my own namespace only".

## Cleanup

`helm uninstall deployer -n demo` removes the API itself (and its
ServiceAccount/Role/RoleBinding), but **not** any Deployments the API created
on your behalf — those are separate resources. Delete them yourself via
`DELETE /deployments/{name}` or `kubectl delete deploy -l created-by=k8s-deployer-api -n demo`
before uninstalling.
