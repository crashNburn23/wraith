import csv
import io

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.models import Source
from app.schemas.source import SourceCreate, SourceUpdate, SourceOut
from app.db.base import new_uuid

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("", response_model=list[SourceOut])
def list_sources(db: Session = Depends(get_db)):
    return db.query(Source).order_by(Source.name).all()


@router.post("", response_model=SourceOut, status_code=201)
def create_source(body: SourceCreate, db: Session = Depends(get_db)):
    if db.query(Source).filter(Source.url == body.url).first():
        raise HTTPException(400, "A source with this URL already exists")
    source = Source(id=new_uuid(), **body.model_dump())
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


@router.get("/{source_id}", response_model=SourceOut)
def get_source(source_id: str, db: Session = Depends(get_db)):
    source = db.query(Source).filter(Source.id == source_id).first()
    if not source:
        raise HTTPException(404, "Source not found")
    return source


@router.patch("/{source_id}", response_model=SourceOut)
def update_source(source_id: str, body: SourceUpdate, db: Session = Depends(get_db)):
    source = db.query(Source).filter(Source.id == source_id).first()
    if not source:
        raise HTTPException(404, "Source not found")
    for field, val in body.model_dump(exclude_none=True).items():
        setattr(source, field, val)
    db.commit()
    db.refresh(source)
    return source


@router.delete("/{source_id}", status_code=204)
def delete_source(source_id: str, db: Session = Depends(get_db)):
    source = db.query(Source).filter(Source.id == source_id).first()
    if not source:
        raise HTTPException(404, "Source not found")
    db.delete(source)
    db.commit()


@router.post("/import-csv")
async def import_sources_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    # Normalize field names to lowercase
    if reader.fieldnames:
        reader.fieldnames = [f.strip().lower() for f in reader.fieldnames]

    added, skipped, errors = [], [], []

    for i, row in enumerate(reader):
        name = (row.get("name") or "").strip()
        url = (row.get("url") or row.get("feed_url") or row.get("feed url") or "").strip()

        if not name or not url:
            errors.append({"row": i + 2, "error": "Missing name or url"})
            continue

        if db.query(Source).filter(Source.url == url).first():
            skipped.append(url)
            continue

        try:
            db.add(Source(id=new_uuid(), name=name, url=url))
            db.flush()
            added.append(name)
        except Exception as e:
            db.rollback()
            errors.append({"row": i + 2, "error": str(e)})

    db.commit()
    return {"added": len(added), "skipped": len(skipped), "errors": errors}
