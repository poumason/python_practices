"""管理 system client：建立 / 停用。
Demo 用，正式環境應該加上管理權限驗證（例如只允許內部管理者的 id_token）。
"""
import secrets

from fastapi import APIRouter, HTTPException

from app.db import get_pool
from app.models import CreateClientRequest, CreateClientResponse
from app.security.secrets_utils import hash_secret

router = APIRouter(prefix="/admin/clients", tags=["admin"])


@router.post("", response_model=CreateClientResponse)
async def create_client(body: CreateClientRequest):
    client_id = f"client-{secrets.token_hex(6)}"
    client_secret = secrets.token_urlsafe(32)
    secret_hash = hash_secret(client_secret)

    pool = get_pool()
    await pool.execute(
        "INSERT INTO clients (client_id, client_secret_hash, name) VALUES ($1, $2, $3)",
        client_id,
        secret_hash,
        body.name,
    )

    # client_secret 只在這裡回傳一次，之後查不到明文
    return CreateClientResponse(client_id=client_id, client_secret=client_secret, name=body.name)


@router.post("/{client_id}/disable")
async def disable_client(client_id: str):
    pool = get_pool()
    result = await pool.execute(
        "UPDATE clients SET status = 'disabled' WHERE client_id = $1", client_id
    )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="client not found")
    return {"client_id": client_id, "status": "disabled"}


@router.post("/{client_id}/authorize-agent")
async def authorize_agent(client_id: str, agent_id: str, permission: str = "read"):
    """Demo 用：直接幫 client 開一條對某個 agent 的授權，模擬管理員設定授權表。"""
    pool = get_pool()
    client = await pool.fetchrow("SELECT client_id FROM clients WHERE client_id = $1", client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="client not found")

    await pool.execute(
        """
        INSERT INTO system_agent_auth (client_id, agent_id, permission)
        VALUES ($1, $2, $3)
        ON CONFLICT (client_id, agent_id) DO UPDATE SET permission = EXCLUDED.permission
        """,
        client_id,
        agent_id,
        permission,
    )
    return {"client_id": client_id, "agent_id": agent_id, "permission": permission}
