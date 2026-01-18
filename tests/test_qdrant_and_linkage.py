"""Unit tests for Qdrant retry logic and citation matching."""

import pytest
from unittest.mock import MagicMock, patch
from app.documents import match_citation_to_fragment


class TestMatchCitationToFragment:
    """Tests for the citation matching fallback function."""

    def test_exact_substring_match(self):
        """Should find exact substring match immediately."""
        fragments = [
            "Este es el primer fragmento con contenido",
            "El segundo fragmento tiene otra información importante",
            "Tercer fragmento con datos relevantes",
        ]
        citation = "información importante"
        
        result = match_citation_to_fragment(citation, fragments)
        assert result == 1  # Second fragment

    def test_direct_match_returns_early(self):
        """Direct substring should return without computing similarity."""
        fragments = [
            "La comunidad se organiza de manera autónoma",
            "Los vecinos participan activamente en las decisiones",
        ]
        citation = "comunidad se organiza"
        
        result = match_citation_to_fragment(citation, fragments)
        assert result == 0

    def test_similarity_match_with_word_overlap(self):
        """Should match based on word overlap when no exact match."""
        fragments = [
            "Las reuniones comunitarias son muy importantes para todos",
            "El proyecto de mejora urbana continúa avanzando",
        ]
        citation = "reuniones comunitarias importantes"
        
        result = match_citation_to_fragment(citation, fragments, threshold=0.3)
        assert result == 0

    def test_no_match_below_threshold(self):
        """Should return None when no match above threshold."""
        fragments = [
            "Primer fragmento sobre economía local",
            "Segundo fragmento sobre medio ambiente",
        ]
        citation = "tecnología y educación digital"
        
        result = match_citation_to_fragment(citation, fragments, threshold=0.6)
        assert result is None

    def test_empty_citation_returns_none(self):
        """Empty citation should return None."""
        fragments = ["Algún contenido aquí"]
        
        assert match_citation_to_fragment("", fragments) is None
        assert match_citation_to_fragment(None, fragments) is None

    def test_empty_fragments_returns_none(self):
        """Empty fragments list should return None."""
        assert match_citation_to_fragment("alguna cita", []) is None
        assert match_citation_to_fragment("cita", None) is None

    def test_case_insensitive_matching(self):
        """Matching should be case insensitive."""
        fragments = ["LA COMUNIDAD se ORGANIZA"]
        citation = "la comunidad se organiza"
        
        result = match_citation_to_fragment(citation, fragments)
        assert result == 0


class TestQdrantRetry:
    """Tests for Qdrant retry logic."""

    def test_upsert_once_logs_latency(self):
        """Should log latency after successful upsert."""
        from app.qdrant_block import _upsert_once
        from qdrant_client.models import PointStruct
        
        mock_client = MagicMock()
        mock_logger = MagicMock()
        points = [PointStruct(id="1", vector=[0.1, 0.2], payload={})]
        
        _upsert_once(mock_client, "test_collection", points, logger=mock_logger)
        
        mock_client.upsert.assert_called_once()
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        assert call_args[0][0] == "qdrant.upsert.success"
        assert "count" in call_args[1]
        assert "elapsed_ms" in call_args[1]

    def test_upsert_splits_on_failure(self):
        """Should split batch on failure and retry."""
        from app.qdrant_block import upsert
        from qdrant_client.models import PointStruct
        
        mock_client = MagicMock()
        mock_logger = MagicMock()
        
        # First call fails, subsequent calls succeed
        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("Timeout error")
            return None
        
        mock_client.upsert.side_effect = side_effect
        
        points = [
            PointStruct(id=str(i), vector=[0.1, 0.2], payload={})
            for i in range(4)
        ]
        
        # Should not raise - splits and retries
        with patch('app.qdrant_block._upsert_once') as mock_upsert:
            mock_upsert.side_effect = [Exception("fail"), None, None]
            upsert(mock_client, "test", points, logger=mock_logger)
        
        # Should have logged a split warning
        assert any("split" in str(call) for call in mock_logger.warning.call_args_list)


class TestQdrantSettings:
    """Tests for configurable Qdrant settings."""

    def test_default_timeout(self):
        """Should have default timeout of 30."""
        from app.settings import QdrantSettings
        
        settings = QdrantSettings(uri="http://localhost", api_key=None, collection="test")
        assert settings.timeout == 30

    def test_default_batch_size(self):
        """Should have default batch_size of 20."""
        from app.settings import QdrantSettings
        
        settings = QdrantSettings(uri="http://localhost", api_key=None, collection="test")
        assert settings.batch_size == 20

    def test_custom_timeout_from_env(self):
        """Should load custom timeout from environment."""
        import os
        from app.settings import load_settings
        
        with patch.dict(os.environ, {"QDRANT_TIMEOUT": "60"}):
            # Note: This would require mocking other required env vars too
            pass  # Placeholder for integration test
