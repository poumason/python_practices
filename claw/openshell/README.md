# Openshell

## Overwrite path
- /var/lib/rancher/k3s
  - agent
    - /var/lib/rancher/k3s/agent/etc/containerd
        - confing.toml
            - setting default pod first container, from `rancher/mirrored-pause:3.6`
  - server
    - /var/lib/rancher/k3s/server/static/charts

  - storage
- /opt/openshell
  - from build source to copy full charts and yaml files into the foler.
  - manifests
  - charts
  - gpu-manifests
- /etc/ranker/k3s
  - registries.yaml
    ```
    mirrors:
        "ghcr.io":
            endpoint:
            - "https://ghcr.io"
        "registry.k8s.io":
            endpoint:
            - "https://ghcr.io"
    ```
    - record registry host name and match target endpoint
