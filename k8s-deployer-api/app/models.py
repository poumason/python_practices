from __future__ import annotations

from pydantic import BaseModel, Field


class CreateDeploymentRequest(BaseModel):
    name: str | None = Field(default=None, description="Deployment name; auto-generated if omitted")
    image: str | None = Field(default=None, description="Container image; falls back to DEFAULT_IMAGE")
    replicas: int = Field(default=1, ge=1, le=10)


class CreateDeploymentResponse(BaseModel):
    name: str
    namespace: str
    uid: str
    image: str
    replicas: int


class DeleteDeploymentResponse(BaseModel):
    name: str
    namespace: str
    deleted: bool
