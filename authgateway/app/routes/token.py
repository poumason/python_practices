from fastapi import APIRouter, Form, HTTPException

from app.db import get_pool
from app.models import TokenResponse
from app.security.jwt_utils import issue_system_token
from app.security.secrets_utils import verify_secret

router = APIRouter(tags=["oauth"])


@router.post("/oauth/token", response_model=TokenResponse)
async def token_endpoint(
    grant_type: str = Form(...),
    client_id: str = Form(...),
    client_secret: str = Form(...),
):
    if grant_type != "client_credentials":
        raise HTTPException(status_code=400, detail="unsupported_grant_type")

    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT client_secret_hash, status FROM clients WHERE client_id = $1", client_id
    )
    if row is None or row["status"] != "active" or not verify_secret(client_secret, row["client_secret_hash"]):
        raise HTTPException(status_code=401, detail="invalid_client")

    return issue_system_token(client_id)
