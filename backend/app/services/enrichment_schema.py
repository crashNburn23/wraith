from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional


class IOCItem(BaseModel):
    ioc_type: str   # ip, domain, hash, url, email
    value: str
    ioc_confidence: str = Field(default="high")  # high, medium, low
    source_excerpt: Optional[str] = None


class TTPItem(BaseModel):
    technique_id: str   # T1566
    technique_name: str
    tactic: Optional[str] = None
    source_excerpt: Optional[str] = None


class ActorItem(BaseModel):
    name: str
    source_excerpt: Optional[str] = None


class CVEItem(BaseModel):
    cve_id: str
    source_excerpt: Optional[str] = None


class EnrichmentResult(BaseModel):
    summary: str = Field(default="")
    threat_category: str = Field(default="General")
    severity_score: float = Field(default=0.0, ge=0, le=100)
    sector_targets: list[str] = Field(default_factory=list)
    geo_origin: Optional[str] = None
    geo_targets: list[str] = Field(default_factory=list)
    iocs: list[IOCItem] = Field(default_factory=list)
    ttps: list[TTPItem] = Field(default_factory=list)
    threat_actors: list[ActorItem] = Field(default_factory=list)
    cves: list[CVEItem] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def drop_null_names(cls, data: dict) -> dict:
        if isinstance(data, dict):
            actors = data.get("threat_actors") or []
            data["threat_actors"] = [a for a in actors if isinstance(a, dict) and a.get("name")]
        return data
