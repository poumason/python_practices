from pydantic import BaseModel


class TokenRequest(BaseModel):
    grant_type: str
    client_id: str
    client_secret: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int


class CreateClientRequest(BaseModel):
    name: str
    public_key: str | None = None  # 給了就走 private_key_jwt，不產生 client_secret


class CreateClientResponse(BaseModel):
    client_id: str
    client_secret: str | None = None  # 走 private_key_jwt 註冊時不會有這個欄位
    name: str
    auth_method: str  # "client_secret" | "private_key_jwt"


class AuthorizeResponse(BaseModel):
    principal_type: str
    principal_id: str
    agent_id: str
    permission: str
