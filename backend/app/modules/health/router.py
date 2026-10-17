from fastapi import APIRouter

router = APIRouter()


@router.get("")
async def api_health_check() -> dict[str, str]:
    return {"status": "ok"}
