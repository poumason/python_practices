-- 人類（透過公司 SSO id_token）對 agent 的授權
CREATE TABLE IF NOT EXISTS user_agent_auth (
    user_id    text NOT NULL,
    agent_id   text NOT NULL,
    permission text NOT NULL DEFAULT 'read',
    PRIMARY KEY (user_id, agent_id)
);

-- 註冊的 system client（M2M 呼叫方）
CREATE TABLE IF NOT EXISTS clients (
    client_id          text PRIMARY KEY,
    client_secret_hash text NOT NULL,
    name                text,
    status              text NOT NULL DEFAULT 'active',  -- active | disabled
    created_at          timestamptz NOT NULL DEFAULT now()
);

-- system client 對 agent 的授權
CREATE TABLE IF NOT EXISTS system_agent_auth (
    client_id  text NOT NULL REFERENCES clients(client_id),
    agent_id   text NOT NULL,
    permission text NOT NULL DEFAULT 'read',
    PRIMARY KEY (client_id, agent_id)
);
