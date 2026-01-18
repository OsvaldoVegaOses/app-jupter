import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

# Aggressive mocking
with patch.dict('sys.modules', {
    'neo4j': MagicMock(),
    'neo4j.exceptions': MagicMock(),
    'openai': MagicMock(),
    'structlog': MagicMock(),
    'celery': MagicMock(),
    'backend.celery_worker': MagicMock(),
    'python-jose': MagicMock(),
}):
    # Import app
    from backend import app as backend_app
    from fastapi import HTTPException

def test_async_workflow():
    # Mock celery behavior
    mock_task = MagicMock()
    mock_task.id = "task-123"
    
    # Mock task_analyze_interview.delay
    with patch('backend.app.task_analyze_interview') as mock_worker_task, \
         patch('backend.app.load_fragments', return_value=["frag1"]), \
         patch('pathlib.Path.exists', return_value=True), \
         patch('backend.app.resolve_project', return_value="proj1"), \
         patch('backend.app.AsyncResult') as mock_async_result:
        
        mock_worker_task.delay.return_value = mock_task
        
        # 1. Test Dispatch
        payload = backend_app.AnalyzeRequest(
            project="default",
            docx_path="test.docx",
            persist=False
        )
        
        import asyncio
        coro = backend_app.api_analyze(payload, settings=MagicMock(), user=MagicMock())
        resp = asyncio.run(coro)
        
        assert resp["task_id"] == "task-123"
        assert resp["status"] == "queued"
        mock_worker_task.delay.assert_called_once()
        
        # 2. Test Polling
        # Mock AsyncResult behavior
        mock_res_instance = MagicMock()
        mock_res_instance.status = "SUCCESS"
        mock_res_instance.ready.return_value = True
        mock_res_instance.result = {"analysis": "done"}
        mock_async_result.return_value = mock_res_instance
        
        coro_poll = backend_app.get_task_status("task-123", user=MagicMock())
        status_resp = asyncio.run(coro_poll)
        
        assert status_resp["task_id"] == "task-123"
        assert status_resp["status"] == "SUCCESS"
        assert status_resp["result"]["analysis"] == "done"

if __name__ == "__main__":
    try:
        test_async_workflow()
        print("Async Workflow Test Passed!")
    except Exception as e:
        print(f"Async Test Failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
