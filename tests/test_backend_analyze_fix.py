import sys
from unittest.mock import MagicMock, patch
from pathlib import Path
import pytest

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

# Mock fastAPI and others before importing app
# Mock fastAPI and others before importing app
with patch.dict('sys.modules', {
    'fastapi': MagicMock(),
    'fastapi.middleware.cors': MagicMock(),
    'fastapi.responses': MagicMock(),
    'neo4j': MagicMock(),
    'neo4j.exceptions': MagicMock(),
    'openai': MagicMock(),
    'structlog': MagicMock(),
    'pydantic': MagicMock(),
    'dotenv': MagicMock(),
}):
    import backend.app as backend_app

def test_api_analyze_calls_with_list():
    # Mock dependencies
    mock_settings = MagicMock()
    mock_clients = MagicMock()
    mock_clients.postgres = MagicMock()
    mock_user = MagicMock()
    mock_user.user_id = "test-user"
    mock_request = MagicMock()
    mock_request.state = MagicMock(request_id="req-1")
    
    # Mock internal functions
    with patch('backend.app.load_fragments') as mock_load, \
         patch('app.analysis.analyze_interview_text') as mock_analyze, \
         patch('backend.app.stage0_require_ready_or_override', return_value=None), \
         patch('app.postgres_block.count_pending_candidates', return_value=0), \
         patch('app.coding.get_all_codes_for_project', return_value=[]), \
         patch('app.reports.generate_interview_report', return_value=MagicMock(to_dict=lambda: {})), \
         patch('app.reports.save_interview_report', return_value=None), \
         patch('pathlib.Path.exists', return_value=True):
        
        # Setup returns
        mock_load.return_value = ["Fragment 1", "Fragment 2"]
        mock_analyze.return_value = {"status": "ok"}
        
        # Create payload
        payload = backend_app.AnalyzeRequest(
            project="default",
            docx_path="test.docx",
            persist=False
        )
        
        # Execute handler (we need to run it as async check if possible, or just call the logic)
        # Since it's async, we use pytest-asyncio or just inspect the logic if we mock enough?
        # Let's try to invoke it directly. We might need 'await' if it's async.
        import asyncio
        
        # We need to bypass dependencies injection
        coroutine = backend_app.api_analyze(
            payload,
            request=mock_request,
            settings=mock_settings,
            clients=mock_clients,
            user=mock_user,
        )
        
        # In a real test we'd use pytest-asyncio, here we manually drive it if simple
        asyncio.run(coroutine)

        # Verification
        # The key check: Did we pass the list ["Fragment 1"] or the string "Fragment 1..."?
        args, _ = mock_analyze.call_args
        passed_fragments = args[2] # arg 0=clients, 1=settings, 2=fragments
        
        print(f"Passed type: {type(passed_fragments)}")
        if isinstance(passed_fragments, list):
            print("SUCCESS: Passed a list.")
        else:
            print("FAILURE: Passed a string (or other).")
            raise AssertionError("Did not pass a list to analyze_interview_text")

if __name__ == "__main__":
    try:
        test_api_analyze_calls_with_list()
        print("Test verified successfully.")
    except Exception as e:
        print(f"Test failed: {e}")
        sys.exit(1)
