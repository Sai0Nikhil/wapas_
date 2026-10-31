from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import approvals, cases, dev, health, khata, webhooks
from app.db import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Wapas", version="0.1.0", lifespan=lifespan)
for r in (health.router, webhooks.router, cases.router, approvals.router, khata.router, dev.router):
    app.include_router(r)

