"""
In-memory job state for ingest and enrichment runs.
Single-user local tool — no persistence needed across restarts.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
import threading

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
    status: str          # "running" | "paused" | "completed" | "error" | "idle"
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
        return round((end - self.started_at).total_seconds(), 1)

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


# Module-level state
_runs: dict[str, Optional[JobRun]] = {"ingest": None, "enrich": None}
_paused: dict[str, bool] = {"enrich": False}
_stopped: dict[str, bool] = {"enrich": False}


def start_run(job_type: str, total: int = 0) -> JobRun:
    with _lock:
        run = JobRun(job_type=job_type, status="running", total=total)
        _runs[job_type] = run
        return run


def get_run(job_type: str) -> Optional[JobRun]:
    return _runs.get(job_type)


def is_paused(job_type: str = "enrich") -> bool:
    return _paused.get(job_type, False)


def set_paused(job_type: str, paused: bool) -> None:
    with _lock:
        _paused[job_type] = paused


def is_stopped(job_type: str = "enrich") -> bool:
    return _stopped.get(job_type, False)


def set_stopped(job_type: str, stopped: bool) -> None:
    with _lock:
        _stopped[job_type] = stopped


def finish_run(run: JobRun, status: str = "completed") -> None:
    with _lock:
        run.status = status
        run.current_title = None
        run.finished_at = datetime.now(timezone.utc)
