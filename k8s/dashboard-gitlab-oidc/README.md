# Kubernetes Dashboard with Keycloak OIDC login + claim-based static-identity routing

> Directory name is a historical leftover from when this started as a
> GitLab-OIDC prototype (see `oidc_k8s/` and git history). The company's real
> identity provider is **Keycloak**; `01-oauth2proxy.yaml` points at it, not
> GitLab.

## Architecture

```
Browser → nginx ingress (auth-url) → dashboard-auth-injector ──/oauth2/auth──► oauth2-proxy ──OIDC──► Keycloak
                                           │ decodes the real ID token
                                           │ (email + dept_id claims) and
                                           │ picks ONE of three static
                                           │ ServiceAccount tokens
                                           ▼
                             nginx auth-response-headers copies it through
                                           ▼
                             kubernetes-dashboard ──Bearer <static token>──► kube-apiserver
```

**Current design (as of 2026-11): three shared static identities, chosen by
claims, not true per-user RBAC.** This started as a design that forwarded
each user's *own* OIDC ID token to kube-apiserver, so RBAC could tell
specific people apart (see git history / the `03-rbac.yaml` and
`04-viewer-nodes-rbac.yaml` comments for that earlier approach). That kept
breaking because the ID token expired every ~10-12 minutes and forced
re-logins mid-session were disruptive, so the company decided to trade away
true per-user RBAC for three fixed, non-expiring identities instead:

- `oauth2-proxy` is purely a **login gate** — anyone on the company email
  domain (`--email-domain`, `01-oauth2proxy.yaml`) can log in at all; it also
  puts the real Keycloak ID token on its `/oauth2/auth` response via
  `--set-authorization-header=true` so the injector can read it.
- `dashboard-auth-injector` (`05-static-auth-injector.yaml`) sits between
  nginx and oauth2-proxy. It re-checks the session against oauth2-proxy
  internally, decodes that real ID token's `email` and `dept_id` claims
  (no signature re-verification — oauth2-proxy already validated it; this is
  only reading claims to pick a tier), and stamps ONE of three fixed
  ServiceAccount tokens onto the response based on simple rules hard-coded as
  env vars in that file:
  - `ADMIN_EMAILS` (specific named people) → `cluster-admin`
  - `POD_OPERATOR_DEPT_IDS` (specific department IDs) → full CRUD + logs on
    pods, read-only on ingresses/services/deployments/statefulsets/
    replicasets/jobs/cronjobs/persistentvolumes
  - everyone else → get/list/watch + delete on pods only, nothing else
  nginx's `auth-response-headers` (a plain annotation, not a snippet) copies
  the chosen token into the request forwarded to the Dashboard.
- `03-rbac.yaml` / `04-viewer-nodes-rbac.yaml` (the earlier per-user-token
  design) are left in place but unused by this path.

This exists specifically because the company's ingress-nginx has
`configuration-snippet` disabled by policy, which is the usual way people do
static-token injection — `dashboard-auth-injector` is a plain
Deployment/ConfigMap/Service, not an Ingress annotation, so it isn't subject
to that admission-webhook restriction at all. Plain nginx config can't decode
a JWT or branch on a claim, though, so the injector is a small stdlib-only
Python script (no pip installs, no custom image build) rather than the
nginx+envsubst approach the single-static-token version used.

---

## Prerequisites

- `kind`, `kubectl`, `helm` installed
- A confidential client registered in the company's Keycloak realm
  - **Redirect URI**: `https://kubedashboard.localhost/oauth2/callback`
  - **Scopes**: `openid`, `profile`, `email`
  - A protocol mapper on this client (or realm) that puts a custom `dept_id`
    claim onto the issued ID token — confirm this is actually there before
    debugging anything else; `dashboard-auth-injector` has no fallback if
    it's missing, every request just falls through to the pod-deleter tier
- `/etc/hosts` entry:
  ```
  127.0.0.1  kubedashboard.localhost
  ```

---

## Step-by-step setup

### 1. Fill in the Keycloak client credentials

- `01-oauth2proxy.yaml`'s `oauth2-proxy-secret` Secret — replace
  `REPLACE_WITH_KEYCLOAK_CLIENT_ID` / `REPLACE_WITH_KEYCLOAK_CLIENT_SECRET`
  with the confidential client's credentials from Keycloak
- Same file's `--oidc-issuer-url` arg — replace
  `REPLACE_WITH_KEYCLOAK_REALM_ISSUER_URL` with the realm's issuer, e.g.
  `https://keycloak.company.internal/realms/<realm-name>`
- Same file's `--email-domain` arg — replace `REPLACE_WITH_COMPANY_DOMAIN`
  with the real company email domain (anyone with that domain can log in;
  `05-static-auth-injector.yaml` decides what they can actually do)

Generate the cookie secret and fill it in too:
```bash
python3 -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(16)).decode())"
```

Also generate the Redis password for `01-redis.yaml`'s `redis-secret`:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(24))"
```

### 2. Fill in the three permission tiers

In `05-static-auth-injector.yaml`'s `dashboard-auth-injector` Deployment:
- `ADMIN_EMAILS` — replace `REPLACE_WITH_COMPANY_DOMAIN` in each of the three
  example addresses with the real domain (must match the `email` claim
  exactly, case-insensitive)
- `POD_OPERATOR_DEPT_IDS` — comma-separated department IDs that should get
  the pod-operator tier (matched against the `dept_id` claim)

Everyone else who can log in at all (`--email-domain` above) automatically
gets the pod-deleter tier — there's nothing to configure for that, it's the
fallback in `pick_static_token()`.

### 3. (Not needed for this design) kube-apiserver OIDC flags

`00-kind-config.yaml` / `kube-apiserver.example.yaml` only matter for the
**earlier per-user-token design** (`03-rbac.yaml` /
`04-viewer-nodes-rbac.yaml`) — kube-apiserver never sees a user's real OIDC
token in the current static-identity design, only the fixed ServiceAccount
tokens from `05-static-auth-injector.yaml`, which it validates natively with
no extra flags needed. Skip this step entirely unless you're reverting to
that older design.

### 4. Install ingress-nginx (if not already running)

```bash
kubectl apply -f k8s/ingress/kind_deploy.yaml
kubectl -n ingress-nginx wait --for=condition=ready pod \
  -l app.kubernetes.io/component=controller --timeout=120s
```

### 5. Install Kubernetes Dashboard

```bash
helm repo add kubernetes-dashboard https://kubernetes.github.io/dashboard/
helm upgrade --install kubernetes-dashboard kubernetes-dashboard/kubernetes-dashboard \
  --create-namespace --namespace kubernetes-dashboard
```

### 6. Apply Redis, oauth2-proxy, the static-token injector, NetworkPolicy, ingress, and RBAC

```bash
kubectl apply -f k8s/dashboard-gitlab-oidc/01-redis.yaml
kubectl apply -f k8s/dashboard-gitlab-oidc/01-oauth2proxy.yaml
kubectl apply -f k8s/dashboard-gitlab-oidc/05-static-auth-injector.yaml
kubectl apply -f k8s/dashboard-gitlab-oidc/06-networkpolicy.yaml
kubectl apply -f k8s/dashboard-gitlab-oidc/02-ingress.yaml
kubectl apply -f k8s/dashboard-gitlab-oidc/03-rbac.yaml
kubectl apply -f k8s/dashboard-gitlab-oidc/04-viewer-nodes-rbac.yaml
```

`03-rbac.yaml` and `04-viewer-nodes-rbac.yaml` are no longer load-bearing
under the current static-token design (see Architecture above) — applying
them is harmless (nothing routes through per-user tokens to use them) and
keeps things ready in case this gets reverted later.

If your cluster enforces NetworkPolicy (common on a hardened kubeadm/Calico
or Cilium setup, unlike `kind` which doesn't run a NetworkPolicy controller
at all — this is why the gap wasn't caught in local testing), apply
`06-networkpolicy.yaml` too, or `oauth2-proxy` and `dashboard-auth-injector`
will be unreachable from the ingress controller with no obvious error beyond
a connection failure in nginx's logs.

### 7. Open the dashboard

Visit `https://kubedashboard.localhost` — you'll be redirected to Keycloak to
log in. Anyone on the company email domain can log in; which of the three
tiers they land in (admin / pod-operator / pod-deleter-only) is decided by
`dashboard-auth-injector` from their `email`/`dept_id` claims — see
Architecture above.

To add more admins, add their email to `ADMIN_EMAILS` in
`05-static-auth-injector.yaml`'s Deployment env and `kubectl apply` it — a
plain Deployment env change triggers a normal rollout on its own, no manual
restart needed. Same for adding department IDs to `POD_OPERATOR_DEPT_IDS`.
(This is different from editing `server.py` itself, which lives in a
ConfigMap — see the troubleshooting table below for why that one *does* need
a manual `rollout restart`.)

---

## Verifying permissions without logging in

There's no per-user `User` identity to pass to `--as` anymore — everyone
collapses onto one of the three ServiceAccounts. Check each tier directly:

```bash
kubectl auth can-i --list --as=system:serviceaccount:kubernetes-dashboard:dashboard-static-admin
kubectl auth can-i --list --as=system:serviceaccount:kubernetes-dashboard:dashboard-pod-operator
kubectl auth can-i --list --as=system:serviceaccount:kubernetes-dashboard:dashboard-pod-deleter
```

To check the *routing* logic itself (which tier a given email/dept_id lands
in) without a real Keycloak login, exec into the injector pod and hit it
with a hand-built fake session — or simpler, just read `pick_static_token()`
in `05-static-auth-injector.yaml`'s ConfigMap; it's a small, pure function
with no side effects.

---

## Known limitation: losing your place on a forced re-login

Dashboard is a hash-routed SPA (e.g. `.../#!/pod?namespace=foo`). The part of
the URL after `#` is never sent to any server by the browser — it's purely
client-side. So when a token expires mid-session and you F5 to trigger a
fresh oauth2-proxy → Keycloak → oauth2-proxy login round-trip, none of
nginx/oauth2-proxy/Keycloak can see or carry that hash through, and you land
back on the default route/namespace no matter what.

The only real fix is client-side JS injected into the page (e.g. via nginx
`sub_filter`, saving the hash to `sessionStorage` on change and restoring it
on load). That requires the `nginx.ingress.kubernetes.io/configuration-snippet`
annotation, which **is disabled by policy on the company's ingress-nginx** —
its admission webhook rejects the ingress outright ("Snippet directives are
disabled by the Ingress administrator"). A pod-level fix (patching Dashboard's
static `index.html` via a mounted ConfigMap, bypassing ingress entirely) is
possible but couples to Dashboard's internal file layout and needs
re-verifying on every Dashboard upgrade.

**Decision: leave this as-is.** `01-oauth2proxy.yaml`'s `--cookie-refresh=2m`
already makes forced re-logins rare; when one does happen, re-selecting the
namespace is a minor one-time inconvenience, not worth the added maintenance
cost of a pod-level HTML patch.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Dashboard shows blank / redirects to its own login page | `auth-response-headers: Authorization` missing on `kubernetes-dashboard-ingress`, or oauth2-proxy not returning `--set-authorization-header=true` — the dashboard needs the `Authorization` header forwarded through, not a redirect |
| oauth2-proxy: `dial tcp: lookup redis ... no such host` or `NOAUTH Authentication required` | `01-redis.yaml` wasn't applied yet, or `redis-secret`'s password wasn't filled in / doesn't match what oauth2-proxy is using — confirm `redis` pod is `Running` in `kubernetes-dashboard` namespace and `OAUTH2_PROXY_REDIS_PASSWORD` matches `redis-secret` |
| Logged in successfully but Dashboard shows 401 / no Authorization reaches it, even though `dashboard-auth-injector`'s logs show 202 from oauth2-proxy | Only applies to the earlier plain-nginx version of this file. Current version is a Python service and doesn't have this failure mode — if you still see it, you're running stale manifests; redeploy from the current `05-static-auth-injector.yaml` |
| `dashboard-auth-injector` or `oauth2-proxy` times out / connection refused when nginx tries to reach them, nothing wrong in their own logs | Your cluster enforces NetworkPolicy (common on kubeadm + Calico/Cilium) and once a pod is selected by any NetworkPolicy, only explicitly allowed traffic reaches it. `kind` doesn't run a NetworkPolicy controller at all, so this never surfaced in local testing. Apply `06-networkpolicy.yaml`, which allows the `ingress-nginx` namespace in to both pods (and oauth2-proxy in from `dashboard-auth-injector` too, for its internal re-check) — if your ingress controller runs in a differently-named namespace, update the `namespaceSelector` there accordingly |
| Everyone (even the named admins) only ever gets the pod-deleter tier | Check in order: (1) `--set-authorization-header=true` is present in `01-oauth2proxy.yaml` — without it oauth2-proxy never puts the real ID token on its `/oauth2/auth` response, so the injector has no claims to read and silently falls through to the default tier; (2) the Keycloak client actually has a protocol mapper emitting `dept_id` onto the **ID token** (not just the access token — some mapper configs only add a claim to one or the other); (3) `ADMIN_EMAILS` in `05-static-auth-injector.yaml` has the real domain filled in, not still `REPLACE_WITH_COMPANY_DOMAIN`; (4) the `email` claim's casing — matching is lowercased on both sides, but confirm Keycloak isn't sending something unexpected (e.g. a username instead of an email) by checking `dashboard-auth-injector`'s pod logs, which print the oauth2-proxy call's exceptions, or temporarily add a debug `print(claims)` to `server.py` in the ConfigMap |
| Edited `ADMIN_EMAILS`/`POD_OPERATOR_DEPT_IDS` in the Deployment and nothing changed | These are plain Deployment env vars, so `kubectl apply` alone should trigger a normal rollout — check `kubectl -n kubernetes-dashboard rollout status deploy/dashboard-auth-injector` actually completed. If instead you edited `server.py` inside the `dashboard-auth-injector-script` ConfigMap, that needs a manual `kubectl -n kubernetes-dashboard rollout restart deploy/dashboard-auth-injector` — editing a ConfigMap never triggers a rollout on its own, and the script is only read once at container start |
| Editing `05-static-auth-injector.yaml` and `kubectl apply` reports way fewer resources changed than expected (e.g. a `ClusterRoleBinding` just vanishes) | Every resource in a multi-doc YAML file needs a real `---` on its own line between it and the next — a comment banner like `# --- Tier 2 ---` is NOT a document separator. Without one, PyYAML/kubectl silently merges two resources into one mapping and keeps only the *last* value for any duplicate key (`kind`, `metadata`, ...), so the earlier resource just disappears with no error. Sanity-check after editing: `python3 -c "import yaml; print(len(list(yaml.safe_load_all(open('05-static-auth-injector.yaml')))))"` should match the number of resources you expect |
