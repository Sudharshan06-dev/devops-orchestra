from pydantic import BaseModel


'''REQUEST SCHEMA SECTION'''

class UserChatRequest(BaseModel):
    role: str
    content: str
    timestamp: str
    chat_id: str

class UserChatResponse(BaseModel):
    role: str
    content: str
    timestamp: str
    message_id: str  # Changed from int to str
    chat_id: str     # Changed from int to str
    user_id: int
    is_active: int
