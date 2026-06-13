from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.schemas.article import ArticleListItem


class ScoreBreakdown(BaseModel):
    computed_score: float
    score_ai_severity: float
    score_feedback_signal: float
    score_profile_match: float = 0.0
    score_kev_bonus: float
    score_recency: float
    raw_ai_severity: float
    raw_feedback_signal: float
    raw_profile_match: float = 0.0
    raw_kev_bonus: float
    raw_recency_factor: float
    feedback_signal_articles: Optional[list] = None


class BulletinItemOut(BaseModel):
    id: str
    rank: int
    article: ArticleListItem
    score: ScoreBreakdown
    user_rating: Optional[int] = None   # -1, 1, or None (unrated)
    user_reason_tags: list = []
    read_status: str = "unread"
    cluster_id: Optional[str] = None
    is_cluster_lead: bool = True
    cluster_size: int = 1
    model_config = {"from_attributes": True}


class BulletinOut(BaseModel):
    id: str
    bulletin_date: str
    generated_at: Optional[datetime]
    items: list[BulletinItemOut] = []
    model_config = {"from_attributes": True}


class BulletinSummary(BaseModel):
    id: str
    bulletin_date: str
    generated_at: Optional[datetime]
    item_count: int
    model_config = {"from_attributes": True}
