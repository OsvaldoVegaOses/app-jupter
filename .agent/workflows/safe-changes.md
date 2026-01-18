---
description: How to safely make code changes without breaking the pipeline
---

# Safe Code Changes Workflow

## Pre-Flight Checks

// turbo
1. Verify backend is running: `curl http://localhost:8000/healthz`

2. Read `CLAUDE.md` for project rules

3. Read `agents.md` to understand module responsibilities

## Before Any Backend Change

1. Check if the function/endpoint already exists:
   ```bash
   grep -r "function_name" app/ backend/
   ```

2. Verify imports are correct in `backend/app.py`:
   - Line ~100-150 contains all imports from `app/` modules
   - Use `from app.module import function`

3. Check settings structure - use NESTED attributes:
   ```python
   # CORRECT:
   settings.postgres.host
   settings.azure.api_key
   settings.qdrant.collection
   
   # WRONG:
   settings.pghost  # Does not exist!
   settings.azure_openai_api_key  # Does not exist!
   ```

## Before Any Frontend Change

1. Verify `frontend/.env` has correct port:
   ```
   VITE_API_BASE=http://127.0.0.1:8000
   ```

2. Check if API function exists in `frontend/src/services/api.ts`

3. If adding new component:
   - Create file in `frontend/src/components/`
   - Add CSS at END of `frontend/src/App.css`
   - Import in `frontend/src/App.tsx`

## Post-Change Verification

1. Check backend still responds: `curl http://localhost:8000/healthz`

2. Check browser console for errors

3. If you modified backend/app.py, test the specific endpoint:
   ```bash
   curl -H "X-API-Key: dev-key" http://localhost:8000/api/YOUR_ENDPOINT
   ```

## Rollback Plan

If something breaks:
1. Check the error message in terminal/console
2. Compare with working version using git diff
3. Revert the specific change that caused the issue
