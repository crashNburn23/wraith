import json
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Literal
from app.api.deps import get_db
from app.services.rag import stream_chat
from app.core.config import settings

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=20_000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=100)


@router.post("")
async def chat(body: ChatRequest, db: Session = Depends(get_db)):
    async def event_stream():
        async for event in stream_chat(db, [message.model_dump() for message in body.messages]):
            yield f"data: {json.dumps(event)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/health")
def chat_health():
    return {
        "provider": settings.LLM_PROVIDER,
        "model": settings.LLM_MODEL,
        "base_url": settings.LLM_BASE_URL if settings.LLM_PROVIDER == "ollama" else "anthropic",
    }
