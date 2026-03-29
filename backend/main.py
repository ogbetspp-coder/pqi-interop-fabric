"""FastAPI entry point for the PQI Interoperability Fabric backend."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import sources, engine, events, downstream
from backend.engine import hapi_client

app = FastAPI(
    title="PQI Interoperability Fabric",
    description="Canonical PQI engine + source domains + downstream consumer",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sources.router)
app.include_router(engine.router)
app.include_router(events.router)
app.include_router(downstream.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/fhir/metadata")
def fhir_metadata():
    """Proxy HAPI metadata through backend so UI never calls HAPI directly."""
    return hapi_client.get_metadata()
