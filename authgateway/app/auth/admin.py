"""/admin/* 端點的管理權限驗證。兩種方式任一通過即可：
- X-Admin-Api-Key：給 CI/腳本用的靜態 key（沒設定 ADMIN_API_KEY 就停用這個後門）
- Authorization: Bearer <公司 SSO id_token>，sub 要在 ADMIN_USER_IDS 允許清單內
"""
import hmac

from fastapi import Header, HTTPException

from app.config import settings
from app.security.jwt_utils import AuthError, verify_company_id_token


async def require_admin(
    authorization: str | None = Header(default=None),
    x_admin_api_key: str | None = Header(default=None),
) -> str:
    if x_admin_api_key is not None:
        if settings.admin_api_key and hmac.compare_digest(x_admin_api_key, settings.admin_api_key):
            return "admin-api-key"
        raise HTTPException(status_code=401, detail="invalid admin api key")

    if authorization is not None and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        try:
            claims = await verify_company_id_token(token)
        except AuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

        user_id = claims["sub"]
        if user_id not in settings.admin_user_id_set:
            raise HTTPException(status_code=403, detail=f"{user_id} is not an admin")
        return user_id

    raise HTTPException(status_code=401, detail="missing admin credentials")
