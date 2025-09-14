from pydantic import BaseModel

'''RESPONSE SCHEMA SECTION'''
class DefaultResponse(BaseModel):
    title: str
    message: str