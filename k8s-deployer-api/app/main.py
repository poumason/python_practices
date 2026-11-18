from __future__ import annotations

import uuid

from fastapi import FastAPI, HTTPException

from app import k8s_client
from app.models import CreateDeploymentRequest, CreateDeploymentResponse, DeleteDeploymentResponse

app = FastAPI(title="k8s-deployer-api")


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@app.post("/deployments", response_model=CreateDeploymentResponse)
async def create_deployment(request: CreateDeploymentRequest) -> CreateDeploymentResponse:
    namespace = k8s_client.get_current_namespace()
    name = request.name or f"demo-{uuid.uuid4().hex[:8]}"
    image = request.image or k8s_client.DEFAULT_IMAGE

    manifest = k8s_client.render_default_manifest(
        name=name, image=image, replicas=request.replicas, namespace=namespace
    )

    try:
        created = k8s_client.create_deployment(manifest, namespace)
    except Exception as exc:  # surface k8s API errors as 502 instead of a bare 500
        raise HTTPException(status_code=502, detail=f"failed to create deployment: {exc}") from exc

    return CreateDeploymentResponse(
        name=created.metadata.name,
        namespace=created.metadata.namespace,
        uid=created.metadata.uid,
        image=image,
        replicas=request.replicas,
    )


@app.delete("/deployments/{name}", response_model=DeleteDeploymentResponse)
async def delete_deployment(name: str) -> DeleteDeploymentResponse:
    namespace = k8s_client.get_current_namespace()

    try:
        k8s_client.delete_deployment(name, namespace)
    except k8s_client.DeploymentNotFound as exc:
        raise HTTPException(status_code=404, detail=f"deployment '{name}' not found in namespace '{namespace}'") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"failed to delete deployment: {exc}") from exc

    return DeleteDeploymentResponse(name=name, namespace=namespace, deleted=True)
