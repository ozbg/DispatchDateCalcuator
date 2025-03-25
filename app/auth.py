# app/auth.py
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials, APIKeyHeader
from app.config import API_KEY, USER_CREDENTIALS
from typing import Optional

# If you want to hash passwords, you can install passlib and do:
# from passlib.context import CryptContext
# pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
# def verify_password(plain_password, hashed_password):
#     return pwd_context.verify(plain_password, hashed_password)

security_basic = HTTPBasic(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=False)

def get_current_user(
    request: Request,
    api_key: Optional[str] = Depends(api_key_header),
    credentials: Optional[HTTPBasicCredentials] = Depends(security_basic),
):
    # 1) If an API key is provided, validate it.
    if api_key:
        if api_key == API_KEY:
            return {"username": "api_key_client", "role": "api"}
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API Key",
                headers={"WWW-Authenticate": "Bearer"},
            )
    
    # 2) Otherwise, check for Basic Auth credentials.
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Basic Auth credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    
    user_data = USER_CREDENTIALS.get(credentials.username)
    if not user_data or credentials.password != user_data["password"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Basic Auth credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    
    return {"username": credentials.username, "role": user_data["role"]}