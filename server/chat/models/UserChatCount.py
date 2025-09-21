from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Enum, Text
from datetime import datetime
from config.database import base as Base

# Base model for common attributes
class BaseModel(Base):
    __abstract__ = True  # This will not create a separate table
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_deleted = Column(Boolean, default=False)


class UserChatCountModel(BaseModel):
    """
    Represents users in the system, storing their login credentials and role.
    """
    __tablename__ = 'user_chat_count'

    user_id = Column(Integer, primary_key=True, index=True)
    count = Column(Integer)