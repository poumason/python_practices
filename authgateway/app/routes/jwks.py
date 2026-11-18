from fastapi import APIRouter
from cryptography.hazmat.primitives import serialization
from jwt.algorithms import RSAAlgorithm

from app.config import settings
from app.security.keys import load_own_keys

router = APIRouter(tags=["oauth"])


@router.get("/.well-known/jwks.json")
async def jwks():
    _, public_pem = load_own_keys()
    public_key = serialization.load_pem_public_key(public_pem.encode())
    jwk = RSAAlgorithm(RSAAlgorithm.SHA256).to_jwk(public_key, as_dict=True)
    jwk.update({"kid": settings.key_id, "use": "sig", "alg": "RS256"})
    return {"keys": [jwk]}
