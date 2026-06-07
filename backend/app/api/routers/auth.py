from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])

_ALGORITHM = "HS256"
_EXPIRY_DAYS = 30


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginRequest):
    if body.username != settings.AUTH_USERNAME or body.password != settings.AUTH_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = jwt.encode(
        {"sub": body.username, "exp": datetime.now(timezone.utc) + timedelta(days=_EXPIRY_DAYS)},
        settings.SECRET_KEY,
        algorithm=_ALGORITHM,
    )
    return {"access_token": token, "token_type": "bearer"}
