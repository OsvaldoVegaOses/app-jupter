"""
Celery application configuration for background task processing.
"""
from celery import Celery
import os

# Redis URL from environment or default
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:16379/0")

# Create Celery app
celery_app = Celery(
    "transcription_workers",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.tasks"],
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    
    # Concurrency: 5 workers as approved by user
    worker_concurrency=5,
    
    # Task timeouts
    task_soft_time_limit=600,  # 10 min soft limit
    task_time_limit=900,       # 15 min hard limit
    
    # Results expire after 1 hour
    result_expires=3600,
    
    # Prefetch optimization
    worker_prefetch_multiplier=1,
    
    # Task acknowledgment
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)

# Task routing (optional, for future scaling)
celery_app.conf.task_routes = {
    "app.tasks.transcribe_audio_task": {"queue": "transcription"},
}
