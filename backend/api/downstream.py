from fastapi import APIRouter
from backend.downstream.consumer import get_inbox

router = APIRouter(prefix="/downstream", tags=["downstream"])


@router.get("/inbox")
def list_inbox(limit: int = 50):
    return get_inbox(limit)
