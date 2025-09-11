from fastapi import Request
from config.database import get_db_connection
from core.auth_helper import get_user_details  # Import your auth functions
from core.context_vars import user_id_ctx, access_token_ctx
import os
import jwt


async def user_middleware(request: Request, call_next):

    auth_header = request.headers.get('Authorization')

    if auth_header and auth_header.startswith('Bearer '):

        auth_token = auth_header.split(" ")[1]

        access_token_ctx.set(auth_token)

        try:

            payload = jwt.decode(auth_token, os.getenv('SECRET_KEY'), os.getenv('ALGORITHM'))

            #Check the token for revoked access
            #TODO

            email = payload.get("sub")

            if email:
                db = next(get_db_connection())
                user = get_user_details(email, db)

                if user and user_id_ctx.get() is None:
                    user_id_ctx.set(user)
        
        except Exception as e:
            print('Error occured while getting the user details', e)
            pass
    
    response = await call_next(request)

    return response
