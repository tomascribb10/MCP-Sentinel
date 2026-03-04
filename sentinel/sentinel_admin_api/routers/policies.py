from fastapi import APIRouter, HTTPException, Query, status
from sentinel_admin_api.deps import ConductorDep, CurrentUserDep
from sentinel_admin_api.schemas import (
    RoleBindingCreate, RoleBindingResponse, RoleBindingUpdate,
)

router = APIRouter(prefix="/policies", tags=["policies"])


@router.get("", response_model=list[RoleBindingResponse])
async def list_policies(
    conductor: ConductorDep,
    _: CurrentUserDep,
    principal_id: str | None = Query(None),
):
    return conductor.call({}, "list_role_bindings", principal_id=principal_id)


@router.post("", response_model=RoleBindingResponse, status_code=status.HTTP_201_CREATED)
async def create_policy(
    body: RoleBindingCreate, conductor: ConductorDep, _: CurrentUserDep
):
    return conductor.call({}, "create_role_binding", data=body.model_dump())


@router.get("/{policy_id}", response_model=RoleBindingResponse)
async def get_policy(policy_id: str, conductor: ConductorDep, _: CurrentUserDep):
    result = conductor.call({}, "get_role_binding", binding_id=policy_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
    return result


@router.patch("/{policy_id}", response_model=RoleBindingResponse)
async def update_policy(
    policy_id: str, body: RoleBindingUpdate, conductor: ConductorDep, _: CurrentUserDep
):
    result = conductor.call(
        {}, "update_role_binding",
        binding_id=policy_id, data=body.model_dump(exclude_none=True),
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
    return result


@router.delete("/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_policy(policy_id: str, conductor: ConductorDep, _: CurrentUserDep):
    ok = conductor.call({}, "delete_role_binding", binding_id=policy_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
