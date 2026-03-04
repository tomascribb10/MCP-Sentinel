from fastapi import APIRouter, HTTPException, status
from sentinel_admin_api.deps import ConductorDep, CurrentUserDep
from sentinel_admin_api.schemas import (
    CommandCreate, CommandResponse,
    CommandSetCreate, CommandSetResponse,
)

router = APIRouter(prefix="/command-sets", tags=["command-sets"])


@router.get("", response_model=list[CommandSetResponse])
async def list_command_sets(conductor: ConductorDep, _: CurrentUserDep):
    return conductor.call({}, "list_command_sets")


@router.post("", response_model=CommandSetResponse, status_code=status.HTTP_201_CREATED)
async def create_command_set(
    body: CommandSetCreate, conductor: ConductorDep, _: CurrentUserDep
):
    return conductor.call({}, "create_command_set", data=body.model_dump())


@router.get("/{command_set_id}", response_model=CommandSetResponse)
async def get_command_set(command_set_id: str, conductor: ConductorDep, _: CurrentUserDep):
    result = conductor.call({}, "get_command_set", command_set_id=command_set_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Command set not found")
    return result


@router.delete("/{command_set_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_command_set(
    command_set_id: str, conductor: ConductorDep, _: CurrentUserDep
):
    ok = conductor.call({}, "delete_command_set", command_set_id=command_set_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Command set not found")


@router.post(
    "/{command_set_id}/commands",
    response_model=CommandResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_command(
    command_set_id: str,
    body: CommandCreate,
    conductor: ConductorDep,
    _: CurrentUserDep,
):
    result = conductor.call(
        {}, "create_command", command_set_id=command_set_id, data=body.model_dump()
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Command set not found")
    return result


@router.delete(
    "/{command_set_id}/commands/{command_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_command(
    command_set_id: str, command_id: str, conductor: ConductorDep, _: CurrentUserDep
):
    ok = conductor.call({}, "delete_command", command_id=command_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Command not found")
