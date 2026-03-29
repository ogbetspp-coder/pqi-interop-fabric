from fastapi import APIRouter
from backend.events.outbox import get_events, get_traces_for_run

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/")
def list_events(limit: int = 100):
    return get_events(limit)


@router.get("/run/{run_id}/traces")
def run_traces(run_id: str):
    return get_traces_for_run(run_id)
