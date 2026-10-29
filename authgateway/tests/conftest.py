import asyncio
import os
import socket
import threading
import time
from pathlib import Path

import asyncpg
import httpx
import pytest
import pytest_asyncio
import uvicorn
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

MIGRATIONS_FILE = Path(__file__).parent.parent / "migrations" / "001_init.sql"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def mock_sso_server(tmp_path_factory):
    """跑一個真的 mock SSO HTTP server，讓 app 走真實的 JWKS 抓取與驗簽路徑。"""
    port = _free_port()
    issuer = f"http://127.0.0.1:{port}"
    os.environ["MOCK_SSO_ISSUER"] = issuer
    os.environ["MOCK_SSO_AUDIENCE"] = "authgateway"
    os.environ["MOCK_SSO_KEY_DIR"] = str(tmp_path_factory.mktemp("mock_sso_keys"))

    from mock_sso import main as mock_sso_main  # 延後 import，確保讀到上面設的 env

    config = uvicorn.Config(mock_sso_main.app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    for _ in range(100):
        try:
            httpx.get(f"{issuer}/.well-known/jwks.json", timeout=0.2)
            break
        except httpx.HTTPError:
            time.sleep(0.05)
    else:
        raise RuntimeError("mock SSO server did not start in time")

    yield issuer

    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="session")
def app_env(tmp_path_factory, mock_sso_server):
    key_dir = tmp_path_factory.mktemp("own_keys")
    private_path = key_dir / "private.pem"
    public_path = key_dir / "public.pem"

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )

    os.environ["DATABASE_URL"] = os.environ.get(
        "TEST_DATABASE_URL", "postgresql://authgateway:authgateway@localhost:5432/authgateway"
    )
    os.environ["SSO_ISSUER"] = mock_sso_server
    os.environ["SSO_JWKS_URL"] = f"{mock_sso_server}/.well-known/jwks.json"
    os.environ["SSO_AUDIENCE"] = "authgateway"
    os.environ["OWN_ISSUER"] = "http://testserver"
    os.environ["PRIVATE_KEY_PATH"] = str(private_path)
    os.environ["PUBLIC_KEY_PATH"] = str(public_path)
    os.environ["KEY_ID"] = "test-key-1"
    os.environ["ACCESS_TOKEN_TTL_SECONDS"] = "1800"
    return key_dir


@pytest.fixture(scope="session")
def migrated_db(app_env):
    """套用 migration，用自己獨立的 event loop 跑完就關掉，
    不留下任何跨 test 的 event-loop 綁定資源（asyncpg pool/connection 是 loop-bound 的）。"""

    async def _migrate():
        pool = await asyncpg.create_pool(os.environ["DATABASE_URL"])
        try:
            async with pool.acquire() as conn:
                await conn.execute(MIGRATIONS_FILE.read_text())
        finally:
            await pool.close()

    asyncio.run(_migrate())
    return True


@pytest_asyncio.fixture
async def test_app(migrated_db):
    """每個測試都重新開一個 pool，確保 pool 跟目前這個測試的 event loop 一致。"""
    from app.db import close_pool, init_pool
    from app.main import app

    await init_pool()
    yield app
    await close_pool()


@pytest_asyncio.fixture(autouse=True)
async def clean_db(test_app):
    from app.db import get_pool

    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE system_agent_auth, user_agent_auth, clients CASCADE")
    yield


@pytest_asyncio.fixture
async def client(test_app):
    transport = httpx.ASGITransport(app=test_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest_asyncio.fixture
async def id_token_factory(mock_sso_server):
    async def _get(username: str = "alice", password: str = "password123") -> str:
        async with httpx.AsyncClient() as c:
            resp = await c.post(f"{mock_sso_server}/mock-login", json={"username": username, "password": password})
            resp.raise_for_status()
            return resp.json()["id_token"]

    return _get
