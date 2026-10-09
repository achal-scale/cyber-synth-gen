"""
api/auth.py - Authentication routes
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from audit import audit
from auth import create_access_token, hash_password, verify_password
from config import settings
from database import get_db
from dependencies import get_current_user
from models import User
from schemas import AuthResponse, LoginRequest, UserCreate, UserEnvelope, UserResponse, SuccessResponse

router = APIRouter()


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(user_data: UserCreate, response: Response, db: Session = Depends(get_db)):
    username = user_data.username.strip()
    email = user_data.email.strip()
    display_name = (user_data.display_name or "").strip() or username

    existing_by_username = db.query(User).filter(User.username == username).first()
    existing_by_email = db.query(User).filter(User.email == email).first()

    if existing_by_username and existing_by_email and existing_by_username.id != existing_by_email.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username or email already registered")

    existing_user = existing_by_username or existing_by_email
    if existing_user:
        if verify_password(user_data.password, existing_user.password_hash):
            access_token = create_access_token(data={"sub": existing_user.id})
            response.set_cookie(
                key="access_token",
                value=access_token,
                httponly=True,
                secure=settings.SECURE_COOKIES,
                samesite="lax",
                max_age=60 * 60 * 24 * 7,
            )
            response.status_code = status.HTTP_200_OK
            return AuthResponse(user=UserResponse.model_validate(existing_user))

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username or email already registered")

    hashed_password = hash_password(user_data.password)
    new_user = User(
        username=username,
        display_name=display_name,
        email=email,
        password_hash=hashed_password,
    )

    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
    except IntegrityError as exc:
        db.rollback()
        existing_user = db.query(User).filter(
            (User.username == username) | (User.email == email)
        ).first()
        if existing_user and verify_password(user_data.password, existing_user.password_hash):
            access_token = create_access_token(data={"sub": existing_user.id})
            response.set_cookie(
                key="access_token",
                value=access_token,
                httponly=True,
                secure=settings.SECURE_COOKIES,
                samesite="lax",
                max_age=60 * 60 * 24 * 7,
            )
            response.status_code = status.HTTP_200_OK
            return AuthResponse(user=UserResponse.model_validate(existing_user))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already registered",
        ) from exc

    audit("auth.register", actor=new_user.username, resource="user", outcome="success")
    access_token = create_access_token(data={"sub": new_user.id})
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.SECURE_COOKIES,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
    )

    return AuthResponse(user=UserResponse.model_validate(new_user))


@router.post("/login", response_model=AuthResponse)
def login(login_data: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(
        (User.email == login_data.email_or_username)
        | (User.username == login_data.email_or_username)
    ).first()

    if not user or not verify_password(login_data.password, user.password_hash):
        audit("auth.login", actor=login_data.email_or_username, resource="session", outcome="failure")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email/username or password",
        )

    audit("auth.login", actor=user.username, resource="session", outcome="success")
    access_token = create_access_token(data={"sub": user.id})
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.SECURE_COOKIES,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
    )

    return AuthResponse(user=UserResponse.model_validate(user))


@router.post("/logout", response_model=SuccessResponse)
def logout(response: Response, current_user: User = Depends(get_current_user)):
    audit("auth.logout", actor=current_user.username, resource="session", outcome="success")
    response.delete_cookie(key="access_token")
    return SuccessResponse(success=True)


@router.get("/me", response_model=UserEnvelope)
def get_current_user_info(current_user: User = Depends(get_current_user)):
    return UserEnvelope(user=UserResponse.model_validate(current_user))
