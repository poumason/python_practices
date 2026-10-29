from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://authgateway:authgateway@localhost:5432/authgateway"

    sso_issuer: str = "http://localhost:9000"
    sso_jwks_url: str = "http://localhost:9000/.well-known/jwks.json"
    sso_audience: str = "authgateway"

    own_issuer: str = "http://localhost:8000"
    private_key_path: str = "./keys/private.pem"
    public_key_path: str = "./keys/public.pem"
    key_id: str = "authgateway-key-1"

    access_token_ttl_seconds: int = 1800


settings = Settings()
