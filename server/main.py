from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from auth.user_auth import auth_router
from chat.user_chat import chat_router
from core.user_middleware import user_middleware
from config.database import engine, get_db_connection, base
import logging

app = FastAPI()

logger = logging.getLogger(__name__)

#Enable cors
accepted_origins = ["http://localhost:4200", "http://localhost:8000"]

#Application routers
routers = [auth_router, chat_router]

#Add the custom middleware and the cors
app.add_middleware(BaseHTTPMiddleware, dispatch=user_middleware)
app.add_middleware(
    CORSMiddleware, 
    allow_origins=accepted_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

#Add all the routes for the application
for app_router in routers:
    app.include_router(app_router)

#Spin up all the models that is needed to be created
base.metadata.create_all(bind=engine)

@app.get("/")
async def root():
    return {"message": "API is running"}