from fastapi import APIRouter, Query
from sentinel_admin_api.deps import ConductorDep, CurrentUserDep
from sentinel_admin_api.schemas import AuditLogResponse

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])


@router.get("", response_model=list[AuditLogResponse])
async def list_audit_logs(
    conductor: ConductorDep,
    _: CurrentUserDep,
    initiator_id: str | None = Query(None),
    target_agent_id: str | None = Query(None),
    outcome: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    return conductor.call(
        {},
        "list_audit_logs",
        initiator_id=initiator_id,
        target_agent_id=target_agent_id,
        outcome=outcome,
        limit=limit,
        offset=offset,
    )
