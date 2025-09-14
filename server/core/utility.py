#HELPERS FUNCTION
from fastapi.responses import JSONResponse
from core.messages import SUCCESS, ERROR
from schemas.shared import DefaultResponse


##Common Utility Function for Responses ##
def create_response(status_code: int, message: str, status: str):
    message_value = SUCCESS.get(message) if status == 'Success' else ERROR.get(message)
    return JSONResponse(status_code=status_code, content=DefaultResponse(title=status, message=message_value).dict())