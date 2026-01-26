"""
Tests para resolve_canonical_code_id() y get_code_id_for_codigo().

TICKET-001: Fase 1.5 Core — Identidad por ID end-to-end
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from typing import Optional, List, Tuple


class MockCursor:
    """Cursor mock que permite configurar resultados por query."""
    
    def __init__(self, results_map: dict = None):
        self._results_map = results_map or {}
        self._current_results: List[Tuple] = []
        self._index = 0
        
    def execute(self, query: str, params: tuple = None):
        # Buscar resultado basado en el code_id del params
        if params and len(params) >= 2:
            key = params[1]  # project_id, code_id o codigo
            if key in self._results_map:
                self._current_results = self._results_map[key]
            else:
                self._current_results = []
        else:
            self._current_results = []
        self._index = 0
            
    def fetchone(self) -> Optional[Tuple]:
        if self._current_results:
            return self._current_results[0] if isinstance(self._current_results[0], tuple) else self._current_results
        return None
    
    def fetchall(self) -> List[Tuple]:
        return self._current_results if isinstance(self._current_results, list) else [self._current_results]
    
    def close(self):
        pass
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        pass


class MockConnection:
    """Conexión mock configurable."""
    
    def __init__(self, results_map: dict = None):
        self._results_map = results_map or {}
        
    def cursor(self):
        return MockCursor(self._results_map)
    
    def commit(self):
        pass
    
    def close(self):
        pass


@pytest.fixture
def mock_pg_canonical():
    """
    Mock connection para código canónico (sin puntero).
    code_id=42, canonical_code_id=NULL, status='active'
    """
    return MockConnection({
        42: (42, None, "active"),  # (code_id, canonical_code_id, status)
    })


@pytest.fixture
def mock_pg_merged():
    """
    Mock connection para código merged.
    code_id=10 → canonical_code_id=42
    code_id=42 es canónico
    """
    return MockConnection({
        10: (10, 42, "merged"),
        42: (42, None, "active"),
    })


@pytest.fixture
def mock_pg_chain():
    """
    Mock connection para cadena de 3 niveles.
    code_id=5 → 10 → 42 (canónico)
    """
    return MockConnection({
        5: (5, 10, "merged"),
        10: (10, 42, "merged"),
        42: (42, None, "active"),
    })


@pytest.fixture
def mock_pg_self_canonical():
    """
    Mock connection para self-canonical.
    code_id=50, canonical_code_id=50 (self-pointing)
    """
    return MockConnection({
        50: (50, 50, "active"),
    })


@pytest.fixture
def mock_pg_cycle():
    """
    Mock connection para ciclo (A→B→A).
    code_id=100 → 101 → 100
    """
    return MockConnection({
        100: (100, 101, "merged"),
        101: (101, 100, "merged"),
    })


@pytest.fixture
def mock_pg_empty():
    """Mock connection sin datos."""
    return MockConnection({})


class TestResolveCanonicalCodeId:
    """Tests para resolve_canonical_code_id()."""
    
    def test_canonical_returns_self(self, mock_pg_canonical):
        """Código canónico (sin puntero) retorna sí mismo."""
        from app.postgres_block import resolve_canonical_code_id
        
        with patch("app.postgres_block.ensure_codes_catalog_table"):
            result = resolve_canonical_code_id(mock_pg_canonical, "jd-007", 42)
        
        assert result == 42
    
    def test_merged_returns_canonical(self, mock_pg_merged):
        """Código merged retorna el canónico final."""
        from app.postgres_block import resolve_canonical_code_id
        
        with patch("app.postgres_block.ensure_codes_catalog_table"):
            result = resolve_canonical_code_id(mock_pg_merged, "jd-007", 10)
        
        assert result == 42
    
    def test_chain_resolves_to_final(self, mock_pg_chain):
        """Cadena de 3 niveles resuelve al canónico final."""
        from app.postgres_block import resolve_canonical_code_id
        
        with patch("app.postgres_block.ensure_codes_catalog_table"):
            result = resolve_canonical_code_id(mock_pg_chain, "jd-007", 5)
        
        assert result == 42
    
    def test_self_canonical_returns_self(self, mock_pg_self_canonical):
        """Self-canonical (canonical_code_id = code_id) retorna sí mismo."""
        from app.postgres_block import resolve_canonical_code_id
        
        with patch("app.postgres_block.ensure_codes_catalog_table"):
            result = resolve_canonical_code_id(mock_pg_self_canonical, "jd-007", 50)
        
        assert result == 50
    
    def test_nonexistent_returns_none(self, mock_pg_empty):
        """code_id inexistente retorna None."""
        from app.postgres_block import resolve_canonical_code_id
        
        with patch("app.postgres_block.ensure_codes_catalog_table"):
            result = resolve_canonical_code_id(mock_pg_empty, "jd-007", 99999)
        
        assert result is None
    
    def test_cycle_returns_none(self, mock_pg_cycle):
        """Ciclo detectado retorna None sin loop infinito."""
        from app.postgres_block import resolve_canonical_code_id
        
        with patch("app.postgres_block.ensure_codes_catalog_table"):
            # Debe terminar sin loop infinito
            result = resolve_canonical_code_id(mock_pg_cycle, "jd-007", 100)
        
        assert result is None
    
    def test_none_input_returns_none(self, mock_pg_empty):
        """code_id=None retorna None."""
        from app.postgres_block import resolve_canonical_code_id
        
        with patch("app.postgres_block.ensure_codes_catalog_table"):
            result = resolve_canonical_code_id(mock_pg_empty, "jd-007", None)
        
        assert result is None


class TestGetCodeIdForCodigo:
    """Tests para get_code_id_for_codigo()."""
    
    def test_existing_code_returns_id(self):
        """Código existente retorna su code_id."""
        from app.postgres_block import get_code_id_for_codigo
        
        mock_pg = MockConnection({
            "resiliencia": (42,),
        })
        
        with patch("app.postgres_block.ensure_codes_catalog_table"):
            result = get_code_id_for_codigo(mock_pg, "jd-007", "resiliencia")
        
        assert result == 42
    
    def test_nonexistent_code_returns_none(self):
        """Código inexistente retorna None."""
        from app.postgres_block import get_code_id_for_codigo
        
        mock_pg = MockConnection({})
        
        with patch("app.postgres_block.ensure_codes_catalog_table"):
            result = get_code_id_for_codigo(mock_pg, "jd-007", "no_existe")
        
        assert result is None
    
    def test_empty_string_returns_none(self):
        """String vacío retorna None."""
        from app.postgres_block import get_code_id_for_codigo
        
        mock_pg = MockConnection({})
        
        with patch("app.postgres_block.ensure_codes_catalog_table"):
            result = get_code_id_for_codigo(mock_pg, "jd-007", "")
        
        assert result is None
    
    def test_none_input_returns_none(self):
        """codigo=None retorna None."""
        from app.postgres_block import get_code_id_for_codigo
        
        mock_pg = MockConnection({})
        
        with patch("app.postgres_block.ensure_codes_catalog_table"):
            result = get_code_id_for_codigo(mock_pg, "jd-007", None)
        
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
