from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import require_auth
from app.api.routers import (
    articles, bulletin, chat, cve, enrich, entities, export,
    feedback, health, ingest, investigations, search, searches, settings, sources,
)
from app.api.routers import auth
from app.core.logging import setup_logging
from app.services.scheduler import start_scheduler, stop_scheduler

_auth = [Depends(require_auth)]
_DEFAULT_SECRETS = {
    "change-me-in-production",
    "change-me-in-production-wraith-01",
    "change-me-use-a-long-random-string",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    import logging
    from app.core.config import settings as app_settings
    if (
        app_settings.SECRET_KEY in _DEFAULT_SECRETS
        or (app_settings.AUTH_USERNAME == "admin" and app_settings.AUTH_PASSWORD == "wraith")
    ):
        logging.getLogger("app").warning(
            "SECURITY: default credentials or SECRET_KEY detected — change them "
            "in .env before exposing this app beyond localhost."
        )
    if app_settings.SCHEDULER_ENABLED:
        start_scheduler(app)
    yield
    if app_settings.SCHEDULER_ENABLED:
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
app.include_router(searches.router,       prefix="/api", dependencies=_auth)
app.include_router(investigations.router, prefix="/api", dependencies=_auth)
app.include_router(export.router,         prefix="/api", dependencies=_auth)
