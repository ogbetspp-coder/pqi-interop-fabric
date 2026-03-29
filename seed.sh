#!/bin/sh
# Bring up the full stack and run initial canonicalization.
# Run once after cloning. Safe to re-run (reset is handled by the engine).

set -eu

echo "Starting services..."
docker compose up -d

echo "Waiting for Postgres..."
until docker compose exec -T postgres pg_isready -U pqi -d pqi_fabric > /dev/null 2>&1; do
  sleep 2
done

echo "Waiting for HAPI FHIR..."
until curl -sf http://localhost:8080/fhir/metadata > /dev/null 2>&1; do
  sleep 5
done

echo "Waiting for backend..."
until curl -sf http://localhost:8000/health > /dev/null 2>&1; do
  sleep 3
done

echo "Running initial canonicalization..."
curl -sf -X POST http://localhost:8000/engine/run | \
  python3 -c "import json,sys; r=json.load(sys.stdin); print(f\"  created: {r['summary']['created']}, skipped: {r['summary']['skipped']}\")"

echo ""
echo "Done. Open http://localhost:8501 to view the demo."
