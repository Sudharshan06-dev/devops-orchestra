from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone


'''REQUEST SCHEMA SECTION'''


class UserChatRequest(BaseModel):
    # default role is 'user' so clients that omit it won't fail validation
    role: str = Field(default='user')
    content: str
    # timestamp will default to current time if omitted by the client
    timestamp: Optional[str] = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    chat_id: Optional[str] = None


class UserChatResponse(BaseModel):
    role: str
    content: str
    timestamp: str
    message_id: str
    chat_id: str
    user_id: int
    is_active: int
