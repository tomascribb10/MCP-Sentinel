from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from typing import Annotated

from sentinel_admin_api.auth import create_access_token, verify_password
from sentinel_admin_api.deps import ConductorDep, ConfDep, CurrentUserDep
from sentinel_admin_api.schemas import TokenResponse, CurrentUser

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    conductor: ConductorDep,
    conf: ConfDep,
):
    """Authenticate and receive a JWT access token."""
    user = conductor.call({}, "get_user_by_username", username=form.username)
    if user is None or not verify_password(form.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.get("is_active", False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is disabled")

    ttl = conf.auth.admin_api_token_ttl_minutes
    token = create_access_token(
        data={"sub": user["username"]},
        secret_key=conf.auth.admin_api_secret_key,
        expires_minutes=ttl,
    )
    return TokenResponse(access_token=token, expires_in_minutes=ttl)


@router.get("/me", response_model=CurrentUser)
async def get_me(current_user: CurrentUserDep):
    """Return the currently authenticated user."""
    return current_user
