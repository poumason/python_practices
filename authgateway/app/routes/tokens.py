"""撤銷單一 access_token（用 jti），不用停用整個 client。"""
from fastapi import APIRouter, Depends

from app.auth.admin import require_admin
from app.config import settings
from app.db import get_pool

router = APIRouter(prefix="/admin/tokens", tags=["admin"], dependencies=[Depends(require_admin)])


@router.post("/{jti}/revoke")
async def revoke_token(jti: str):
    pool = get_pool()
    # 任何合法 token 本來最長也只活 ACCESS_TOKEN_TTL_SECONDS，撤銷紀錄沒必要留更久
    await pool.execute(
        """
        INSERT INTO revoked_jti (jti, expires_at)
        VALUES ($1, now() + ($2 || ' seconds')::interval)
        ON CONFLICT (jti) DO NOTHING
        """,
        jti,
        str(settings.access_token_ttl_seconds),
    )
    return {"jti": jti, "status": "revoked"}
