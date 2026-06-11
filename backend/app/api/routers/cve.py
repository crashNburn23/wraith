from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.models import CVERecord, CVEMention

router = APIRouter(prefix="/cve", tags=["cve"])


@router.get("")
def list_cves(
    db: Session = Depends(get_db),
    in_kev: bool | None = None,
    cvss_min: float | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    q = db.query(CVERecord)
    if in_kev is not None:
        q = q.filter(CVERecord.in_kev == in_kev)
    if cvss_min is not None:
        q = q.filter(CVERecord.cvss_score >= cvss_min)
    total = q.count()
    items = q.order_by(CVERecord.cvss_score.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total,
        "items": [
            {
                "id": r.id,
                "cve_id": r.cve_id,
                "cvss_score": r.cvss_score,
                "epss_score": r.epss_score,
                "epss_percentile": r.epss_percentile,
                "in_kev": r.in_kev,
                "kev_due_date": r.kev_due_date,
                "nvd_description": r.nvd_description,
                "ai_summary": r.ai_summary,
            }
            for r in items
        ],
    }


@router.get("/stats")
def cve_stats(db: Session = Depends(get_db)):
    total = db.query(CVERecord).count()
    kev = db.query(CVERecord).filter(CVERecord.in_kev == True).count()
    critical = db.query(CVERecord).filter(CVERecord.cvss_score >= 9.0).count()
    return {"total": total, "in_kev": kev, "critical_cvss": critical}


@router.post("/sync")
async def trigger_cve_sync(background_tasks: BackgroundTasks):
    from app.db.session import SessionLocal
    from app.services.cve_enrichment import sync_cves_for_articles

    async def _run():
        # Own session: the request-scoped one is closed before background tasks run
        session = SessionLocal()
        try:
            await sync_cves_for_articles(session)
        finally:
            session.close()

    background_tasks.add_task(_run)
    return {"status": "started"}


@router.get("/{cve_id}")
def get_cve(cve_id: str, db: Session = Depends(get_db)):
    record = db.query(CVERecord).filter(CVERecord.cve_id == cve_id.upper()).first()
    if not record:
        raise HTTPException(404, "CVE not found")
    article_ids = [m.article_id for m in db.query(CVEMention).filter(CVEMention.cve_id == cve_id).all()]
    return {
        "cve_id": record.cve_id,
        "cvss_score": record.cvss_score,
        "epss_score": record.epss_score,
        "epss_percentile": record.epss_percentile,
        "in_kev": record.in_kev,
        "kev_due_date": record.kev_due_date,
        "nvd_description": record.nvd_description,
        "ai_summary": record.ai_summary,
        "article_ids": article_ids,
    }
