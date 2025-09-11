from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Enum, Text
from datetime import datetime
from config.database import base as Base

# Base model for common attributes
class BaseModel(Base):
    __abstract__ = True  # This will not create a separate table
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_deleted = Column(Boolean, default=False)


class UserModel(BaseModel):
    """
    Represents users in the system, storing their login credentials and role.
    """
    __tablename__ = 'users'

    user_id = Column(Integer, primary_key=True, index=True)
    firstname = Column(String(100), nullable=False)
    lastname = Column(String(100), nullable=False)
    email = Column(String(256), unique=True, index=True, nullable=False)
    hashed_password = Column(String(256), nullable=False)
    last_login_activity = Column(DateTime, default=datetime.utcnow)
    sso_enabled = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

class UserTokenModel(Base):
    """
    Stores authentication tokens for user sessions.
    """
    __tablename__ = 'user_tokens'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.user_id', ondelete="CASCADE"), nullable=False)
    token = Column(String(255), unique=True, nullable=False)
    is_revoked = Column(Boolean, default=False)