from fastapi import APIRouter, HTTPException, status
from sentinel_admin_api.deps import ConductorDep, CurrentUserDep
from sentinel_admin_api.schemas import (
    TargetResponse, GroupMemberAdd,
    HostGroupCreate, HostGroupResponse, HostGroupUpdate,
)

router = APIRouter(prefix="/groups", tags=["host-groups"])


@router.get("", response_model=list[HostGroupResponse])
async def list_groups(conductor: ConductorDep, _: CurrentUserDep):
    return conductor.call({}, "list_host_groups")


@router.post("", response_model=HostGroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group(body: HostGroupCreate, conductor: ConductorDep, _: CurrentUserDep):
    return conductor.call({}, "create_host_group", data=body.model_dump())


@router.get("/{group_id}", response_model=HostGroupResponse)
async def get_group(group_id: str, conductor: ConductorDep, _: CurrentUserDep):
    result = conductor.call({}, "get_host_group", group_id=group_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    return result


@router.patch("/{group_id}", response_model=HostGroupResponse)
async def update_group(
    group_id: str, body: HostGroupUpdate, conductor: ConductorDep, _: CurrentUserDep
):
    result = conductor.call(
        {}, "update_host_group",
        group_id=group_id, data=body.model_dump(exclude_none=True),
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    return result


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(group_id: str, conductor: ConductorDep, _: CurrentUserDep):
    ok = conductor.call({}, "delete_host_group", group_id=group_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")


@router.get("/{group_id}/members", response_model=list[TargetResponse])
async def list_members(group_id: str, conductor: ConductorDep, _: CurrentUserDep):
    return conductor.call({}, "list_group_members", group_id=group_id)


@router.post("/{group_id}/members", status_code=status.HTTP_204_NO_CONTENT)
async def add_member(
    group_id: str, body: GroupMemberAdd, conductor: ConductorDep, _: CurrentUserDep
):
    ok = conductor.call({}, "add_target_to_group", group_id=group_id, target_id=body.target_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group or target not found",
        )


@router.delete("/{group_id}/members/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    group_id: str, target_id: str, conductor: ConductorDep, _: CurrentUserDep
):
    ok = conductor.call({}, "remove_target_from_group", group_id=group_id, target_id=target_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Membership not found",
        )
