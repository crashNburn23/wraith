from pydantic import BaseModel, Field
from typing import Optional


class IOCItem(BaseModel):
    ioc_type: str   # ip, domain, hash, url, email
    value: str


class TTPItem(BaseModel):
    technique_id: str   # T1566
    technique_name: str
    tactic: Optional[str] = None


class EnrichmentResult(BaseModel):
    summary: str = Field(default="")
    threat_category: str = Field(default="General")
    severity_score: float = Field(default=0.0, ge=0, le=100)
    sector_targets: list[str] = Field(default_factory=list)
    geo_origin: Optional[str] = None
    geo_targets: list[str] = Field(default_factory=list)
    iocs: list[IOCItem] = Field(default_factory=list)
    ttps: list[TTPItem] = Field(default_factory=list)
    threat_actors: list[str] = Field(default_factory=list)
    cves: list[str] = Field(default_factory=list)
