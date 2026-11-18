from fastapi import APIRouter, Header, HTTPException

from app.audit import log_authorization
from app.auth.authorize import NotAuthorized, check_authorization
from app.auth.principal import resolve_principal
from app.models import AuthorizeResponse
from app.security.jwt_utils import AuthError

router = APIRouter(prefix="/v1", tags=["gateway"])


@router.get("/agents/{agent_id}/authorize", response_model=AuthorizeResponse)
async def authorize(agent_id: str, authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()

    try:
        principal = await resolve_principal(token)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    jti = principal.claims.get("jti")
    try:
        permission = await check_authorization(principal, agent_id)
    except NotAuthorized as exc:
        log_authorization(principal.type, principal.id, agent_id, jti, "denied")
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    log_authorization(principal.type, principal.id, agent_id, jti, "allowed")
    return AuthorizeResponse(
        principal_type=principal.type,
        principal_id=principal.id,
        agent_id=agent_id,
        permission=permission,
    )
