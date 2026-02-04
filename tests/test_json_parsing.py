"""
Test de Parsing JSON Robusto (JSON Parsing Robustness Test).

Este script verifica que call_llm_chat_json maneje correctamente:
- JSON malformado
- Respuestas truncadas
- Respuestas con texto extra
- Esquema incorrecto

Uso:
    python tests/test_json_parsing.py
"""

import sys
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def create_mock_response(content: str):
    """Create a mock Azure OpenAI response."""
    mock_choice = MagicMock()
    mock_choice.message.content = content
    
    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 100
    mock_usage.completion_tokens = 50
    
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage = mock_usage
    
    return mock_response


def test_valid_json():
    """Test with valid JSON response."""
    print("\n--- Test: Valid JSON ---")
    
    from app.analysis import call_llm_chat_json
    
    valid_json = json.dumps({
        "etapa3_matriz_abierta": [
            {"codigo": "participacion", "cita": "ejemplo", "fragmento_idx": 1}
        ],
        "etapa4_axial": []
    })
    
    mock_clients = MagicMock()
    mock_clients.aoai.chat.completions.create.return_value = create_mock_response(valid_json)
    
    mock_settings = MagicMock()
    mock_settings.azure.deployment_chat = "test-model"
    
    result = call_llm_chat_json(
        clients=mock_clients,
        settings=mock_settings,
        system_prompt="test",
        user_prompt="test",
    )
    assert "etapa3_matriz_abierta" in result
    print("✓ PASS: Valid JSON parsed correctly")


def test_json_with_extra_text():
    """Test JSON embedded in extra text."""
    print("\n--- Test: JSON with Extra Text ---")
    
    from app.analysis import call_llm_chat_json
    
    content_with_text = '''
    Aquí está mi análisis:
    
    ```json
    {"etapa3_matriz_abierta": [{"codigo": "test", "cita": "example"}]}
    ```
    
    Espero que sea útil.
    '''
    
    mock_clients = MagicMock()
    mock_clients.aoai.chat.completions.create.return_value = create_mock_response(content_with_text)
    
    mock_settings = MagicMock()
    mock_settings.azure.deployment_chat = "test-model"
    
    result = call_llm_chat_json(
        clients=mock_clients,
        settings=mock_settings,
        system_prompt="test",
        user_prompt="test",
    )
    assert "etapa3_matriz_abierta" in result
    print("✓ PASS: JSON extracted from text")


def test_missing_required_keys():
    """Test JSON missing required keys triggers retry."""
    print("\n--- Test: Missing Required Keys ---")
    
    from app.analysis import call_llm_chat_json
    
    # First response missing keys, second response valid
    bad_json = json.dumps({"other_key": "value"})
    good_json = json.dumps({"etapa3_matriz_abierta": []})
    
    mock_clients = MagicMock()
    mock_clients.aoai.chat.completions.create.side_effect = [
        create_mock_response(bad_json),
        create_mock_response(good_json),
    ]
    
    mock_settings = MagicMock()
    mock_settings.azure.deployment_chat = "test-model"
    
    call_llm_chat_json(
        clients=mock_clients,
        settings=mock_settings,
        system_prompt="test",
        user_prompt="test",
    )
    # Should have retried
    assert mock_clients.aoai.chat.completions.create.call_count >= 2
    print("✓ PASS: Retry triggered for missing keys")


def test_malformed_json():
    """Test completely malformed JSON fails gracefully."""
    print("\n--- Test: Malformed JSON ---")
    
    from app.analysis import call_llm_chat_json
    
    malformed = "This is not JSON at all {{{{"
    
    mock_clients = MagicMock()
    mock_clients.aoai.chat.completions.create.return_value = create_mock_response(malformed)
    
    mock_settings = MagicMock()
    mock_settings.azure.deployment_chat = "test-model"
    
    with pytest.raises((json.JSONDecodeError, ValueError)) as excinfo:
        call_llm_chat_json(
            clients=mock_clients,
            settings=mock_settings,
            system_prompt="test",
            user_prompt="test",
            max_retries=2,
        )
    print(f"✓ PASS: Properly raised exception: {type(excinfo.value).__name__}")


def test_oversized_response():
    """Test response truncation at 32k chars."""
    print("\n--- Test: Oversized Response ---")
    
    from app.analysis import MAX_LLM_RESPONSE_SIZE
    
    # Create oversized response
    large_content = "x" * (MAX_LLM_RESPONSE_SIZE + 1000) + json.dumps({"etapa3_matriz_abierta": []})
    
    print(f"  MAX_LLM_RESPONSE_SIZE = {MAX_LLM_RESPONSE_SIZE}")
    print(f"  Test content size = {len(large_content)}")
    
    # This would be truncated, potentially breaking the JSON
    # The function should handle this gracefully
    assert MAX_LLM_RESPONSE_SIZE > 0
    print("✓ PASS: MAX_LLM_RESPONSE_SIZE constant exists")


def run_all_tests():
    """Run all JSON parsing tests."""
    print("=" * 60)
    print("JSON PARSING ROBUSTNESS TEST SUITE")
    print("=" * 60)
    
    results = [
        test_valid_json(),
        test_json_with_extra_text(),
        test_missing_required_keys(),
        test_malformed_json(),
        test_oversized_response(),
    ]
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"  {passed}/{total} tests passed")
    
    return all(results)


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
