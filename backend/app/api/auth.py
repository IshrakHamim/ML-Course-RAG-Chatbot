import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    hash_password,
    verify_password,
)
from app.models import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserOut

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


def _token_response(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.id), user=UserOut.model_validate(user)
    )


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user account and log in",
    responses={409: {"description": "Email already registered"}},
)
def register(body: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = User(email=body.email, password_hash=hash_password(body.password), role="user")
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered") from None
    logger.info("Registered user id=%s", user.id)
    return _token_response(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Log in and get an access token",
    responses={401: {"description": "Invalid email or password"}},
)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == body.email))
    if user is None:
        verify_password(body.password, DUMMY_PASSWORD_HASH)
    if user is None or not verify_password(body.password, user.password_hash):
        logger.info("Login failed")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    logger.info("Login ok user id=%s", user.id)
    return _token_response(user)


@router.get("/me", response_model=UserOut, summary="Get the current user")
def me(user: User = Depends(get_current_user)) -> User:
    return user
