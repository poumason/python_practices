from __future__ import annotations

import os
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader
from kubernetes import client, config
from kubernetes.client.rest import ApiException

DEFAULT_IMAGE = os.environ.get("DEFAULT_IMAGE", "python:3.12-slim")

TEMPLATES_DIR = Path(__file__).parent / "templates"
_jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))


class DeploymentNotFound(Exception):
    pass


def _load_k8s_config() -> None:
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()


def get_current_namespace() -> str:
    """Namespace this app is allowed to manage, matching its own RBAC Role."""
    env_namespace = os.environ.get("POD_NAMESPACE")
    if env_namespace:
        return env_namespace

    # local dev fallback: whatever namespace the active kubeconfig context points at
    try:
        _, active_context = config.list_kube_config_contexts()
        return active_context["context"].get("namespace", "default")
    except config.ConfigException:
        return "default"


def render_default_manifest(name: str, image: str, replicas: int, namespace: str) -> dict:
    template = _jinja_env.get_template("default_deployment.yaml.j2")
    rendered = template.render(name=name, image=image, replicas=replicas, namespace=namespace)
    return yaml.safe_load(rendered)


def create_deployment(manifest: dict, namespace: str) -> client.V1Deployment:
    _load_k8s_config()
    apps_v1 = client.AppsV1Api()
    return apps_v1.create_namespaced_deployment(namespace=namespace, body=manifest)


def delete_deployment(name: str, namespace: str) -> None:
    _load_k8s_config()
    apps_v1 = client.AppsV1Api()
    try:
        apps_v1.delete_namespaced_deployment(name=name, namespace=namespace)
    except ApiException as exc:
        if exc.status == 404:
            raise DeploymentNotFound(name) from exc
        raise
