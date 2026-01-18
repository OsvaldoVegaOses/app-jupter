"""Schemas for Discovery AI Automation.

This module defines Pydantic models for structured LLM responses
in the Discovery analysis workflow.

Sprint 22: JSON contract for discovery synthesis.
Sprint 29+: Adds explicit epistemic status for synthesis statements.
"""

from typing import List, Optional, Dict, Union, Any

from pydantic import BaseModel, Field
from pydantic import ConfigDict, model_validator


class EpistemicStatement(BaseModel):
    """A single statement tagged with epistemic status and optional evidence."""

    type: str = Field(
        ...,
        description="One of: OBSERVATION | INTERPRETATION | HYPOTHESIS | NORMATIVE_INFERENCE",
    )
    text: str = Field(..., description="Statement text (Spanish)")
    evidence_ids: Optional[List[int]] = Field(
        default=None,
        description="Optional list of fragment indices (1..N) that support the statement",
    )


class RefinamientoDiscovery(BaseModel):
    """Sugerencias para refinar la búsqueda Discovery."""
    positivos: List[str] = Field(
        default_factory=list,
        description="Conceptos positivos sugeridos para próxima búsqueda"
    )
    negativos: List[str] = Field(
        default_factory=list,
        description="Conceptos negativos sugeridos para excluir"
    )
    target: Optional[str] = Field(
        default=None,
        description="Texto objetivo sugerido para focalizar"
    )


class DiscoveryAISynthesis(BaseModel):
    """
    Respuesta estructurada del LLM para síntesis de Discovery.
    
    Sprint 22: Contrato JSON para automatizar acciones.
    """
    memo_sintesis: Union[str, List[EpistemicStatement]] = Field(
        ...,
        description=(
            "Síntesis de hallazgos. Puede ser string (legacy) o lista de statements etiquetados "
            "con estatus epistemológico (preferido)."
        ),
    )
    codigos_sugeridos: List[str] = Field(
        ...,
        min_length=1,
        max_length=7,
        description="Lista de códigos emergentes detectados (snake_case)"
    )
    refinamiento_busqueda: RefinamientoDiscovery = Field(
        default_factory=RefinamientoDiscovery,
        description="Sugerencias para iterar la búsqueda"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "memo_sintesis": [
                    {"type": "OBSERVATION", "text": "Se describe presión sobre infraestructura en temporada alta.", "evidence_ids": [1, 3]},
                    {"type": "INTERPRETATION", "text": "Esto sugiere tensión entre turismo y vida cotidiana.", "evidence_ids": [1, 3]},
                    {"type": "HYPOTHESIS", "text": "La identidad cultural aparece como recurso de resistencia simbólica.", "evidence_ids": [2]},
                ],
                "codigos_sugeridos": [
                    "crecimiento_poblacional_percibido",
                    "presion_infraestructura",
                    "identidad_cultural_amenazada"
                ],
                "refinamiento_busqueda": {
                    "positivos": ["migración residencial", "cohesión comunitaria"],
                    "negativos": ["política pública"],
                    "target": "Horcón"
                }
            }
        }


# =============================================================================
# Product artifacts schemas (Sprint 30+: product-grade outputs)
# =============================================================================


class ProductInsightQuery(BaseModel):
    """Suggested query/action backing a product insight.

    We keep this permissive (extra fields allowed) because older insights or
    future features may introduce new keys.
    """

    action: str = Field(..., description="Action to execute: search|analyze|compare|link_prediction|...")
    positivos: List[str] = Field(default_factory=list, description="Positive concepts for search")
    negativos: List[str] = Field(default_factory=list, description="Negative concepts for search")
    codes: List[str] = Field(default_factory=list, description="Codes to compare/merge")
    target: Optional[str] = Field(default=None, description="Optional target text")
    context: Optional[str] = Field(default=None, description="Optional context hint (e.g., axial_coding)")
    min_fragments: Optional[int] = Field(default=None, description="Minimum fragments expected/desired")
    find_cooccurrence: Optional[bool] = Field(default=None, description="Hint to find co-occurrence")
    expand_semantic: Optional[bool] = Field(default=None, description="Hint to broaden semantic search")
    min_score: Optional[float] = Field(default=None, description="Minimum score threshold")

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="after")
    def _validate_query(self) -> "ProductInsightQuery":
        action = (self.action or "").strip().lower()
        if not action:
            raise ValueError("suggested_query.action is required")

        if self.min_fragments is not None and int(self.min_fragments) <= 0:
            raise ValueError("suggested_query.min_fragments must be > 0")

        if self.min_score is not None:
            ms = float(self.min_score)
            if ms < 0.0 or ms > 1.0:
                raise ValueError("suggested_query.min_score must be in [0, 1]")

        # Minimal coupling between action and required params
        if action == "search" and not (self.positivos or []):
            raise ValueError("suggested_query.positivos must be non-empty when action=search")
        if action == "compare" and len(self.codes or []) < 2:
            raise ValueError("suggested_query.codes must have at least 2 items when action=compare")

        return self


class ProductInsightItem(BaseModel):
    """A single product insight, derived from analysis_insights rows."""

    id: Optional[int] = Field(default=None)
    source_type: Optional[str] = Field(default=None)
    source_id: Optional[str] = Field(default=None)
    insight_type: str = Field(..., description="One of: explore|validate|saturate|merge")
    content: str = Field(..., description="Human-readable insight")
    suggested_query: Optional[ProductInsightQuery] = Field(default=None)
    priority: float = Field(default=0.0, description="0..1")
    status: Optional[str] = Field(default=None)
    created_at: Optional[str] = Field(default=None)
    updated_at: Optional[str] = Field(default=None)

    @model_validator(mode="after")
    def _validate_item(self) -> "ProductInsightItem":
        insight_type = (self.insight_type or "").strip().lower()
        allowed = {"explore", "validate", "saturate", "merge"}
        if insight_type not in allowed:
            raise ValueError(f"insight_type must be one of: {', '.join(sorted(allowed))}")

        if not (self.content or "").strip():
            raise ValueError("content must be non-empty")

        pr = float(self.priority)
        if pr < 0.0 or pr > 1.0:
            raise ValueError("priority must be in [0, 1]")

        # Hard validation rule: actionable insights must provide suggested_query.
        if self.suggested_query is None:
            raise ValueError("suggested_query is required for product insights")

        if insight_type == "merge" and len(self.suggested_query.codes or []) < 2:
            raise ValueError("merge insights require suggested_query.codes with at least 2 items")
        if insight_type == "validate" and len(self.suggested_query.positivos or []) < 2:
            raise ValueError("validate insights require suggested_query.positivos with at least 2 items")

        return self


class TopInsightsArtifact(BaseModel):
    """Schema contract for reports/<project>/top_10_insights.json."""

    schema_version: int = Field(1, description="Schema version for this payload")
    project: str
    generated_at: str
    items: List[ProductInsightItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_payload(self) -> "TopInsightsArtifact":
        if len(self.items or []) > 25:
            raise ValueError("items must be <= 25")
        return self
