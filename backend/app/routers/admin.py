from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.repositories import ImportBatchRepository

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/features")
async def features():
    return {"data_reset": settings.allow_data_reset}


@router.post("/reset")
async def reset_all_data(db: AsyncSession = Depends(get_db)):
    """Delete every transaction and import batch. Categories and budget
    targets are kept. Only available when ALLOW_DATA_RESET is set (dev)."""
    if not settings.allow_data_reset:
        raise HTTPException(status_code=403, detail="Data reset is disabled in this environment")

    deleted = await ImportBatchRepository(db).delete_all_with_transactions()
    return {"ok": True, "deleted": deleted}
