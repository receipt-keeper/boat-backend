from fastapi import APIRouter

router = APIRouter(tags=["observability"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
