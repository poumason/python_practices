-- 讓單一 access_token 可以被立刻撤銷，不用停用整個 client
CREATE TABLE IF NOT EXISTS revoked_jti (
    jti        text PRIMARY KEY,
    revoked_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL
);
