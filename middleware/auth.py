import os
from typing import Optional
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from firebase.client import verify_token

security = HTTPBearer()

async def get_current_user(auth: HTTPAuthorizationCredentials = Depends(security)):
    """Verifies the Firebase ID token in the Authorization header."""
    if os.getenv("BYPASS_AUTH", "false").lower() == "true":
        # Mock user for local development
        user = {"uid": "local_dev_user", "email": "dev@gmail.com", "name": "Dev User"}
    else:
        token = auth.credentials
        user = verify_token(token)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Restrict to @gmail.com
    email = user.get("email", "")
    if not email.endswith("@gmail.com"):
        raise HTTPException(status_code=403, detail="Only Gmail accounts are allowed.")
    
    # Initialize profile if it doesn't exist
    from firebase import db_ops
    db_ops.get_or_create_user_profile(user["uid"], {
        "email": email,
        "name": user.get("name", "User"),
        "picture": user.get("picture", "")
    })
    
    return user

async def optional_user(auth: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))):
    """Optional authentication."""
    if os.getenv("BYPASS_AUTH", "false").lower() == "true":
        return {"uid": "local_dev_user"}
    
    if not auth:
        return None
    
    return verify_token(auth.credentials)
