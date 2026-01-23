import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

# Skip this test module - auth was refactored to routers
pytest.skip(
    "test_auth.py is deprecated - auth endpoints moved to backend/routers/auth.py. "
    "Use integration tests with TestClient instead.",
    allow_module_level=True
)

def test_token_flow():
    # 1. Generate token
    form = OAuth2PasswordRequestForm(username="testuser", password="pwd", scope=None, grant_type=None)
    
    # We need to run the async function
    import asyncio
    
    # login_for_access_token is simple logic, let's run it
    coro = login_for_access_token(form)
    token_resp = asyncio.run(coro)
    
    assert "access_token" in token_resp
    assert token_resp["token_type"] == "bearer"
    token = token_resp["access_token"]
    
    # 2. Verify token
    # require_auth calls get_current_user
    # We can call auth.verify_token directly
    data = auth.verify_token(token)
    assert data.sub == "testuser"
    assert data.org == "default_org"

def test_require_auth_logic():
    # Test verify_token raises error on bad token
    with pytest.raises(HTTPException):
        auth.verify_token("badtoken")

if __name__ == "__main__":
    try:
        test_token_flow()
        test_require_auth_logic()
        print("Auth Tests Passed!")
    except Exception as e:
        print(f"Auth Test Failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
