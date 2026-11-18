"""user / system 共用的授權查詢骨架。"""
from app.auth.principal import Principal
from app.db import get_pool


class NotAuthorized(Exception):
    pass


async def check_authorization(principal: Principal, agent_id: str) -> str:
    pool = get_pool()

    if principal.type == "user":
        row = await pool.fetchrow(
            "SELECT permission FROM user_agent_auth WHERE user_id = $1 AND agent_id = $2",
            principal.id,
            agent_id,
        )
    elif principal.type == "system":
        row = await pool.fetchrow(
            "SELECT permission FROM system_agent_auth WHERE client_id = $1 AND agent_id = $2",
            principal.id,
            agent_id,
        )
    else:
        raise ValueError(f"unknown principal type: {principal.type}")

    if row is None:
        raise NotAuthorized(f"{principal.type} {principal.id} has no access to agent {agent_id}")

    return row["permission"]
