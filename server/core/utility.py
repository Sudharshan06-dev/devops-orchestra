#HELPERS FUNCTION
from fastapi.responses import JSONResponse
from core.messages import SUCCESS, ERROR
from schemas.shared import DefaultResponse


##Common Utility Function for Responses ##
def create_response(status_code: int, message: str, status: str):
    if status == 'Success':
        message_value = SUCCESS.get(message, "Success")
    else:
        message_value = ERROR.get(message, "An error occurred")
    
    return JSONResponse(
        status_code=status_code, 
        content=DefaultResponse(title=status, message=message_value).dict()
    )