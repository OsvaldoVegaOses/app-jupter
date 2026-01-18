---
description: Checklist before adding any new feature to the project
---

# New Feature Checklist

## Step 1: Understand the Request

1. What module does this affect? (See `agents.md`)
2. Does it require:
   - [ ] New API endpoint?
   - [ ] New frontend component?
   - [ ] Database schema changes?
   - [ ] New environment variables?

## Step 2: Backend Implementation (if needed)

### Adding New Endpoint

1. Check if similar endpoint exists (avoid duplicates)

2. Add endpoint at the END of `backend/app.py` (before candidate endpoints)

3. Use standard pattern:
   ```python
   @app.get("/api/your-endpoint")
   async def your_endpoint(
       settings: AppSettings = Depends(get_settings),
       user: User = Depends(require_auth),  # if authenticated
   ) -> Dict[str, Any]:
       # Your logic here
       return {"result": "data"}
   ```

4. If you need functions from `app/` modules:
   - Add import at line ~140-150 of `backend/app.py`
   - Use pattern: `from app.module import function1, function2`

// turbo
5. Test immediately: `curl -H "X-API-Key: dev-key" http://localhost:8000/api/your-endpoint`
5. Test immediately: `curl -H "X-API-Key: dev-key" http://localhost:8000/api/your-endpoint`

## Step 3: Frontend Implementation (if needed)

### Adding New Component

1. Create `frontend/src/components/YourComponent.tsx`

2. Add types at the top of the file

3. Include loading and error states:
   ```tsx
   const [loading, setLoading] = useState(false);
   const [error, setError] = useState<string | null>(null);
   ```

4. Add CSS at END of `frontend/src/App.css`

5. Import and render in `frontend/src/App.tsx`

### Adding API Function

1. Add to `frontend/src/services/api.ts`:
   ```typescript
   export async function yourApiCall(params: YourType): Promise<ResponseType> {
     const res = await apiFetch('/api/your-endpoint', {
       method: 'POST',
       body: JSON.stringify(params),
     });
     return res.json();
   }
   ```

## Step 4: Verification

// turbo
1. Backend health: `curl http://localhost:8000/healthz`
1. Backend health: `curl http://localhost:8000/healthz`

2. Open browser, check console for errors

3. Test the new feature manually

4. Verify no regression in existing features

## Step 5: Documentation

1. Update `agents.md` if new module/component added
2. Update relevant docs in `docs/` folder if needed
