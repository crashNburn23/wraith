"""
Job state for ingest and enrichment runs.

In-memory dataclasses remain the hot-path working objects, but every mutation
is persisted to the job_runs / job_flags tables so state survives server
restarts (no more phantom RUNNING jobs after a uvicorn reload).
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
import threading

from app.db.base import new_uuid

_lock = threading.Lock()


@dataclass
class ArticleError:
    article_id: str
    title: str
    error: str


@dataclass
class SourceResult:
    name: str
    url: str
    status: str          # "ok" | "error"
    new_articles: int = 0
    duplicates: int = 0
    error: Optional[str] = None


@dataclass
class JobRun:
    job_type: str        # "ingest" | "enrich"
    status: str          # "running" | "paused" | "stopped" | "completed" | "error" | "interrupted"
    id: str = field(default_factory=new_uuid)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None

    # Enrich-specific
    total: int = 0
    processed: int = 0
    succeeded: int = 0
    failed: int = 0
    current_title: Optional[str] = None   # article being processed right now
    errors: list[ArticleError] = field(default_factory=list)

    # Ingest-specific
    source_results: list[SourceResult] = field(default_factory=list)

    def elapsed_seconds(self) -> float:
        end = self.finished_at or datetime.now(timezone.utc)
        started = self.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        return round((end - started).total_seconds(), 1)

    def to_dict(self) -> dict:
        d = {
            "job_type": self.job_type,
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "elapsed_seconds": self.elapsed_seconds(),
        }
        if self.job_type == "enrich":
            d.update({
                "total": self.total,
                "processed": self.processed,
                "succeeded": self.succeeded,
                "failed": self.failed,
                "current_title": self.current_title,
                "errors": [
                    {"article_id": e.article_id, "title": e.title, "error": e.error}
                    for e in self.errors[-20:]   # last 20 errors max
                ],
            })
        if self.job_type == "ingest":
            d["source_results"] = [
                {
                    "name": r.name,
                    "url": r.url,
                    "status": r.status,
                    "new_articles": r.new_articles,
                    "duplicates": r.duplicates,
                    "error": r.error,
                }
                for r in self.source_results
            ]
        return d


# In-memory mirror of the active run per job type (hot path)
_runs: dict[str, Optional[JobRun]] = {"ingest": None, "enrich": None}


# ─── Persistence helpers ──────────────────────────────────────────────────────

def _persist(run: JobRun) -> None:
    from app.db.session import SessionLocal
    from app.models import JobRunRecord
    with SessionLocal() as s:
        row = s.get(JobRunRecord, run.id)
        if not row:
            row = JobRunRecord(id=run.id, job_type=run.job_type, started_at=run.started_at)
            s.add(row)
        row.status = run.status
        row.finished_at = run.finished_at
        row.payload = run.to_dict()
        s.commit()


def _load_latest(job_type: str) -> Optional[JobRun]:
    """Reconstruct the most recent run from the DB after a restart.
    A row still marked 'running' means the process died mid-run — mark it interrupted."""
    from app.db.session import SessionLocal
    from app.models import JobRunRecord
    with SessionLocal() as s:
        row = (
            s.query(JobRunRecord)
            .filter(JobRunRecord.job_type == job_type)
            .order_by(JobRunRecord.started_at.desc())
            .first()
        )
        if not row:
            return None
        if row.status == "running":
            row.status = "interrupted"
            if row.payload:
                row.payload = {**row.payload, "status": "interrupted"}
            s.commit()
        p = row.payload or {}
        run = JobRun(job_type=job_type, status=row.status, id=row.id)
        run.started_at = row.started_at
        run.finished_at = row.finished_at
        run.total = p.get("total", 0)
        run.processed = p.get("processed", 0)
        run.succeeded = p.get("succeeded", 0)
        run.failed = p.get("failed", 0)
        run.current_title = None
        run.errors = [ArticleError(**e) for e in p.get("errors", [])]
        run.source_results = [SourceResult(**r) for r in p.get("source_results", [])]
        return run


def _get_flag_row(s, job_type: str):
    from app.models import JobFlag
    row = s.get(JobFlag, job_type)
    if not row:
        row = JobFlag(job_type=job_type, paused=False, stopped=False)
        s.add(row)
        s.commit()
    return row


# ─── Public API ───────────────────────────────────────────────────────────────

def start_run(job_type: str, total: int = 0) -> JobRun:
    with _lock:
        run = JobRun(job_type=job_type, status="running", total=total)
        _runs[job_type] = run
    _persist(run)
    return run


def save_run(run: JobRun) -> None:
    """Checkpoint progress to the DB (call after each article / source)."""
    _persist(run)


def get_run(job_type: str) -> Optional[JobRun]:
    run = _runs.get(job_type)
    if run is None:
        run = _load_latest(job_type)
        if run:
            _runs[job_type] = run
    return run


def is_paused(job_type: str = "enrich") -> bool:
    from app.db.session import SessionLocal
    with SessionLocal() as s:
        return _get_flag_row(s, job_type).paused


def set_paused(job_type: str, paused: bool) -> None:
    from app.db.session import SessionLocal
    with SessionLocal() as s:
        row = _get_flag_row(s, job_type)
        row.paused = paused
        s.commit()


def is_stopped(job_type: str = "enrich") -> bool:
    from app.db.session import SessionLocal
    with SessionLocal() as s:
        return _get_flag_row(s, job_type).stopped


def set_stopped(job_type: str, stopped: bool) -> None:
    from app.db.session import SessionLocal
    with SessionLocal() as s:
        row = _get_flag_row(s, job_type)
        row.stopped = stopped
        s.commit()


def finish_run(run: JobRun, status: str = "completed") -> None:
    with _lock:
        run.status = status
        run.current_title = None
        run.finished_at = datetime.now(timezone.utc)
    _persist(run)
