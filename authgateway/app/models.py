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


class CreateClientResponse(BaseModel):
    client_id: str
    client_secret: str
    name: str


class AuthorizeResponse(BaseModel):
    principal_type: str
    principal_id: str
    agent_id: str
    permission: str
