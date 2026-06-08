from pydantic import BaseModel, model_validator
from typing import Optional
from datetime import datetime


class ScoringConfigOut(BaseModel):
    id: str
    weight_ai_severity: float
    weight_feedback_signal: float
    weight_profile_match: float
    weight_kev_bonus: float
    weight_recency: float
    feedback_lookback_days: int
    recency_half_life_days: float
    min_feedback_articles: int
    feedback_decay_half_life_days: float
    updated_at: datetime
    model_config = {"from_attributes": True}


class ScoringConfigUpdate(BaseModel):
    weight_ai_severity: Optional[float] = None
    weight_feedback_signal: Optional[float] = None
    weight_profile_match: Optional[float] = None
    weight_kev_bonus: Optional[float] = None
    weight_recency: Optional[float] = None
    feedback_lookback_days: Optional[int] = None
    recency_half_life_days: Optional[float] = None
    min_feedback_articles: Optional[int] = None
    feedback_decay_half_life_days: Optional[float] = None

    @model_validator(mode="after")
    def weights_sum_to_one(self):
        weights = [
            self.weight_ai_severity,
            self.weight_feedback_signal,
            self.weight_profile_match,
            self.weight_kev_bonus,
            self.weight_recency,
        ]
        provided = [w for w in weights if w is not None]
        if len(provided) == 5:
            total = sum(provided)
            if abs(total - 1.0) > 0.001:
                raise ValueError(f"The five weights must sum to 1.0 (got {total:.3f})")
        return self
