from fastapi import Depends, FastAPI, HTTPException, status
from fastapi_sso.sso.google import GoogleSSO
from sqlalchemy.orm import Session
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from sqlalchemy.exc import SQLAlchemyError
from core.user_middleware import user_middleware
from core.utility import create_response
from core.context_vars import access_token_ctx, user_id_ctx
from models.UserModel import UserModel, UserTokenModel
from core.auth_helper import get_hashed_password, verify_password, create_access_token, get_current_user
from schemas.user_schema import UserLoginRequest, UserRegisterRequest, UserLoginResponse, UserResponse, DefaultResponse
from config.database import engine, get_db_connection, base
import os
import logging

app = FastAPI()

logger = logging.getLogger(__name__)

#Enable cors
accepted_origins = ["http://localhost:4200", "http://localhost:8000"]

#Add the custom middleware and the cors
app.add_middleware(BaseHTTPMiddleware, dispatch=user_middleware)
app.add_middleware(
    CORSMiddleware, 
    allow_origins=accepted_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

#Spin up all the models that is needed to be created
base.metadata.create_all(bind=engine)

#Google SSO
google_sso = GoogleSSO(
    client_id=os.getenv('GOOGLE_CLIENT_ID'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
    redirect_uri= "http://localhost:8000/api/auth/callback"
)

@app.get("/")
async def root():
    return {"message": "API is running"}

@app.get("/auth/google/login")
async def google_login():
    return await google_sso.get_login_redirect()

@app.get("/api/auth/callback")
async def google_callback(request: Request, db: Session = Depends(get_db_connection)):
    user_info = await google_sso.verify_and_process(request)
    
    email = user_info.email
    first_name = user_info.first_name
    last_name = user_info.last_name

    user = db.query(UserModel).filter(UserModel.email == email and UserModel.is_active == True and UserModel.is_deleted == False).first()

    if not user:
        user = UserModel(
            firstname=first_name,
            lastname=last_name,
            email=email,
            hashed_password="GOOGLE_AUTH",# placeholder since no password
            sso_enabled=True
        )

        db.add(user)
        db.commit()
        db.refresh(user)

    # Create JWT token
    access_token = create_access_token(data={
        "sub": user.email,
        "firstname": user.firstname,
        "lastname": user.lastname
    })

    #Create the access token => to check for the status of authentication
    update_access_token = UserTokenModel(
        user_id = user.user_id,
        token = access_token 
    )

    db.add(update_access_token)
    db.commit()
    db.refresh(update_access_token)

    # Redirect to frontend with token
    response = RedirectResponse(url=f"http://localhost:4200/dashboard?token={access_token}")
    return response


@app.post("/register-user", response_model=UserLoginResponse)
async def register_user(user_data: UserRegisterRequest, db: Session = Depends(get_db_connection)):

    #Create the user
    user_db_data = UserModel(
        firstname = user_data.firstname,
        lastname = user_data.lastname,
        email = user_data.email,
        hashed_password = get_hashed_password(user_data.password)
    )

    db.add(user_db_data)
    db.commit()
    db.refresh(user_db_data)

    return create_response(200, "register_user", "Success")



@app.post("/token", response_model=UserLoginResponse)
async def login_user(user_credentials: UserLoginRequest, db: Session = Depends(get_db_connection)):
    
    try:

        email = user_credentials.email
        password = user_credentials.password

        user_data = db.query(UserModel).filter(UserModel.email == email and UserModel.is_active == True and UserModel.is_deleted == False).first()

        #Check the email is correct
        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Login Failed! Username or Password is incorrect",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        #User is signed up with Google Auth => redirect to google sign in page
        if user_data.sso_enabled:
            raise HTTPException(
                status_code=status.HTTP_307_TEMPORARY_REDIRECT,
                detail="SSO Enabled. Please redirect to /auth/google/login"
            )
            

        #Check the password is correct
        if not verify_password(password, user_data.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Login Failed! Username or Password is incorrect",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        access_token = create_access_token(data={
            "sub": user_data.email,
            "firstname": user_data.firstname,
            "lastname": user_data.lastname
        })

        #Create the access token => to check for the status of authentication
        update_access_token = UserTokenModel(
            user_id = user_data.user_id,
            token = access_token 
        )

        db.add(update_access_token)
        db.commit()
        db.refresh(update_access_token)

        return UserLoginResponse(
            access_token=access_token,
            user=UserResponse.model_validate(user_data)
        )
        
    except Exception:
        logger.exception("Unexpected error in creating user")
        return create_response(500, "invalid_user_login", "Error")
        

@app.get("/current-user", response_model=UserResponse)
async def get_current_user_route(_: UserResponse = Depends(get_current_user)):
    return user_id_ctx.get()

@app.post("/logout", response_model=DefaultResponse)
async def logout(db: Session = Depends(get_db_connection), _: DefaultResponse = Depends(get_current_user)):
    
    token_entry = db.query(UserTokenModel).filter(UserTokenModel.token == access_token_ctx.get() and UserTokenModel.user_id == user_id_ctx.get('user_id')).first()

    if token_entry:
        token_entry.is_revoked = True
    
    db.commit()

    return DefaultResponse(title="Success", message="Successfully logged out and token revoked")


