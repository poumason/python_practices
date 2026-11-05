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

    # /admin/* 的管理權限驗證：兩種可以同時開，任一通過即可
    admin_api_key: str | None = None  # 給 CI/腳本用的靜態 key；留空就停用這個後門
    admin_user_ids: str = ""  # 逗號分隔的 user_id（SSO 的 sub）允許清單

    @property
    def admin_user_id_set(self) -> set[str]:
        return {uid.strip() for uid in self.admin_user_ids.split(",") if uid.strip()}


settings = Settings()
