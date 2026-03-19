from fastapi import APIRouter, HTTPException, Query, status
from sentinel_admin_api.deps import ConductorDep, CurrentUserDep
from sentinel_admin_api.schemas import TargetResponse, TargetUpdate, HostGroupResponse

router = APIRouter(prefix="/targets", tags=["targets"])


@router.get("", response_model=list[TargetResponse])
async def list_targets(
    conductor: ConductorDep,
    _: CurrentUserDep,
    status_filter: str | None = Query(None, alias="status"),
):
    return conductor.call({}, "list_targets", status_filter=status_filter)


@router.get("/{target_id}", response_model=TargetResponse)
async def get_target(target_id: str, conductor: ConductorDep, _: CurrentUserDep):
    result = conductor.call({}, "get_target", target_id=target_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found")
    return result


@router.patch("/{target_id}", response_model=TargetResponse)
async def update_target(
    target_id: str, body: TargetUpdate, conductor: ConductorDep, _: CurrentUserDep
):
    result = conductor.call({}, "update_target", target_id=target_id, data=body.model_dump())
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found")
    return result


@router.delete("/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_target(target_id: str, conductor: ConductorDep, _: CurrentUserDep):
    ok = conductor.call({}, "delete_target", target_id=target_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found")


@router.get("/{target_id}/groups", response_model=list[HostGroupResponse])
async def get_target_groups(target_id: str, conductor: ConductorDep, _: CurrentUserDep):
    """List all host groups the target belongs to."""
    all_groups = conductor.call({}, "list_host_groups")
    result = []
    for group in all_groups:
        members = conductor.call({}, "list_group_members", group_id=group["id"])
        if any(m["target_id"] == target_id for m in members):
            result.append(group)
    return result
