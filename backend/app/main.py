from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import require_auth
from app.api.routers import (
    articles, bulletin, chat, cve, enrich, entities,
    feedback, health, ingest, search, settings, sources,
)
from app.api.routers import auth
from app.core.logging import setup_logging
from app.services.scheduler import start_scheduler, stop_scheduler

_auth = [Depends(require_auth)]


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    start_scheduler(app)
    yield
    stop_scheduler()


app = FastAPI(
    title="Wraith",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Public routes
app.include_router(health.router, prefix="/api")
app.include_router(auth.router,   prefix="/api")

# Protected routes
app.include_router(sources.router,  prefix="/api", dependencies=_auth)
app.include_router(ingest.router,   prefix="/api", dependencies=_auth)
app.include_router(articles.router, prefix="/api", dependencies=_auth)
app.include_router(enrich.router,   prefix="/api", dependencies=_auth)
app.include_router(cve.router,      prefix="/api", dependencies=_auth)
app.include_router(bulletin.router, prefix="/api", dependencies=_auth)
app.include_router(feedback.router, prefix="/api", dependencies=_auth)
app.include_router(search.router,   prefix="/api", dependencies=_auth)
app.include_router(chat.router,     prefix="/api", dependencies=_auth)
app.include_router(settings.router, prefix="/api", dependencies=_auth)
app.include_router(entities.router, prefix="/api", dependencies=_auth)
