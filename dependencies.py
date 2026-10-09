"""
dependencies.py - FastAPI dependencies
"""
from fastapi import Depends, HTTPException, status, Cookie
from sqlalchemy.orm import Session
from database import get_db
from auth import decode_access_token
from models import User
from typing import Optional

async def get_current_user(
    token: str = Cookie(None, alias="access_token"),
    db: Session = Depends(get_db)
) -> User:
    """
    Get the current authenticated user from JWT token in cookie.
    Raises 401 if token is invalid or user not found.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token"
        )
    
    user_id: str = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    return user


async def get_current_user_optional(
    token: str = Cookie(None, alias="access_token"),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    Get the current authenticated user from JWT token in cookie.
    Returns None if token is missing or invalid (doesn't raise exception).
    """
    if not token:
        return None
    
    payload = decode_access_token(token)
    if not payload:
        return None
    
    user_id: str = payload.get("sub")
    if not user_id:
        return None
    
    user = db.query(User).filter(User.id == user_id).first()
    return user
