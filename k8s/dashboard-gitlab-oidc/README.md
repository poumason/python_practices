# Kubernetes Dashboard with direct GitLab OIDC login + email-based RBAC

## Architecture

```
Browser → nginx ingress (auth-url) → dashboard-auth-injector ──OIDC check──► oauth2-proxy ──► GitLab.com
                                           │ add_header Authorization:
                                           │ Bearer <static token> (always, on any status)
                                           ▼
                             nginx auth-response-headers copies it through
                                           ▼
                             kubernetes-dashboard ──Bearer <static token>──► kube-apiserver
```

**Current design (as of 2026-09-30): a shared static token, not per-user RBAC.**
This started as a **no-Dex** variant of `../oidc_k8s/` that forwarded each
user's *own* GitLab ID token to kube-apiserver, so RBAC could tell
`poumason@live.com` apart from everyone else (see git history / the
`03-rbac.yaml` and `04-viewer-nodes-rbac.yaml` comments for that design). That
kept breaking because GitLab's ID token expires every ~10-12 minutes and the
forced re-login mid-session was disruptive enough that, after internal
discussion, we gave up per-user differentiation:

- `oauth2-proxy` is now purely a **login gate** — anyone on its email
  allowlist (`01-oauth2proxy.yaml`) can get in, nothing more.
- `dashboard-auth-injector` (`05-static-auth-injector.yaml`) sits between
  nginx and oauth2-proxy, re-checks the session against oauth2-proxy
  internally, and on success stamps a **fixed, non-expiring Kubernetes
  ServiceAccount token** onto the response instead of the user's own token.
  nginx's `auth-response-headers` (a plain annotation, not a snippet) copies
  that into the request forwarded to the Dashboard.
- Every allowed email now shares the exact same identity/permissions (bound
  to `cluster-admin` by default) — `03-rbac.yaml` / `04-viewer-nodes-rbac.yaml`
  are left in place but unused by this path.

This exists specifically because the company's ingress-nginx has
`configuration-snippet` disabled by policy, which is the usual way people do
this kind of static-token injection — `dashboard-auth-injector` is a plain
Deployment/ConfigMap/Service, not an Ingress annotation, so it isn't subject
to that admission-webhook restriction at all.

---

## Prerequisites

- `kind`, `kubectl`, `helm` installed
- A GitLab OAuth application created at https://gitlab.com/-/profile/applications
  - **Redirect URI**: `https://kubedashboard.localhost/oauth2/callback`
  - **Scopes**: `openid`, `profile`, `email`
- `/etc/hosts` entry:
  ```
  127.0.0.1  kubedashboard.localhost
  ```

---

## Step-by-step setup

### 1. Fill in the GitLab Application ID / Secret

- `00-kind-config.yaml` — replace `REPLACE_WITH_GITLAB_APPLICATION_ID` (`oidc-client-id`)
- `01-oauth2proxy.yaml` — replace `REPLACE_WITH_GITLAB_APPLICATION_ID` and
  `REPLACE_WITH_GITLAB_APPLICATION_SECRET` in the `oauth2-proxy-secret` Secret

Both must use the **same** GitLab Application ID: oauth2-proxy requests tokens
for that app, and kube-apiserver checks the token's `aud` claim against
`oidc-client-id` — they have to match.

Generate the cookie secret and fill it in too:
```bash
python3 -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(16)).decode())"
```

Also generate the Redis password for `01-redis.yaml`'s `redis-secret`:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(24))"
```

### 2. Point kube-apiserver at GitLab's OIDC issuer

**Option A — local kind cluster (new):**
```bash
kind create cluster --name gitlab-oidc-demo --config k8s/dashboard-gitlab-oidc/00-kind-config.yaml
```
`00-kind-config.yaml` is kind-specific (it's consumed by `kind create cluster
--config`) — skip it entirely for a kubeadm cluster, it has nothing to do
with kubeadm.

**Option B — kubeadm cluster (e.g. company private k8s), already running:**

kind's control plane is itself just kubeadm running in a container, so the
same static-pod-editing technique works. On **each** control-plane node:
```bash
sudo vi /etc/kubernetes/manifests/kube-apiserver.yaml
# add these 3 lines into spec.containers[0].command (alongside the flags
# already there — do not remove anything). See kube-apiserver.example.yaml
# in this directory for what a full kubeadm-generated manifest looks like
# and exactly where these go:
#   - --oidc-issuer-url=https://gitlab.com
#   - --oidc-client-id=<GitLab Application ID>
#   - --oidc-username-claim=email
# kubelet watches this file and restarts the static pod automatically
# within ~20s of saving — no cluster restart, no kubectl apply.
```
If there are multiple control-plane nodes (HA), repeat this on every one of
them — each runs its own independent kube-apiserver static pod.

To stop a future `kubeadm upgrade` from wiping this out (upgrades can
regenerate the manifest from the cluster's stored config), also persist the
same 3 flags into the cluster's kubeadm ClusterConfiguration:
```bash
kubectl edit cm kubeadm-config -n kube-system
# under ClusterConfiguration.apiServer.extraArgs, add the same 3 keys/values
```

### 3. Install ingress-nginx (if not already running)

```bash
kubectl apply -f k8s/ingress/kind_deploy.yaml
kubectl -n ingress-nginx wait --for=condition=ready pod \
  -l app.kubernetes.io/component=controller --timeout=120s
```

### 4. Install Kubernetes Dashboard

```bash
helm repo add kubernetes-dashboard https://kubernetes.github.io/dashboard/
helm upgrade --install kubernetes-dashboard kubernetes-dashboard/kubernetes-dashboard \
  --create-namespace --namespace kubernetes-dashboard
```

### 5. Apply Redis, oauth2-proxy, the static-token injector, NetworkPolicy, ingress, and RBAC

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

### 6. Open the dashboard

Visit `https://kubedashboard.localhost` — you'll be redirected to GitLab to
log in. `poumason@live.com` gets full cluster-admin; any other email you add
to `authenticated-emails.txt` in `01-oauth2proxy.yaml` can log in and browse
read-only.

To add more admins, add another `User` subject to `dashboard-admin-binding`
in `03-rbac.yaml`. To add more viewers, add another line to
`authenticated-emails.txt` in `01-oauth2proxy.yaml`.

---

## Verifying RBAC without logging in

```bash
kubectl auth can-i --list --as=poumason@live.com
kubectl auth can-i --list --as=someone-else@example.com
```

---

## Known limitation: losing your place on a forced re-login

Dashboard is a hash-routed SPA (e.g. `.../#!/pod?namespace=foo`). The part of
the URL after `#` is never sent to any server by the browser — it's purely
client-side. So when a token expires mid-session and you F5 to trigger a
fresh oauth2-proxy → GitLab → oauth2-proxy login round-trip, none of
nginx/oauth2-proxy/GitLab can see or carry that hash through, and you land
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
| kube-apiserver fails to start after adding OIDC flags | Confirm `oidc-client-id` exactly matches the GitLab Application ID — GitLab checks the token's `aud` claim against it |
| oauth2-proxy: `failed to fetch OIDC configuration` | Check the pod has outbound internet access to reach `https://gitlab.com/.well-known/openid-configuration` |
| Dashboard shows blank / redirects to its own login page | `auth-response-headers: Authorization` missing or oauth2-proxy not returning `--set-authorization-header=true` — the dashboard needs the `Authorization` header forwarded through, not a redirect |
| Non-admin user gets 403 on view/list actions too | RBAC propagation can take a few seconds after applying `03-rbac.yaml`; also confirm the email is in both `authenticated-emails.txt` (to log in) and check `kubectl auth can-i --list --as=<email>` |
| Non-admin user can see pods/deployments/etc. fine but Dashboard's Nodes page is empty/forbidden | Expected — the built-in `view` ClusterRole doesn't cover cluster-scoped resources (`nodes`, `persistentvolumes`, `storageclasses`, ...). `04-viewer-nodes-rbac.yaml` adds `nodes` read access on top; if the same thing happens for PVs/StorageClasses, add another ClusterRole+Binding there following the same pattern |
| Non-admin user CAN create/delete resources | `dashboard-viewer-binding` was probably not applied, or another binding (e.g. from `../oidc_k8s/` or `../rbac-deployment.yaml`) is still active in the cluster — check `kubectl get clusterrolebindings` for stray bindings |
| GitLab redirects to wrong URL | Verify the GitLab OAuth app's Redirect URI is exactly `https://kubedashboard.localhost/oauth2/callback` |
| nginx logs `upstream sent too big header ... subrequest: "/oauth2/auth"` | The GitLab ID token in the `Authorization` header is bigger than nginx's default `proxy_buffer_size`. `02-ingress.yaml` already sets `proxy-buffer-size: "16k"` on `kubernetes-dashboard-ingress` — bump it to `32k` if the warning persists |
| oauth2-proxy: `dial tcp: lookup redis ... no such host` or `NOAUTH Authentication required` | `01-redis.yaml` wasn't applied yet, or `redis-secret`'s password wasn't filled in / doesn't match what oauth2-proxy is using — confirm `redis` pod is `Running` in `kubernetes-dashboard` namespace and `OAUTH2_PROXY_REDIS_PASSWORD` matches `redis-secret` |
| Logged-in session randomly 401s after ~10 min, page doesn't auto-redirect to login | `kubectl -n kube-system logs <kube-apiserver pod>` shows `oidc: token is expired`. GitLab's ID token only lives ~10-12m; `--cookie-refresh` was too close to that lifetime, leaving a gap where oauth2-proxy still says the session is fine (its own `/oauth2/auth` check keeps returning 202 — so nginx's `auth-signin` never fires, since from its point of view auth succeeded) but the stale token it forwards is already expired by the time it reaches kube-apiserver. Fixed by setting `--cookie-refresh=2m` in `01-oauth2proxy.yaml` so oauth2-proxy refreshes with more margin. This is a structural gap in the front-door-proxy + independent-backend-validation pattern — a tighter refresh interval shrinks the window a lot but can't fully guarantee it never happens; a manual page reload always clears it since that forces a fresh top-level auth check |
| oauth2-proxy: `Error redeeming code during OAuth2 callback: could not get claim "groups": failed to fetch claims from profile URL: ... unexpected status "401"` — login never completes | GitLab's ID token has no `groups` claim, so oauth2-proxy tries to fetch it from GitLab's profile/userinfo endpoint on every login and that call 401s. We don't use OIDC groups for RBAC anyway (email + built-in `system:authenticated`, see `03-rbac.yaml`), so `01-oauth2proxy.yaml` sets `--skip-claims-from-profile-url=true` to skip that lookup entirely |
| Logged in successfully but Dashboard shows 401 / no Authorization reaches it, even though `dashboard-auth-injector`'s logs show 202 from oauth2-proxy | nginx's `add_header` directive only decorates a specific status allowlist by default (200/201/204/206/301-304/307) — oauth2-proxy's successful `/oauth2/auth` response is **202**, which isn't on that list, so the header was silently dropped. `05-static-auth-injector.yaml`'s `add_header Authorization ... always;` fixes this — the `always` keyword is required, not optional. After editing the ConfigMap template, you must `kubectl -n kubernetes-dashboard rollout restart deploy/dashboard-auth-injector` — envsubst only renders the template once at container startup, so a running pod won't pick up a ConfigMap change on its own |
| `dashboard-auth-injector` or `oauth2-proxy` times out / connection refused when nginx tries to reach them, nothing wrong in their own logs | Your cluster enforces NetworkPolicy (common on kubeadm + Calico/Cilium) and once a pod is selected by any NetworkPolicy, only explicitly allowed traffic reaches it. `kind` doesn't run a NetworkPolicy controller at all, so this never surfaced in local testing. Apply `06-networkpolicy.yaml`, which allows the `ingress-nginx` namespace in to both pods (and oauth2-proxy in from `dashboard-auth-injector` too, for its internal re-check) — if your ingress controller runs in a differently-named namespace, update the `namespaceSelector` there accordingly |
