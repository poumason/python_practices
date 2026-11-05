from fastapi import APIRouter, Form, HTTPException

from app.db import get_pool
from app.models import TokenResponse
from app.security.client_assertion import CLIENT_ASSERTION_TYPE, verify_client_assertion
from app.security.jwt_utils import AuthError, issue_system_token
from app.security.secrets_utils import verify_secret

router = APIRouter(tags=["oauth"])


async def _authenticate_with_secret(client_id: str, client_secret: str) -> str:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT client_secret_hash, status FROM clients WHERE client_id = $1", client_id
    )
    if (
        row is None
        or row["client_secret_hash"] is None
        or row["status"] != "active"
        or not verify_secret(client_secret, row["client_secret_hash"])
    ):
        raise HTTPException(status_code=401, detail="invalid_client")
    return client_id


@router.post("/oauth/token", response_model=TokenResponse)
async def token_endpoint(
    grant_type: str = Form(...),
    client_id: str | None = Form(default=None),
    client_secret: str | None = Form(default=None),
    client_assertion_type: str | None = Form(default=None),
    client_assertion: str | None = Form(default=None),
):
    if grant_type != "client_credentials":
        raise HTTPException(status_code=400, detail="unsupported_grant_type")

    if client_assertion is not None:
        if client_assertion_type != CLIENT_ASSERTION_TYPE:
            raise HTTPException(status_code=400, detail="unsupported_client_assertion_type")
        try:
            authenticated_client_id = await verify_client_assertion(client_assertion)
        except AuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
    elif client_id is not None and client_secret is not None:
        authenticated_client_id = await _authenticate_with_secret(client_id, client_secret)
    else:
        raise HTTPException(status_code=400, detail="missing client credentials")

    return issue_system_token(authenticated_client_id)
