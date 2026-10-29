"""Demo 用：直接幫 user 開一條對某個 agent 的授權，模擬管理員設定授權表。"""
from fastapi import APIRouter

from app.db import get_pool

router = APIRouter(prefix="/admin/users", tags=["admin"])


@router.post("/{user_id}/authorize-agent")
async def authorize_agent(user_id: str, agent_id: str, permission: str = "read"):
    pool = get_pool()
    await pool.execute(
        """
        INSERT INTO user_agent_auth (user_id, agent_id, permission)
        VALUES ($1, $2, $3)
        ON CONFLICT (user_id, agent_id) DO UPDATE SET permission = EXCLUDED.permission
        """,
        user_id,
        agent_id,
        permission,
    )
    return {"user_id": user_id, "agent_id": agent_id, "permission": permission}
