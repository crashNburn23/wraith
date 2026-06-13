from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class IOCOut(BaseModel):
    id: str
    ioc_type: str
    value: str
    source_excerpt: Optional[str] = None
    user_note: Optional[str]
    model_config = {"from_attributes": True}


class TTPOut(BaseModel):
    id: str
    technique_id: str
    technique_name: str
    tactic: Optional[str]
    source_excerpt: Optional[str] = None
    user_note: Optional[str]
    model_config = {"from_attributes": True}


class ActorOut(BaseModel):
    id: str
    actor_id: str
    actor_name: str
    source_excerpt: Optional[str] = None
    user_note: Optional[str]
    model_config = {"from_attributes": True}


class CVEMentionOut(BaseModel):
    id: str
    cve_id: str
    source_excerpt: Optional[str] = None
    user_note: Optional[str]
    model_config = {"from_attributes": True}


class ArticleListItem(BaseModel):
    id: str
    title: str
    url: str
    source_id: str
    published_at: Optional[datetime]
    enrichment_status: str
    threat_category: Optional[str]
    ai_severity_score: Optional[float]
    geo_origin: Optional[str]
    sector_targets: Optional[list] = None
    og_image: Optional[str] = None
    created_at: datetime
    model_config = {"from_attributes": True}


class ArticleDetail(ArticleListItem):
    ai_summary: Optional[str]
    scraped_text: Optional[str]
    sector_targets: Optional[list]
    geo_targets: Optional[list]
    iocs: list[IOCOut] = []
    ttp_tags: list[TTPOut] = []
    cve_mentions: list[CVEMentionOut] = []
    article_actors: list[ActorOut] = []
    model_config = {"from_attributes": True}
