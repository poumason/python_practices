-- 讓 client 可以選擇用 private_key_jwt 取代 client_secret
ALTER TABLE clients ALTER COLUMN client_secret_hash DROP NOT NULL;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS public_key text;

-- JWT assertion 的 jti 用過一次就記下來，擋 replay
CREATE TABLE IF NOT EXISTS used_client_assertions (
    jti        text PRIMARY KEY,
    client_id  text NOT NULL REFERENCES clients(client_id),
    expires_at timestamptz NOT NULL
);
