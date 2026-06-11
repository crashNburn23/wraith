import secrets
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])

_ALGORITHM = "HS256"
_EXPIRY_DAYS = 30

# Simple in-memory login rate limit: max N failures per IP per window
_RATE_WINDOW_SECONDS = 60
_RATE_MAX_FAILURES = 5
_failures: dict[str, list[float]] = defaultdict(list)


class LoginRequest(BaseModel):
    username: str
    password: str


def _rate_limited(ip: str) -> bool:
    now = time.monotonic()
    _failures[ip] = [t for t in _failures[ip] if now - t < _RATE_WINDOW_SECONDS]
    return len(_failures[ip]) >= _RATE_MAX_FAILURES


@router.post("/login")
def login(body: LoginRequest, request: Request):
    ip = request.client.host if request.client else "unknown"
    if _rate_limited(ip):
        raise HTTPException(429, "Too many failed attempts — try again in a minute")

    # Constant-time comparison to avoid timing side channels
    user_ok = secrets.compare_digest(body.username.encode(), settings.AUTH_USERNAME.encode())
    pass_ok = secrets.compare_digest(body.password.encode(), settings.AUTH_PASSWORD.encode())
    if not (user_ok and pass_ok):
        _failures[ip].append(time.monotonic())
        raise HTTPException(status_code=401, detail="Invalid credentials")

    _failures.pop(ip, None)
    token = jwt.encode(
        {"sub": body.username, "exp": datetime.now(timezone.utc) + timedelta(days=_EXPIRY_DAYS)},
        settings.SECRET_KEY,
        algorithm=_ALGORITHM,
    )
    return {"access_token": token, "token_type": "bearer"}
