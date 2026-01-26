#!/usr/bin/env bash
# CI smoke script (bash)
# - Verifica /healthz
# - Ejecuta checks de servicios (blob, postgres, neo4j, qdrant)
# - Ejecuta smoke_tenant_upload (direct SDK upload)
# - Opcional: encola job async si WORKER_ENABLED=true

set -euo pipefail
ROOT=$(dirname "$0")/..
ROOT=$(cd "$ROOT" && pwd)
cd "$ROOT"

BACKEND_URL=${BACKEND_URL:-http://127.0.0.1:8000}
API_KEY=${API_KEY:-}
API_ORG=${API_KEY_ORG_ID:-}

echo "=== CI SMOKE START ==="

echo "1) Health check: $BACKEND_URL/healthz"
status=$(curl -s -o /dev/stderr -w "%{http_code}" "$BACKEND_URL/healthz" || true)
if [ "$status" != "200" ]; then
  echo "Health check failed: HTTP $status"
  exit 2
fi

echo "2) Services quick checks"
python -m scripts.check_azure_services || { echo "check_azure_services failed"; exit 3; }

echo "3) Tenant SDK upload (smoke)"
python -m scripts.smoke_tenant_upload || { echo "smoke_tenant_upload failed"; exit 4; }

if [ "${WORKER_ENABLED:-false}" = "true" ]; then
  echo "4) Enqueue async transcription job (stream) and poll status"
  if [ -z "$API_KEY" ]; then
    echo "API_KEY is required to enqueue job"; exit 5
  fi
  # Prepare minimal base64 audio (1-second silent WAV) - small precomputed content
  WAV_B64="UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA="
  payload=$(jq -n --arg project smoke_test_project --arg audio_base64 "$WAV_B64" --arg filename "smoke.wav" '{project:$project, audio_base64:$audio_base64, filename:$filename, diarize:false, language:"es", ingest:false}')
  task_resp=$(curl -s -X POST "$BACKEND_URL/api/transcribe/stream" -H "Authorization: Bearer $API_KEY" -H 'Content-Type: application/json' -d "$payload")
  echo "task_resp: $task_resp"
  task_id=$(echo "$task_resp" | jq -r '.task_id')
  if [ -z "$task_id" ] || [ "$task_id" = "null" ]; then
    echo "Failed to start task"; exit 6
  fi
  echo "Polling task $task_id"
  for i in {1..30}; do
    status=$(curl -s -H "Authorization: Bearer $API_KEY" "$BACKEND_URL/api/jobs/$task_id/status" | jq -r '.status')
    echo "status=$status"
    if [ "$status" = "SUCCESS" ] || [ "$status" = "COMPLETED" ] || [ "$status" = "SUCCESS" ]; then
      echo "Task completed"
      break
    fi
    sleep 2
  done
fi

echo "=== CI SMOKE OK ==="
exit 0
