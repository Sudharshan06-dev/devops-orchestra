from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from passlib.context import CryptContext
from datetime import datetime, timedelta, timezone
from models.UserModel import UserModel
from core.context_vars import user_id_ctx
from typing import Optional
from dotenv import load_dotenv
from config.database import get_db_connection
from schemas.user_schema import UserResponse
import jwt
import os

#Load all the env data
load_dotenv()

#Add all the contexts and dependecies need to be used
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl='token')


def get_hashed_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_user_details(email: str, db: Session) ->Optional[UserModel]:
    #Check for the context vars, if not present query the database
    user_details = user_id_ctx.get()

    if user_details is None:
        user_details = db.query(UserModel).filter(UserModel.email == email and UserModel.is_active == True and UserModel.is_deleted == False).first()
        user_id_ctx.set(user_details)
        print('check user_id context', user_id_ctx.get())
    return user_details

def validate_user(email: str, password: str, db: Session) -> Optional[UserModel]:

    user_details = user_id_ctx.get() if user_id_ctx.get() else get_user_details(email, db)

    if not user_details or not verify_password(password, user_details.hashed_password):
        return None
    
    return user_details

def create_access_token(data: dict, expires_delta=timedelta(minutes=30 * 60 * 60)) -> jwt:

    encode_data = data.copy()

    expire = datetime.now(timezone.utc) + expires_delta

    encode_data.update({"exp": expire})

    return jwt.encode(encode_data, os.getenv('SECRET_KEY'), os.getenv('ALGORITHM'))


async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db_connection)) -> UserResponse:
    try:

        if user_id_ctx.get():
            return user_id_ctx.get()
        
        payload = jwt.decode(token, os.getenv('AUTH_SECRET_KEY'), algorithms=[os.getenv('AUTH_ALGORITHM')])

        username: str = payload.get("sub")
        
        if username is None:
            raise HTTPException(status_code=401, detail="User not found")
        
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="User not found")

    user = get_user_details(username, db)

    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    return UserResponse.model_validate(user)



