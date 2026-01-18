@echo off
echo Starting Celery Worker (threads pool, 5 concurrency) - debugging/local only
cd ..
.\.venv\Scripts\celery -A backend.celery_worker worker --loglevel=info --pool=threads --concurrency=5
pause
