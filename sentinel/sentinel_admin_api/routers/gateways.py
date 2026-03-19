from fastapi import APIRouter, HTTPException, Query, status
from sentinel_admin_api.deps import ConductorDep, CurrentUserDep
from sentinel_admin_api.schemas import GatewayResponse

router = APIRouter(prefix="/gateways", tags=["gateways"])


@router.get("", response_model=list[GatewayResponse])
async def list_gateways(
    conductor: ConductorDep,
    _: CurrentUserDep,
    status_filter: str | None = Query(None, alias="status"),
):
    return conductor.call({}, "list_gateways", status_filter=status_filter)


@router.get("/{gateway_id}", response_model=GatewayResponse)
async def get_gateway(gateway_id: str, conductor: ConductorDep, _: CurrentUserDep):
    result = conductor.call({}, "get_gateway", gateway_id=gateway_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gateway not found")
    return result
