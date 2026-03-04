from fastapi import APIRouter, HTTPException, Query, status
from sentinel_admin_api.deps import ConductorDep, CurrentUserDep
from sentinel_admin_api.schemas import AgentResponse, AgentUpdate, HostGroupResponse

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=list[AgentResponse])
async def list_agents(
    conductor: ConductorDep,
    _: CurrentUserDep,
    status_filter: str | None = Query(None, alias="status"),
):
    return conductor.call({}, "list_agents", status_filter=status_filter)


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: str, conductor: ConductorDep, _: CurrentUserDep):
    result = conductor.call({}, "get_agent", agent_id=agent_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return result


@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: str, body: AgentUpdate, conductor: ConductorDep, _: CurrentUserDep
):
    result = conductor.call({}, "update_agent", agent_id=agent_id, data=body.model_dump())
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return result


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent_id: str, conductor: ConductorDep, _: CurrentUserDep):
    ok = conductor.call({}, "delete_agent", agent_id=agent_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")


@router.get("/{agent_id}/groups", response_model=list[HostGroupResponse])
async def get_agent_groups(agent_id: str, conductor: ConductorDep, _: CurrentUserDep):
    """List all host groups the agent belongs to."""
    # Get all groups and filter by membership — delegated to conductor CRUD
    all_groups = conductor.call({}, "list_host_groups")
    result = []
    for group in all_groups:
        members = conductor.call({}, "list_group_members", group_id=group["id"])
        if any(m["agent_id"] == agent_id for m in members):
            result.append(group)
    return result
