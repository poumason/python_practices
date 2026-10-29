from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import close_pool, init_pool
from app.routes import clients, gateway, jwks, token, users


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    yield
    await close_pool()


app = FastAPI(title="AuthGateway", lifespan=lifespan)

app.include_router(token.router)
app.include_router(jwks.router)
app.include_router(clients.router)
app.include_router(users.router)
app.include_router(gateway.router)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
