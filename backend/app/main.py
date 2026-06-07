from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.logging import setup_logging
from app.api.routers import (
    health, sources, ingest, articles, enrich, cve, bulletin, feedback, search, chat, settings, entities
)
from app.services.scheduler import start_scheduler, stop_scheduler


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

app.include_router(health.router, prefix="/api")
app.include_router(sources.router, prefix="/api")
app.include_router(ingest.router, prefix="/api")
app.include_router(articles.router, prefix="/api")
app.include_router(enrich.router, prefix="/api")
app.include_router(cve.router, prefix="/api")
app.include_router(bulletin.router, prefix="/api")
app.include_router(feedback.router, prefix="/api")
app.include_router(search.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(entities.router, prefix="/api")
