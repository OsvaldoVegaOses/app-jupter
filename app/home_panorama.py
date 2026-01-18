from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple


def _safe_int(value: Any, default: int = 0) -> int:
	try:
		if value is None:
			return default
		return int(value)
	except Exception:
		return default


def _safe_float(value: Any, default: float = 0.0) -> float:
	try:
		if value is None:
			return default
		return float(value)
	except Exception:
		return default


def _first_incomplete_stage(
	validated: Optional[Dict[str, Any]],
	*,
	stage_order: Sequence[str],
) -> Tuple[Optional[str], Optional[str]]:
	stages = (validated or {}).get("stages") if isinstance(validated, dict) else None
	stages = stages if isinstance(stages, dict) else {}

	for key in stage_order:
		entry = stages.get(key) or {}
		if not bool(entry.get("completed")):
			label = entry.get("label") or key
			return key, str(label)

	if stage_order:
		key = stage_order[-1]
		entry = stages.get(key) or {}
		label = entry.get("label") or key
		return key, str(label)
	return None, None


def compute_axial_gate(
	*,
	observed: Optional[Dict[str, Any]],
	saturation: Optional[Dict[str, Any]],
	config: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
	observed = observed if isinstance(observed, dict) else {}
	config = config if isinstance(config, dict) else {}

	coverage_percent = _safe_float(((observed.get("codificacion") or {}).get("porcentaje_cobertura")), 0.0)
	axial_rel = _safe_int(((observed.get("axial") or {}).get("relaciones")), 0)

	policy = str(config.get("axial_gate_policy") or "auto").strip().lower()
	min_coverage = _safe_float(config.get("axial_min_coverage_percent"), 70.0)
	manual_unlocked = bool(config.get("axial_manual_unlocked") or False)

	plateau = False
	if isinstance(saturation, dict):
		plateau = bool(((saturation.get("summary") or {}).get("saturacion_alcanzada")) or False)

	if axial_rel > 0:
		return {
			"status": "unlocked",
			"policy_used": "observed",
			"reasons": ["Ya existen relaciones axiales en el proyecto."],
			"unlock_hint": None,
			"metrics": {
				"coverage_percent": coverage_percent,
				"axial_relaciones": axial_rel,
				"saturation_plateau": plateau,
				"min_coverage_percent": min_coverage,
			},
		}

	policy_used = policy
	if policy == "auto":
		policy_used = "saturation" if plateau and coverage_percent >= 30.0 else "coverage"

	unlocked = False
	reasons: List[str] = []
	unlock_hint: Optional[str] = None

	if policy_used == "manual":
		unlocked = manual_unlocked
		if not unlocked:
			reasons.append("Bloqueo axial configurado en modo manual.")
			unlock_hint = "Activa el desbloqueo manual en Configuración del proyecto."
	elif policy_used == "saturation":
		unlocked = bool(plateau) and coverage_percent >= 30.0
		if not plateau:
			reasons.append("Aún no se detecta plateau de saturación (no se alcanzó saturación teórica).")
		if coverage_percent < 30.0:
			reasons.append("Cobertura demasiado baja para iniciar Axial incluso con saturación.")
		if not unlocked:
			unlock_hint = "Continúa codificando hasta detectar plateau o aumenta cobertura mínima (≥30%)."
	else:
		unlocked = coverage_percent >= min_coverage
		if not unlocked:
			reasons.append(f"Cobertura de codificación abierta por debajo del umbral ({coverage_percent:.1f}% < {min_coverage:.1f}%).")
			unlock_hint = "Codifica más fragmentos (Etapa 3) o ajusta el umbral en Configuración del proyecto."

	if unlocked:
		reasons = ["Condiciones cumplidas para iniciar Codificación Axial.", *(reasons or [])]

	return {
		"status": "unlocked" if unlocked else "locked",
		"policy_used": policy_used,
		"reasons": reasons,
		"unlock_hint": unlock_hint,
		"metrics": {
			"coverage_percent": coverage_percent,
			"axial_relaciones": axial_rel,
			"saturation_plateau": plateau,
			"min_coverage_percent": min_coverage,
		},
	}


def compute_primary_actions(
	*,
	project: str,
	current_stage_key: Optional[str],
	current_stage_label: Optional[str],
	observed: Optional[Dict[str, Any]],
	pending_total: int,
	pending_in_recommended: Optional[int],
	recommended_archivo: Optional[str],
	axial_gate: Dict[str, Any],
) -> Dict[str, Any]:
	observed = observed if isinstance(observed, dict) else {}
	ingesta = observed.get("ingesta") or {}
	fam = observed.get("familiarizacion") or {}
	cand = observed.get("candidatos") or {}
	cod = observed.get("codificacion") or {}

	archivos = _safe_int(ingesta.get("archivos"), 0)
	analizables = _safe_int(ingesta.get("fragmentos_analizables"), 0)

	entrevistas_revisadas = _safe_int(fam.get("entrevistas_revisadas"), 0)
	entrevistas_totales = _safe_int(fam.get("entrevistas_totales"), 0)

	candidates_pending = _safe_int(cand.get("pendientes"), 0)
	coverage_percent = _safe_float(cod.get("porcentaje_cobertura"), 0.0)

	actions: List[Dict[str, Any]] = []

	def add_action(
		*,
		action_id: str,
		label: str,
		view: str,
		subview: Optional[str],
		reason: str,
		score: float,
		params: Optional[Dict[str, Any]] = None,
	) -> None:
		actions.append(
			{
				"id": action_id,
				"label": label,
				"view": view,
				"subview": subview,
				"params": params or {},
				"reason": reason,
				"score": round(float(score), 3),
			}
		)

	if archivos <= 0 or analizables <= 0:
		add_action(
			action_id="ingest",
			label="Ingestar entrevistas",
			view="proceso",
			subview=None,
			reason="No hay fragmentos analizables en el proyecto.",
			score=1000.0,
		)
	elif entrevistas_totales > 0 and entrevistas_revisadas < entrevistas_totales:
		remaining = max(entrevistas_totales - entrevistas_revisadas, 0)
		add_action(
			action_id="familiarization",
			label=f"Continuar Familiarización ({entrevistas_revisadas}/{entrevistas_totales})",
			view="proceso",
			subview=None,
			reason=f"Faltan {remaining} entrevistas por revisar antes de consolidar codificación.",
			score=900.0 + remaining,
		)

	if pending_in_recommended is not None and pending_in_recommended > 0 and recommended_archivo:
		add_action(
			action_id="continue_interview",
			label=f"Continuar entrevista recomendada: {recommended_archivo}",
			view="investigacion",
			subview="abierta",
			reason=f"Hay {pending_in_recommended} fragmentos pendientes en esta entrevista.",
			score=800.0 + float(pending_in_recommended),
			params={"archivo": recommended_archivo, "project": project},
		)

	if pending_total > 0:
		add_action(
			action_id="continue_open_coding",
			label="Continuar Codificación Abierta",
			view="investigacion",
			subview="abierta",
			reason=f"Quedan {pending_total} fragmentos pendientes en el proyecto.",
			score=700.0 + float(pending_total),
			params={"project": project},
		)

	if candidates_pending > 0:
		add_action(
			action_id="validate_candidates",
			label=f"Validar candidatos ({candidates_pending} pendientes)",
			view="investigacion",
			subview="abierta",
			reason="Hay códigos candidatos pendientes por validar/fusionar.",
			score=650.0 + float(candidates_pending),
			params={"project": project},
		)

	if str((axial_gate or {}).get("status")) == "unlocked":
		add_action(
			action_id="start_axial",
			label="Iniciar Codificación Axial",
			view="investigacion",
			subview="axial",
			reason="Axial está desbloqueado según reglas actuales.",
			score=600.0 + (coverage_percent / 10.0),
			params={"project": project},
		)
	else:
		add_action(
			action_id="workflow",
			label=f"Ver Flujo de trabajo (Etapa actual: {current_stage_label or current_stage_key or '-'})",
			view="proceso",
			subview=None,
			reason="Revisa bloqueos y próximos pasos por etapa.",
			score=100.0,
			params={"project": project},
		)

	actions.sort(key=lambda a: float(a.get("score") or 0.0), reverse=True)
	primary = actions[0] if actions else None
	secondary = actions[1:3] if len(actions) > 1 else []

	return {
		"current_stage": {"key": current_stage_key, "label": current_stage_label},
		"primary_action": primary,
		"secondary_actions": secondary,
		"signals": {
			"pending_total": int(pending_total),
			"pending_in_recommended": int(pending_in_recommended) if pending_in_recommended is not None else None,
			"recommended_archivo": recommended_archivo,
			"coverage_percent": coverage_percent,
			"candidates_pending": candidates_pending,
			"entrevistas_revisadas": entrevistas_revisadas,
			"entrevistas_totales": entrevistas_totales,
			"archivos": archivos,
			"fragmentos_analizables": analizables,
		},
	}


def build_panorama(
	*,
	project: str,
	validated: Optional[Dict[str, Any]],
	observed: Optional[Dict[str, Any]],
	stage_order: Sequence[str],
	pending_total: int,
	recommended_archivo: Optional[str],
	pending_in_recommended: Optional[int],
	saturation: Optional[Dict[str, Any]],
	config: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
	current_key, current_label = _first_incomplete_stage(validated, stage_order=stage_order)

	axial_gate = compute_axial_gate(observed=observed, saturation=saturation, config=config)
	actions = compute_primary_actions(
		project=project,
		current_stage_key=current_key,
		current_stage_label=current_label,
		observed=observed,
		pending_total=pending_total,
		pending_in_recommended=pending_in_recommended,
		recommended_archivo=recommended_archivo,
		axial_gate=axial_gate,
	)

	return {
		"project": project,
		"current_stage": actions.get("current_stage"),
		"primary_action": actions.get("primary_action"),
		"secondary_actions": actions.get("secondary_actions"),
		"axial_gate": axial_gate,
		"signals": actions.get("signals"),
		"saturation": (saturation or {}).get("summary") if isinstance(saturation, dict) else None,
	}