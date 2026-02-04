"""Utilities to surface recent report artifacts for LLM report generation.

Epic 6: Ensure that analytic memos and report artifacts are considered in
"informe de avance" (doctoral stage 3/4) and the stage-4 final report.

This module is intentionally lightweight so it can be imported from both
`app/doctoral_reports.py` and `app/reports.py` without creating heavy
dependencies.

Artifact sources (best-effort, bounded scan):
- Filesystem:
	- reports/<project_id>/*.{md,json} (GraphRAG, summaries, exports)
	- reports/<project_id>/doctoral/*.md (doctoral reports)
	- reports/runner/<project_id>/*.md (legacy runner outputs)
	- notes/<project_id>/*.md (Discovery memos and other notes)
	- notes/<project_id>/runner_semantic/*.md (runner memos)
	- logs/runner_reports/<project_id>/*.json (runner post-mortem reports)
	- logs/runner_checkpoints/<project_id>/*.json (runner checkpoints, optional)
- Database:
	- interview_reports (per-interview metrics + memo)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json

import structlog

_logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ReportArtifact:
	kind: str
	source: str  # 'fs' or 'db'
	label: str
	path: Optional[str] = None
	created_at: Optional[str] = None
	excerpt: Optional[str] = None


def _require_org_for_report_artifacts(org_id: Optional[str]) -> None:
	from .blob_storage import allow_orgless_tasks

	if org_id:
		return
	if allow_orgless_tasks():
		return
	raise ValueError(
		"org_id is required for report artifacts in tenant-scoped environments. "
		"Set ALLOW_ORGLESS_TASKS=true for development only."
	)


def _safe_read_text_excerpt(path: Path, max_chars: int) -> str:
	try:
		text = path.read_text(encoding="utf-8", errors="ignore")
	except Exception:
		return ""
	text = "\n".join(line.rstrip() for line in text.splitlines()).strip()
	if len(text) > max_chars:
		return text[:max_chars].rstrip() + "..."
	return text


def _iter_recent_files(*, org_id: Optional[str], project_id: str, limit: int) -> List[ReportArtifact]:
	"""Collect recent markdown/json artifacts.

	Primary: Azure Blob Storage (strict multi-tenant) under container "reports".
	Fallback: local filesystem (legacy/dev).
	"""
	_require_org_for_report_artifacts(org_id)

	def _blob_enabled() -> bool:
		try:
			from . import blob_storage  # local import to avoid hard dependency at import-time

			conn_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
			return bool(conn_str) and bool(getattr(blob_storage, "_AZURE_BLOB_AVAILABLE", False))
		except Exception:
			return False

	if _blob_enabled():
		try:
			from .blob_storage import (
				CONTAINER_REPORTS,
				blob_name_to_logical_path,
				download_file,
				list_files_with_meta,
				tenant_prefix,
			)

			prefix = tenant_prefix(org_id=org_id, project_id=project_id).rstrip("/") + "/"
			# Bound the scan for UX. Blob listing doesn't guarantee order, so we sort client-side.
			items = list_files_with_meta(container=CONTAINER_REPORTS, prefix=prefix, limit=max(60, int(limit) * 8))

			def _sort_key(it: Dict[str, Any]) -> str:
				return str(it.get("last_modified") or "")

			items.sort(key=_sort_key, reverse=True)

			artifacts: List[ReportArtifact] = []
			for it in items:
				name = str(it.get("name") or "")
				if not name:
					continue

				size = it.get("size")
				try:
					if size is not None and int(size) > 350_000:
						continue
				except Exception:
					pass

				logical = blob_name_to_logical_path(org_id=org_id, project_id=project_id, blob_name=name)
				if not logical:
					continue

				suffix = Path(logical).suffix.lower()
				if suffix not in {".md", ".markdown", ".json"}:
					continue

				kind = "project"
				if logical.startswith(f"reports/{project_id}/doctoral/"):
					kind = "doctoral"
				elif logical.startswith(f"notes/{project_id}/runner_semantic/"):
					kind = "runner_memo"
				elif logical.startswith(f"notes/{project_id}/"):
					kind = "note"
				elif logical.startswith(f"logs/runner_reports/{project_id}/"):
					kind = "runner_report"
				elif logical.startswith(f"logs/runner_checkpoints/{project_id}/"):
					kind = "runner_checkpoint"
				elif logical.startswith(f"reports/runner/{project_id}/"):
					kind = "runner"

				excerpt = ""
				try:
					data = download_file(CONTAINER_REPORTS, name)
					if suffix == ".json":
						try:
							raw = json.loads(data.decode("utf-8", errors="ignore"))
							excerpt = json.dumps(raw, ensure_ascii=False)[:700].rstrip() + "..."
						except Exception:
							excerpt = (data.decode("utf-8", errors="ignore") or "").strip()[:700].rstrip() + "..."
					else:
						text = data.decode("utf-8", errors="ignore")
						text = "\n".join(line.rstrip() for line in text.splitlines()).strip()
						excerpt = text[:700].rstrip() + ("..." if len(text) > 700 else "")
				except Exception:
					excerpt = ""

				artifacts.append(
					ReportArtifact(
						kind=kind,
						source="fs",  # backward-compat: 'fs' == durable artifacts store
						label=Path(logical).name,
						path=logical,
						created_at=it.get("last_modified"),
						excerpt=excerpt,
					)
				)

				if len(artifacts) >= max(1, int(limit)):
					break

			return artifacts
		except Exception as e:
			_logger.warning("report_artifacts.blob_failed", project=project_id, error=str(e)[:200])

	# Fallback to local filesystem (legacy/dev).
	base_reports = Path("reports")
	base_notes = Path("notes")
	base_logs = Path("logs")
	candidates: List[Tuple[Path, str]] = []

	runner_dir = base_reports / "runner" / project_id
	if runner_dir.exists():
		candidates.extend((p, "runner") for p in runner_dir.glob("*.md"))

	project_dir = base_reports / project_id
	if project_dir.exists():
		candidates.extend((p, "project") for p in project_dir.glob("*.md"))
		candidates.extend((p, "project") for p in project_dir.glob("*.json"))

		doctoral_dir = project_dir / "doctoral"
		if doctoral_dir.exists():
			candidates.extend((p, "doctoral") for p in doctoral_dir.glob("*.md"))

	# Notes (Discovery + others)
	notes_dir = base_notes / project_id
	if notes_dir.exists():
		candidates.extend((p, "note") for p in notes_dir.glob("*.md"))
		runner_semantic_dir = notes_dir / "runner_semantic"
		if runner_semantic_dir.exists():
			candidates.extend((p, "runner_memo") for p in runner_semantic_dir.glob("*.md"))

	# Runner machine artifacts
	runner_reports_dir = base_logs / "runner_reports" / project_id
	if runner_reports_dir.exists():
		candidates.extend((p, "runner_report") for p in runner_reports_dir.glob("*.json"))

	runner_checkpoints_dir = base_logs / "runner_checkpoints" / project_id
	if runner_checkpoints_dir.exists():
		candidates.extend((p, "runner_checkpoint") for p in runner_checkpoints_dir.glob("*.json"))

	def _mtime(p: Path) -> float:
		try:
			return p.stat().st_mtime
		except Exception:
			return 0.0

	candidates.sort(key=lambda t: _mtime(t[0]), reverse=True)

	artifacts: List[ReportArtifact] = []
	for path, kind in candidates:
		try:
			st = path.stat()
			if st.st_size > 350_000:
				continue
		except Exception:
			continue

		created_at = None
		try:
			created_at = datetime.fromtimestamp(path.stat().st_mtime).isoformat()
		except Exception:
			created_at = None

		excerpt = ""
		if path.suffix.lower() == ".md":
			excerpt = _safe_read_text_excerpt(path, max_chars=700)
		elif path.suffix.lower() == ".json":
			try:
				raw = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
				excerpt = json.dumps(raw, ensure_ascii=False)[:700].rstrip() + "..."
			except Exception:
				excerpt = _safe_read_text_excerpt(path, max_chars=700)

		artifacts.append(
			ReportArtifact(
				kind=kind,
				source="fs",
				label=path.name,
				path=str(path.as_posix()),
				created_at=created_at,
				excerpt=excerpt,
			)
		)
		if len(artifacts) >= max(1, int(limit)):
			break

	return artifacts


def list_recent_report_artifacts(
	pg_conn,
	project_id: str,
	*,
	org_id: Optional[str] = None,
	limit: int = 20,
) -> List[Dict[str, Any]]:
	"""Return structured recent artifacts for UI and orchestration.

	Note: this is best-effort and intentionally bounded (small file/row scans).
	"""
	fs_items = _iter_recent_files(org_id=org_id, project_id=project_id, limit=int(limit))
	db_items = _iter_recent_interview_reports(pg_conn, project_id)
	combined = fs_items + db_items

	def _sort_key(a: ReportArtifact) -> str:
		return a.created_at or ""

	combined.sort(key=_sort_key, reverse=True)
	result: List[Dict[str, Any]] = []
	for a in combined[: max(1, int(limit))]:
		result.append(
			{
				"kind": a.kind,
				"source": a.source,
				"label": a.label,
				"path": a.path,
				"created_at": a.created_at,
				"excerpt": a.excerpt,
			}
		)
	return result


def _iter_recent_interview_reports(pg_conn, project_id: str, limit: int = 6) -> List[ReportArtifact]:
	"""Collect concise summaries from `interview_reports` table (DB)."""
	try:
		with pg_conn.cursor() as cur:
			cur.execute(
				"""
				SELECT archivo, fecha_analisis, report_json
				FROM interview_reports
				WHERE project_id = %s
				ORDER BY fecha_analisis DESC
				LIMIT %s
				""",
				(project_id, limit),
			)
			rows = cur.fetchall()
	except Exception as e:
		_logger.warning("report_artifacts.interview_reports_error", project=project_id, error=str(e))
		return []

	artifacts: List[ReportArtifact] = []
	for archivo, fecha_analisis, report_json in rows:
		try:
			data = report_json if isinstance(report_json, dict) else json.loads(report_json)
		except Exception:
			data = {}

		codigos_nuevos = data.get("codigos_nuevos")
		tasa_cobertura = data.get("tasa_cobertura")
		categorias_nuevas = data.get("categorias_nuevas")
		relaciones_creadas = data.get("relaciones_creadas")
		memo = (data.get("memo_investigador") or "").strip()
		if memo and len(memo) > 260:
			memo = memo[:260].rstrip() + "..."

		created_at = None
		try:
			if isinstance(fecha_analisis, datetime):
				created_at = fecha_analisis.isoformat()
			else:
				created_at = str(fecha_analisis)
		except Exception:
			created_at = None

		parts = [
			f"archivo={archivo}",
			f"codigos_nuevos={codigos_nuevos}",
			f"tasa_cobertura={tasa_cobertura}%",
			f"categorias_nuevas={categorias_nuevas}",
			f"relaciones_creadas={relaciones_creadas}",
		]
		if memo:
			parts.append(f"memo={memo}")

		artifacts.append(
			ReportArtifact(
				kind="interview_report",
				source="db",
				label=f"interview_report:{archivo}",
				path=None,
				created_at=created_at,
				excerpt="; ".join([str(p) for p in parts if p is not None]),
			)
		)

	return artifacts


def get_recent_memos_for_reporting(pg_conn, project_id: str, limit: int = 8) -> str:
	"""Returns a compact memo block for prompts (Discovery + candidate memos)."""
	blocks: List[str] = []

	# Discovery syntheses
	try:
		with pg_conn.cursor() as cur:
			cur.execute(
				"""
				SELECT ai_synthesis, positivos, created_at
				FROM discovery_navigation_log
				WHERE project_id = %s AND ai_synthesis IS NOT NULL AND ai_synthesis != ''
				ORDER BY created_at DESC
				LIMIT %s
				""",
				(project_id, limit),
			)
			rows = cur.fetchall()
		for ai_synthesis, positivos, _created_at in rows:
			synthesis = (ai_synthesis or "").strip()
			if len(synthesis) > 350:
				synthesis = synthesis[:350].rstrip() + "..."
			conceptos = ", ".join((positivos or [])[:3]) if positivos else "(sin conceptos)"
			blocks.append(f"- [Discovery: {conceptos}] {synthesis}")
	except Exception as e:
		_logger.warning("report_artifacts.discovery_memos_error", project=project_id, error=str(e))

	# Candidate memos
	try:
		with pg_conn.cursor() as cur:
			cur.execute(
				"""
				SELECT memo
				FROM codigos_candidatos
				WHERE project_id = %s AND memo IS NOT NULL AND memo != ''
				ORDER BY created_at DESC NULLS LAST
				LIMIT 5
				""",
				(project_id,),
			)
			rows = cur.fetchall()
		for (memo,) in rows:
			m = (memo or "").strip()
			if not m:
				continue
			if len(m) > 280:
				m = m[:280].rstrip() + "..."
			blocks.append(f"- [Código candidato] {m}")
	except Exception as e:
		_logger.warning("report_artifacts.candidate_memos_error", project=project_id, error=str(e))

	if not blocks:
		return "(sin memos recientes)"

	return "\n".join(blocks)


def _format_artifacts_for_prompt(artifacts: List[ReportArtifact], max_items: int) -> str:
	if not artifacts:
		return "(sin artefactos recientes detectados)"

	lines: List[str] = []
	for a in artifacts[:max_items]:
		meta = []
		if a.created_at:
			meta.append(a.created_at)
		if a.path:
			meta.append(a.path)
		meta_str = " | ".join(meta)
		header = f"- [{a.source}:{a.kind}] {a.label}" + (f" ({meta_str})" if meta_str else "")
		if a.excerpt:
			lines.append(header)
			lines.append(f"  excerpt: {a.excerpt}")
		else:
			lines.append(header)

	return "\n".join(lines)


def _get_recent_report_artifacts(
	pg_conn,
	project_id: str,
	*,
	org_id: Optional[str] = None,
	max_items: int = 10,
) -> str:
	"""Epic 6 helper: returns a prompt-ready block with recent artifacts."""
	combined_struct = list_recent_report_artifacts(pg_conn, project_id, org_id=org_id, limit=max_items)
	artifacts: List[ReportArtifact] = []
	for item in combined_struct:
		path = item.get("path")
		created_at = item.get("created_at")
		excerpt = item.get("excerpt")
		artifacts.append(
			ReportArtifact(
				kind=str(item.get("kind") or ""),
				source=str(item.get("source") or ""),
				label=str(item.get("label") or ""),
				path=str(path) if isinstance(path, str) else None,
				created_at=str(created_at) if isinstance(created_at, str) else None,
				excerpt=str(excerpt) if isinstance(excerpt, str) else None,
			)
		)
	return _format_artifacts_for_prompt(artifacts, max_items=max_items)
