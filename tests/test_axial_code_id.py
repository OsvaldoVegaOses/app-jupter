"""
Tests para TICKET-003: Axialidad por ID + sync Neo4j.

Verifica que las funciones axiales soportan code_id para identidad estable.
"""

import pytest
from unittest.mock import MagicMock, patch, call
from typing import Optional


class TestMergeCategoryCodeRelationshipCodeId:
    """Tests para merge_category_code_relationship con code_id."""

    def test_accepts_code_id_parameter(self):
        """Verifica que la función acepta el parámetro code_id."""
        from app.neo4j_block import merge_category_code_relationship
        import inspect
        
        sig = inspect.signature(merge_category_code_relationship)
        param_names = list(sig.parameters.keys())
        
        assert "code_id" in param_names, "merge_category_code_relationship debe aceptar parámetro code_id"
    
    def test_code_id_is_optional(self):
        """Verifica que code_id tiene valor por defecto None."""
        from app.neo4j_block import merge_category_code_relationship
        import inspect
        
        sig = inspect.signature(merge_category_code_relationship)
        code_id_param = sig.parameters.get("code_id")
        
        assert code_id_param is not None
        assert code_id_param.default is None, "code_id debe tener default None"

    @patch("app.neo4j_block.Driver")
    def test_uses_code_id_in_merge_when_provided(self, mock_driver_class):
        """Verifica que cuando code_id está presente, se usa en el MERGE."""
        from app.neo4j_block import merge_category_code_relationship
        
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
        
        merge_category_code_relationship(
            driver=mock_driver,
            database="neo4j",
            categoria="test_cat",
            codigo="test_code",
            relacion="partede",
            evidencia=["frag1", "frag2"],
            memo="test memo",
            project_id="test-project",
            code_id=42,
        )
        
        # Verificar que session.run fue llamado
        assert mock_session.run.called
        call_args = mock_session.run.call_args
        
        # El cypher debe contener code_id en el MERGE
        cypher = call_args[0][0] if call_args[0] else call_args.kwargs.get("query", "")
        assert "code_id" in cypher.lower(), "Cypher debe incluir code_id cuando está presente"
        
        # Verificar que code_id=42 fue pasado como parámetro
        kwargs = call_args[1] if len(call_args) > 1 else call_args.kwargs
        assert kwargs.get("code_id") == 42, "code_id debe pasarse al query"


class TestAssignAxialRelationCodeId:
    """Tests para assign_axial_relation con code_id."""

    def test_returns_code_id_in_payload(self):
        """Verifica que assign_axial_relation incluye code_id en el payload de retorno."""
        import inspect
        from pathlib import Path
        
        # Leer el source directamente sin importar el módulo
        axial_path = Path(__file__).parent.parent / "app" / "axial.py"
        source = axial_path.read_text(encoding="utf-8")
        
        assert '"code_id":' in source or "'code_id':" in source, \
            "assign_axial_relation debe incluir code_id en el payload de retorno"

    def test_imports_code_id_functions(self):
        """Verifica que axial.py importa las funciones necesarias de postgres_block."""
        from pathlib import Path
        
        # Leer el source directamente sin importar el módulo
        axial_path = Path(__file__).parent.parent / "app" / "axial.py"
        source = axial_path.read_text(encoding="utf-8")
        
        assert 'get_code_id_for_codigo' in source, \
            "axial debe importar get_code_id_for_codigo"
        assert 'resolve_canonical_code_id' in source, \
            "axial debe importar resolve_canonical_code_id"


class TestMergeCategoryCodeRelationshipsCodeId:
    """Tests para merge_category_code_relationships (batch) con code_id."""

    def test_handles_rows_with_code_id(self):
        """Verifica que la función batch maneja rows con code_id."""
        from app.neo4j_block import merge_category_code_relationships
        import inspect
        
        source = inspect.getsource(merge_category_code_relationships)
        
        assert "code_id" in source, \
            "merge_category_code_relationships debe manejar code_id"

    @patch("app.neo4j_block.Driver")
    def test_batch_with_mixed_code_ids(self, mock_driver_class):
        """Verifica que el batch maneja mezcla de rows con y sin code_id."""
        from app.neo4j_block import merge_category_code_relationships
        
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
        
        rows = [
            {
                "categoria": "cat1",
                "codigo": "code1",
                "relacion": "partede",
                "evidencia": ["f1"],
                "memo": None,
                "project_id": "proj",
                "code_id": 100,
            },
            {
                "categoria": "cat2",
                "codigo": "code2",
                "relacion": "causa",
                "evidencia": ["f2"],
                "memo": None,
                "project_id": "proj",
                "code_id": None,  # Sin code_id
            },
        ]
        
        # No debe lanzar excepción
        merge_category_code_relationships(
            driver=mock_driver,
            database="neo4j",
            rows=rows,
        )
        
        assert mock_session.run.called


class TestEnsureCodeConstraintsIndex:
    """Tests para el índice de code_id en Neo4j."""

    def test_creates_code_id_index(self):
        """Verifica que ensure_code_constraints crea índice para code_id."""
        from app.neo4j_block import ensure_code_constraints
        import inspect
        
        source = inspect.getsource(ensure_code_constraints)
        
        assert "code_id" in source, \
            "ensure_code_constraints debe crear índice para code_id"
        assert "CREATE INDEX" in source or "CREATE index" in source.lower(), \
            "ensure_code_constraints debe crear un INDEX para code_id"
