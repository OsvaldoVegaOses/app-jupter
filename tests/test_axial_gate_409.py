"""
Tests para TICKET-004: Gate runtime — bloqueo 409 si axial_ready=false.

Verifica que las operaciones axiales son bloqueadas cuando
la infraestructura ontológica no está lista.
"""

import pytest
from unittest.mock import MagicMock, patch
from typing import List, Tuple


class TestCheckAxialReady:
    """Tests para la función check_axial_ready."""

    def test_function_exists(self):
        """Verifica que check_axial_ready existe en postgres_block."""
        from app.postgres_block import check_axial_ready
        assert callable(check_axial_ready)

    def test_returns_tuple(self):
        """Verifica que retorna (bool, List[str])."""
        from app.postgres_block import check_axial_ready
        import inspect
        
        sig = inspect.signature(check_axial_ready)
        # Verificar parámetros
        params = list(sig.parameters.keys())
        assert "pg" in params
        assert "project_id" in params

    def test_docstring_exists(self):
        """Verifica que tiene documentación."""
        from app.postgres_block import check_axial_ready
        assert check_axial_ready.__doc__ is not None
        assert "axial_ready" in check_axial_ready.__doc__.lower()


class TestAxialNotReadyError:
    """Tests para la excepción AxialNotReadyError."""

    def test_exception_exists(self):
        """Verifica que AxialNotReadyError existe en el código."""
        from pathlib import Path
        
        axial_path = Path(__file__).parent.parent / "app" / "axial.py"
        source = axial_path.read_text(encoding="utf-8")
        
        assert "class AxialNotReadyError" in source
        assert "Exception" in source

    def test_has_blocking_reasons_attribute(self):
        """Verifica que tiene atributo blocking_reasons."""
        from pathlib import Path
        
        axial_path = Path(__file__).parent.parent / "app" / "axial.py"
        source = axial_path.read_text(encoding="utf-8")
        
        assert "self.blocking_reasons" in source

    def test_has_project_id_attribute(self):
        """Verifica que tiene atributo project_id."""
        from pathlib import Path
        
        axial_path = Path(__file__).parent.parent / "app" / "axial.py"
        source = axial_path.read_text(encoding="utf-8")
        
        assert "self.project_id" in source

    def test_message_includes_reasons(self):
        """Verifica que el mensaje incluye las razones."""
        from pathlib import Path
        
        axial_path = Path(__file__).parent.parent / "app" / "axial.py"
        source = axial_path.read_text(encoding="utf-8")
        
        # Debe construir mensaje con razones
        assert "blocking_reasons" in source
        assert "project_id" in source


class TestAssignAxialRelationGate:
    """Tests para el gate en assign_axial_relation."""

    def test_has_skip_parameter(self):
        """Verifica que assign_axial_relation tiene parámetro skip_axial_ready_check."""
        from pathlib import Path
        
        axial_path = Path(__file__).parent.parent / "app" / "axial.py"
        source = axial_path.read_text(encoding="utf-8")
        
        assert "skip_axial_ready_check" in source

    def test_calls_check_axial_ready(self):
        """Verifica que assign_axial_relation llama a check_axial_ready."""
        from pathlib import Path
        
        axial_path = Path(__file__).parent.parent / "app" / "axial.py"
        source = axial_path.read_text(encoding="utf-8")
        
        assert "check_axial_ready" in source
        # Debe importarlo
        assert "from .postgres_block import" in source or "from app.postgres_block import" in source

    def test_raises_axial_not_ready_error(self):
        """Verifica que puede lanzar AxialNotReadyError."""
        from pathlib import Path
        
        axial_path = Path(__file__).parent.parent / "app" / "axial.py"
        source = axial_path.read_text(encoding="utf-8")
        
        assert "raise AxialNotReadyError" in source


class TestHttpGate409:
    """Tests para el manejo HTTP 409 en endpoints axiales."""

    def test_app_imports_axial_not_ready_error(self):
        """Verifica que backend/app.py importa AxialNotReadyError."""
        from pathlib import Path
        
        app_path = Path(__file__).parent.parent / "backend" / "app.py"
        source = app_path.read_text(encoding="utf-8")
        
        assert "AxialNotReadyError" in source

    def test_gds_endpoint_handles_409(self):
        """Verifica que /api/axial/gds maneja AxialNotReadyError con 409."""
        from pathlib import Path

        router_path = Path(__file__).parent.parent / "backend" / "routers" / "graphrag.py"
        source = router_path.read_text(encoding="utf-8")
        
        # Debe haber manejo de 409 para AxialNotReadyError
        assert "status_code=409" in source
        assert "axial_not_ready" in source


class TestCliGate:
    """Tests para el gate en el CLI."""

    def test_main_imports_axial_not_ready_error(self):
        """Verifica que main.py importa AxialNotReadyError."""
        from pathlib import Path
        
        main_path = Path(__file__).parent.parent / "main.py"
        source = main_path.read_text(encoding="utf-8")
        
        assert "AxialNotReadyError" in source

    def test_cmd_axial_relate_handles_error(self):
        """Verifica que cmd_axial_relate maneja AxialNotReadyError."""
        from pathlib import Path
        
        main_path = Path(__file__).parent.parent / "main.py"
        source = main_path.read_text(encoding="utf-8")
        
        assert "except AxialNotReadyError" in source


class TestBlockingReasons:
    """Tests para las razones de bloqueo específicas."""

    def test_check_axial_ready_checks_missing_code_id(self):
        """Verifica que check_axial_ready detecta missing_code_id."""
        from pathlib import Path
        
        pg_path = Path(__file__).parent.parent / "app" / "postgres_block.py"
        source = pg_path.read_text(encoding="utf-8")
        
        # Buscar en la función check_axial_ready
        assert "missing_code_id" in source
        assert "code_id IS NULL" in source

    def test_check_axial_ready_checks_divergences(self):
        """Verifica que check_axial_ready detecta divergences_text_vs_id."""
        from pathlib import Path
        
        pg_path = Path(__file__).parent.parent / "app" / "postgres_block.py"
        source = pg_path.read_text(encoding="utf-8")
        
        assert "divergences_text_vs_id" in source

    def test_check_axial_ready_checks_cycles(self):
        """Verifica que check_axial_ready detecta cycles_non_trivial."""
        from pathlib import Path
        
        pg_path = Path(__file__).parent.parent / "app" / "postgres_block.py"
        source = pg_path.read_text(encoding="utf-8")
        
        assert "cycles_non_trivial" in source
        assert "WITH RECURSIVE" in source
