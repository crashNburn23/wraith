from pydantic import BaseModel, Field, model_validator
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
    weight_ai_severity: Optional[float] = Field(default=None, ge=0, le=1)
    weight_feedback_signal: Optional[float] = Field(default=None, ge=0, le=1)
    weight_profile_match: Optional[float] = Field(default=None, ge=0, le=1)
    weight_kev_bonus: Optional[float] = Field(default=None, ge=0, le=1)
    weight_recency: Optional[float] = Field(default=None, ge=0, le=1)
    feedback_lookback_days: Optional[int] = Field(default=None, ge=1, le=3650)
    recency_half_life_days: Optional[float] = Field(default=None, gt=0, le=3650)
    min_feedback_articles: Optional[int] = Field(default=None, ge=1, le=10000)
    feedback_decay_half_life_days: Optional[float] = Field(default=None, gt=0, le=3650)

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
