from fastapi import APIRouter, HTTPException, status
from sentinel_admin_api.auth import hash_password
from sentinel_admin_api.deps import ConductorDep, CurrentUserDep, SuperUserDep
from sentinel_admin_api.schemas import UserCreate, UserResponse, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserResponse])
async def list_users(conductor: ConductorDep, _: SuperUserDep):
    return conductor.call({}, "list_users")


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(body: UserCreate, conductor: ConductorDep, _: SuperUserDep):
    data = body.model_dump()
    data["hashed_password"] = hash_password(data.pop("password"))
    return conductor.call({}, "create_user", data=data)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str, body: UserUpdate, conductor: ConductorDep, _: SuperUserDep
):
    data = body.model_dump(exclude_none=True)
    if "password" in data:
        data["hashed_password"] = hash_password(data.pop("password"))
    result = conductor.call({}, "update_user", user_id=user_id, data=data)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return result


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: str, conductor: ConductorDep, _: SuperUserDep):
    ok = conductor.call({}, "delete_user", user_id=user_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
