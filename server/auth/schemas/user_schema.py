from pydantic import BaseModel, EmailStr


'''REQUEST SCHEMA SECTION'''

class UserRegisterRequest(BaseModel):
    firstname : str
    lastname : str
    email : EmailStr
    password : str

class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str


'''RESPONSE SCHEMA SECTION'''
class DefaultResponse(BaseModel):
    title: str
    message: str

class UserResponse(BaseModel):
    user_id: int
    firstname : str
    lastname : str
    email : EmailStr

    #To read the queried objects as pyndantic data
    class Config:
        from_attributes  = True

class UserLoginResponse(BaseModel):
    access_token: str
    user: UserResponse
