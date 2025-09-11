#HELPERS FUNCTION
from fastapi.responses import JSONResponse
from schemas.user_schema import DefaultResponse
from core.messages import SUCCESS, ERROR


##Common Utility Function for Responses ##
def create_response(status_code: int, message: str, status: str):
    message_value = SUCCESS.get(message) if status == 'Success' else ERROR.get(message)
    return JSONResponse(status_code=status_code, content=DefaultResponse(title=status, message=message_value).dict())