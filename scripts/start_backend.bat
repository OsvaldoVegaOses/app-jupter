@echo off
echo Starting FastAPI Backend...
cd ..
.\.venv\Scripts\uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000
pause
