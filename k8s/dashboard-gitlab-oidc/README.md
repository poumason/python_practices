# Kubernetes Dashboard with direct GitLab OIDC login + email-based RBAC

## Architecture

```
Browser → nginx ingress (auth-url/auth-signin) → oauth2-proxy ──OIDC──► GitLab.com
              │ auth-response-headers: Authorization
              │ (carries the logged-in user's own ID token)
              ▼
     kubernetes-dashboard ──Bearer <user ID token>──► kube-apiserver
                                                         (validates via --oidc-* flags,
                                                          maps `email` claim → RBAC User)
```

This is a **no-Dex** variant of `../oidc_k8s/`: GitLab.com is trusted directly as
the OIDC issuer by both `oauth2-proxy` and `kube-apiserver`, so there's no broker
pod and no self-signed TLS cert to manage.

Unlike `../oidc_k8s/04-ingress.yaml` and `../oauth2proxy-deployment.yaml`, this
setup does **not** inject one shared admin service-account token for every
user. Instead nginx forwards each user's *own* ID token to the dashboard,
which forwards it to kube-apiserver — so RBAC (`03-rbac.yaml`) can tell
`poumason@live.com` apart from everyone else and give them different access.

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

### 5. Apply Redis, oauth2-proxy, ingress, and RBAC

```bash
kubectl apply -f k8s/dashboard-gitlab-oidc/01-redis.yaml
kubectl apply -f k8s/dashboard-gitlab-oidc/01-oauth2proxy.yaml
kubectl apply -f k8s/dashboard-gitlab-oidc/02-ingress.yaml
kubectl apply -f k8s/dashboard-gitlab-oidc/03-rbac.yaml
```

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

## Troubleshooting

| Symptom | Fix |
|---|---|
| kube-apiserver fails to start after adding OIDC flags | Confirm `oidc-client-id` exactly matches the GitLab Application ID — GitLab checks the token's `aud` claim against it |
| oauth2-proxy: `failed to fetch OIDC configuration` | Check the pod has outbound internet access to reach `https://gitlab.com/.well-known/openid-configuration` |
| Dashboard shows blank / redirects to its own login page | `auth-response-headers: Authorization` missing or oauth2-proxy not returning `--set-authorization-header=true` — the dashboard needs the `Authorization` header forwarded through, not a redirect |
| Non-admin user gets 403 on view/list actions too | RBAC propagation can take a few seconds after applying `03-rbac.yaml`; also confirm the email is in both `authenticated-emails.txt` (to log in) and check `kubectl auth can-i --list --as=<email>` |
| Non-admin user CAN create/delete resources | `dashboard-viewer-binding` was probably not applied, or another binding (e.g. from `../oidc_k8s/` or `../rbac-deployment.yaml`) is still active in the cluster — check `kubectl get clusterrolebindings` for stray bindings |
| GitLab redirects to wrong URL | Verify the GitLab OAuth app's Redirect URI is exactly `https://kubedashboard.localhost/oauth2/callback` |
| nginx logs `upstream sent too big header ... subrequest: "/oauth2/auth"` | The GitLab ID token in the `Authorization` header is bigger than nginx's default `proxy_buffer_size`. `02-ingress.yaml` already sets `proxy-buffer-size: "16k"` on `kubernetes-dashboard-ingress` — bump it to `32k` if the warning persists |
| oauth2-proxy: `dial tcp: lookup redis ... no such host` or `NOAUTH Authentication required` | `01-redis.yaml` wasn't applied yet, or `redis-secret`'s password wasn't filled in / doesn't match what oauth2-proxy is using — confirm `redis` pod is `Running` in `kubernetes-dashboard` namespace and `OAUTH2_PROXY_REDIS_PASSWORD` matches `redis-secret` |
