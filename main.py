from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.analysis import analyze_interview_text, matriz_etapa3, matriz_etapa4, modelo_ascii, persist_analysis
from app.coding import (
    assign_open_code,
    citations_for_code,
    coding_statistics,
    list_available_interviews,
    list_interview_fragments,
    list_open_codes,
    suggest_similar_fragments,
    CodingError,
)
from app.nucleus import centrality_report, coverage_report, nucleus_report, probe_semantics
from app.axial import ALLOWED_REL_TYPES, AxialError, AxialNotReadyError, assign_axial_relation, run_gds_analysis
from app.clients import build_service_clients
from app.documents import load_fragments
from app.ingestion import ingest_documents
from app.logging_utils import bind_run, configure_logging
from app.queries import graph_counts, run_cypher, sample_postgres, semantic_search
from app.settings import load_settings
from app import reporting as reporting_utils
from app import transversal as transversal_utils
from app import validation as validation_utils
from app.transcription import (
    transcribe_audio,
    transcribe_audio_chunked,
    audio_to_fragments,
    save_transcription_docx,
    TranscriptionResult,
)
from app.project_state import (
    DEFAULT_PROJECT,
    create_project,
    detect_stage_status,
    get_project,
    list_projects,
    mark_stage,
    resolve_project,
)
from app.metadata_ops import apply_metadata_entries, load_plan_from_csv, load_plan_from_json

STAGE_DEFINITIONS: Dict[str, Dict[str, str]] = {
    "preparacion": {
        "label": "Etapa 0 - Preparacion y Reflexividad",
        "log_glob": "etapa0_*.log",
        "verify": "python scripts/healthcheck.py",
    },
    "ingesta": {
        "label": "Etapa 1 - Ingesta y normalizacion",
        "log_glob": "ingest*.log",
        "verify": "python main.py ingest ...",
    },
    "codificacion": {
        "label": "Etapa 3 - Codificacion abierta",
        "log_glob": "etapa3_*.log",
        "verify": "python main.py coding stats",
    },
    "axial": {
        "label": "Etapa 4 - Codificacion axial",
        "log_glob": "etapa4_*.log",
        "verify": "python main.py axial gds --algorithm pagerank",
    },
    "nucleo": {
        "label": "Etapa 5 - Seleccion del nucleo",
        "log_glob": "etapa5_*.log",
        "verify": "python main.py nucleus report ...",
    },
    "transversal": {
        "label": "Etapa 6 - Analisis transversal",
        "log_glob": "etapa6_*.log",
        "verify": "python main.py transversal dashboard ...",
    },
    "validacion": {
        "label": "Etapa 8 - Validacion y saturacion",
        "log_glob": "etapa8_*.log",
        "verify": "python main.py validation curve",
    },
    "informe": {
        "label": "Etapa 9 - Informe integrado",
        "log_glob": "etapa9_*.log",
        "verify": "python main.py report build",
    },
    "analisis": {
        "label": "Etapa LLM - Analisis asistido",
        "log_glob": "analysis_*.log",
        "verify": "python main.py analyze ...",
    },
}

STAGE_ORDER: List[str] = [
    "preparacion",
    "ingesta",
    "codificacion",
    "axial",
    "nucleo",
    "transversal",
    "validacion",
    "informe",
    "analisis",
]

STAGE_COMMAND_MAP: Dict[str, str] = {
    "ingest": "ingesta",
    "coding": "codificacion",
    "axial": "axial",
    "nucleus": "nucleo",
    "transversal": "transversal",
    "validation": "validacion",
    "report": "informe",
    "analyze": "analisis",
}

SUBCOMMAND_ATTR: Dict[str, str] = {
    "coding": "coding_command",
    "axial": "axial_command",
    "nucleus": "nucleus_command",
    "transversal": "transversal_command",
    "validation": "validation_command",
    "report": "report_command",
    "metadata": "metadata_command",
    "neo4j": "neo4j_command",
}

STAGE_REQUIRED_SUBCOMMAND = {
    "report": {"build"},
}


def _format_log_hint(log_hint: Any) -> str:
    if isinstance(log_hint, dict):
        path = str(log_hint.get("path") or "-")
        modified = log_hint.get("modified_at")
        if modified:
            if path and path != "-":
                return f"{path} (modificado {modified})"
            return f"modificado {modified}"
        return path
    if isinstance(log_hint, str) and log_hint.strip():
        return log_hint.strip()
    return "-"


def _artifact_entry(item: Any) -> str:
    if isinstance(item, dict):
        label = item.get("label")
        details = [
            f"{key}={value}"
            for key, value in item.items()
            if key != "label" and value not in (None, "", [])
        ]
        if label and details:
            return f"{label}: {', '.join(details)}"
        if label:
            return str(label)
        if details:
            return ", ".join(details)
        return "-"
    return str(item)


def _format_artifacts(artifacts: Any) -> List[str]:
    if not artifacts:
        return []
    if isinstance(artifacts, list):
        return [_artifact_entry(item) for item in artifacts]
    return [_artifact_entry(artifacts)]


def _print_status_snapshot(snapshot: Dict[str, Any]) -> None:
    stages = snapshot.get("stages") or {}
    for stage_key in STAGE_ORDER:
        data = stages.get(stage_key, {})
        label = data.get("label") or stage_key
        print(label)
        status = "Completa" if data.get("completed") else "Pendiente"
        print(f"  Estado        : {status}")
        print(f"  Ultimo run_id : {data.get('last_run_id', '-')}")
        print(f"  Actualizado   : {data.get('updated_at', '-')}")
        command = data.get("command")
        subcommand = data.get("subcommand")
        if command or subcommand:
            combo = command or ""
            if command and subcommand:
                combo = f"{command}:{subcommand}"
            elif subcommand and not command:
                combo = subcommand
            print(f"  Ultimo comando: {combo}")
        verify = data.get("verify")
        if verify:
            print(f"  Verificacion  : {verify}")
        log_hint = _format_log_hint(data.get("log_hint"))
        print(f"  Log           : {log_hint}")
        artifact_lines = _format_artifacts(data.get("artifacts"))
        if artifact_lines:
            print("  Evidencia     :")
            for line in artifact_lines:
                print(f"    - {line}")
        else:
            print("  Evidencia     : -")
        print()

    manifest = snapshot.get("manifest")
    if manifest is not None:
        print("Report manifest")
        generated = manifest.get("generated_at") if isinstance(manifest, dict) else None
        print(f"  Generado      : {generated or '-'}")
        report = manifest.get("report") if isinstance(manifest, dict) else None
        if isinstance(report, dict):
            print(f"  Archivo       : {report.get('path', '-')}")
            if report.get("hash"):
                print(f"  Hash          : {report['hash']}")
        print()
    print(f"Estado almacenado: {snapshot.get('state_path', '-')}")


def build_context(env_file: str | None):
    settings = load_settings(env_file)
    clients = build_service_clients(settings)
    return settings, clients


def _coerce_value(value: str):
    lower = value.lower()
    if lower in {"true", "false"}:
        return lower == "true"
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value


def _coerce_bool(value: str) -> bool:
    parsed = _coerce_value(value)
    if isinstance(parsed, bool):
        return parsed
    raise ValueError(f"No se pudo interpretar '{value}' como booleano")


def _parse_segment_arg(raw: str) -> Dict[str, object]:
    parts = [part.strip() for part in raw.split("|") if part.strip()]
    if not parts:
        raise ValueError("Segmento vacio")
    name = parts[0]
    filters: Dict[str, object] = {}
    for token in parts[1:]:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        filters[key.strip()] = _coerce_value(value.strip())
    return {"name": name, "filters": filters}


def cmd_ingest(args):
    logger = args.logger
    raw_inputs = [str(p) for p in args.inputs]
    input_files: List[str] = []
    for item in raw_inputs:
        if any(ch in item for ch in ("*", "?", "[", "]")):
            matches = sorted(glob.glob(item))
            if not matches:
                logger.warning("ingest.pattern.empty", pattern=item)
            input_files.extend(matches)
        else:
            input_files.append(item)
    # remove duplicates preserving order
    seen = set()
    deduped: List[str] = []
    for path in input_files:
        if path not in seen:
            deduped.append(path)
            seen.add(path)
    input_files = deduped
    if not input_files:
        logger.error("ingest.no_files", inputs=raw_inputs)
        print("Error: no se encontraron archivos para ingerir.")
        return
    logger.info(
        "ingest.command.begin",
        etapa="etapa1_ingesta",
        files=input_files,
        batch_size=args.batch_size,
        min_chars=args.min_chars,
        max_chars=args.max_chars,
    )

    settings, clients = build_context(args.env)
    metadata = None
    if getattr(args, "meta_json", None):
        meta_path = Path(args.meta_json)
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))

    try:
        result = ingest_documents(
            clients,
            settings,
            input_files,
            batch_size=args.batch_size,
            min_chars=args.min_chars,
            max_chars=args.max_chars,
            metadata=metadata,
            run_id=args.run_id,
            logger=logger,
            project=args.project,
        )
    finally:
        clients.close()

    if not result:
        return

    for summary in result.get("per_file", []):
        logger.info("ingest.file.summary", etapa="etapa1_ingesta", **summary)

    logger.info(
        "ingest.overall",
        etapa="etapa1_ingesta",
        **result.get("totals", {}),
        issues=result.get("issues", {}),
    )


def cmd_search(args):
    logger = args.logger
    logger.info("search.command.begin", etapa="etapa2_diagnostico", query=args.query, top_k=args.top_k)
    settings, clients = build_context(args.env)
    try:
        results = semantic_search(clients, settings, args.query, top_k=args.top_k, project=args.project)
    finally:
        clients.close()

    for item in results:
        print(f"score={item['score']:.4f} | archivo={item['archivo']} | par_idx={item['par_idx']} | len={item['char_len']}")
        print(f"  {item['fragmento'][:160]}...")
        print()

    logger.info("search.command.complete", etapa="etapa2_diagnostico", results=len(results))


def cmd_counts(args):
    logger = args.logger
    logger.info("counts.command.begin", etapa="etapa2_diagnostico")
    settings, clients = build_context(args.env)
    try:
        data = graph_counts(clients, settings, args.project)
    finally:
        clients.close()

    for row in data:
        print(f"{row['entrevista']}: {row['cantidad']} fragmentos")

    logger.info("counts.command.complete", etapa="etapa2_diagnostico", rows=len(data))


def _parse_param_args(pairs: Optional[List[str]]) -> Dict[str, Any]:
    params: Dict[str, Any] = {}
    for raw in pairs or []:
        if "=" not in raw:
            raise ValueError(f"Parametro invalido: '{raw}'. Usa clave=valor.")
        key, value = raw.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError("El nombre del parametro no puede estar vacio.")
        params[key] = _coerce_value(value.strip())
    return params


def _parse_formats(values: Optional[List[str]]) -> List[str]:
    if not values:
        return ["raw"]
    normalized: List[str] = []
    for entry in values:
        fmt = (entry or "").lower()
        if fmt == "all":
            return ["raw", "table", "graph"]
        if fmt in {"raw", "table", "graph"} and fmt not in normalized:
            normalized.append(fmt)
    return normalized or ["raw"]


def cmd_neo4j_query(args):
    logger = args.logger
    try:
        params = _parse_param_args(args.param)
    except ValueError as exc:
        logger.error("neo4j.query.params_error", error=str(exc))
        print(f"Error: {exc}")
        raise SystemExit(1)
    formats = _parse_formats(args.format)
    logger.info(
        "neo4j.query.begin",
        cypher=args.cypher,
        formatos=formats,
        parametros=len(params),
    )
    settings, clients = build_context(args.env)
    try:
        result = run_cypher(
            clients,
            args.cypher,
            params=params,
            database=settings.neo4j.database,
        )
    except Exception as exc:
        logger.error("neo4j.query.error", error=str(exc))
        print(f"Error: {exc}")
        raise SystemExit(1)
    finally:
        clients.close()
    payload = {fmt: result[fmt] for fmt in formats}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for fmt in formats:
            print(f"== {fmt.upper()} ==")
            print(json.dumps(result[fmt], ensure_ascii=False, indent=2))
    logger.info(
        "neo4j.query.complete",
        formatos=formats,
        filas=len(result["raw"]),
    )


def cmd_sample(args):
    logger = args.logger
    logger.info("sample.command.begin", etapa="etapa2_diagnostico", limit=args.limit)
    settings, clients = build_context(args.env)
    try:
        rows = sample_postgres(clients, args.project, limit=args.limit)
    finally:
        clients.close()
    logger.info("sample.command.complete", etapa="etapa2_diagnostico", rows=len(rows))
    if getattr(args, "json", False):
        print(json.dumps({"samples": rows}, ensure_ascii=False, indent=2))
        return
    for entry in rows:
        fragmento = (entry.get("fragmento") or "").replace("\n", " ")
        preview = fragmento[:160] + ("..." if len(fragmento) > 160 else "")
        print(
            f"{entry.get('fragmento_id')} | archivo={entry.get('archivo')} | par_idx={entry.get('par_idx')} | len={entry.get('char_len')}\n  {preview}"
        )


def cmd_status(args):
    logger = args.logger
    should_update = not args.no_update
    logger.info(
        "status.command.begin",
        etapa="estado_proyecto",
        json=args.json,
        update=should_update,
        project=args.project,
    )
    settings, clients = build_context(args.env)
    try:
        snapshot = detect_stage_status(
            clients.postgres,
            args.project,
            STAGE_DEFINITIONS,
            stage_order=STAGE_ORDER,
        )
    finally:
        clients.close()

    if args.json:
        print(json.dumps(snapshot, ensure_ascii=False, indent=2))
    else:
        _print_status_snapshot(snapshot)

    logger.info(
        "status.command.complete",
        etapa="estado_proyecto",
        etapas=len(snapshot.get("stages", {})),
        updated=snapshot.get("updated"),
        project=args.project,
    )


def cmd_project_create(args):
    settings, clients = build_context(args.env)
    try:
        entry = create_project(clients.postgres, args.name, args.description)
    except ValueError as exc:
        if args.json:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        else:
            print(f"Error: {exc}")
        raise SystemExit(1)
    finally:
        clients.close()

    if args.json:
        print(json.dumps(entry, ensure_ascii=False, indent=2))
    else:
        print(f"Proyecto creado: {entry['name']} (id={entry['id']})")


def cmd_project_list(args):
    settings, clients = build_context(args.env)
    try:
        projects = list_projects(clients.postgres)
    finally:
        clients.close()
    if args.json:
        print(json.dumps({"projects": projects}, ensure_ascii=False, indent=2))
        return
    if not projects:
        print("No hay proyectos registrados.")
        return
    for project in projects:
        print(f"{project.get('id')} -> {project.get('name') or '(sin nombre)'}")
        if project.get("description"):
            print(f"  descripcion: {project['description']}")
        print(f"  creado: {project.get('created_at', '-')}")


def cmd_project_info(args):
    try:
        project_id = resolve_project(args.project, allow_create=False)
    except ValueError as exc:
        if args.json:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        else:
            print(f"Error: {exc}")
        raise SystemExit(1)
    settings, clients = build_context(args.env)
    try:
        project = get_project(clients.postgres, project_id)
        snapshot = detect_stage_status(
            clients.postgres,
            project_id,
            STAGE_DEFINITIONS,
            stage_order=STAGE_ORDER,
        )
    finally:
        clients.close()
    payload = {
        "project": project,
        "snapshot": snapshot,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    name = (project or {}).get("name") if project else project_id
    print(f"Proyecto: {name} (id={project_id})")
    if project and project.get("description"):
        print(f"Descripcion: {project['description']}")
    stages = snapshot.get("stages", {})
    for key in STAGE_ORDER:
        entry = stages.get(key, {})
        status = "Completa" if entry.get("completed") else "Pendiente"
        print(f"- {entry.get('label', key)}: {status}")


def cmd_workflow_complete(args):
    stage_key = args.stage
    if stage_key not in STAGE_DEFINITIONS:
        message = f"Etapa desconocida: {stage_key}"
        if args.json:
            print(json.dumps({"error": message}, ensure_ascii=False))
        else:
            print(message)
        raise SystemExit(1)
    extras: Dict[str, Any] = {}
    if args.notes:
        extras["notes"] = args.notes
    settings, clients = build_context(args.env)
    try:
        payload = mark_stage(
            clients.postgres,
            args.project,
            stage_key,
            run_id=args.run_id,
            command="workflow",
            subcommand="complete",
            extras=extras,
        )
    finally:
        clients.close()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Etapa '{stage_key}' marcada como completa para el proyecto {args.project}.")


def cmd_coding_assign(args):
    logger = args.logger
    logger.info(
        "coding.assign.begin",
        etapa="etapa3_codificacion",
        fragment_id=args.fragment_id,
        codigo=args.codigo,
    )
    settings, clients = build_context(args.env)
    try:
        result = assign_open_code(
            clients,
            settings,
            fragment_id=args.fragment_id,
            codigo=args.codigo,
            cita=args.cita,
            fuente=args.fuente,
            memo=args.memo,
            project=args.project,
            logger=logger,
        )
    except CodingError as exc:
        logger.error("coding.assign.error", error=str(exc))
        message = str(exc)
        if getattr(args, "json", False):
            print(json.dumps({"error": message}, ensure_ascii=False))
        else:
            print(f"Error: {message}")
        raise SystemExit(1)
    finally:
        clients.close()
    logger.info("coding.assign.complete", etapa="etapa3_codificacion", **result)
    if getattr(args, "json", False):
        print(json.dumps({"result": result}, ensure_ascii=False, indent=2))
    else:
        print(f"Asignado codigo '{result['codigo']}' al fragmento {result['fragmento_id']} ({result['archivo']})")

def cmd_coding_suggest(args):
    logger = args.logger
    filters = {
        key: getattr(args, key)
        for key in ("archivo", "area_tematica", "actor_principal")
        if getattr(args, key) is not None
    }
    if args.requiere_protocolo_lluvia is not None:
        filters["requiere_protocolo_lluvia"] = args.requiere_protocolo_lluvia
    logger.info(
        "coding.suggest.begin",
        etapa="etapa3_codificacion",
        fragment_id=args.fragment_id,
        top_k=args.top_k,
        filters=filters,
        include_coded=args.include_coded,
    )
    settings, clients = build_context(args.env)
    try:
        result = suggest_similar_fragments(
            clients,
            settings,
            fragment_id=args.fragment_id,
            top_k=args.top_k,
            filters=filters,
            exclude_coded=not args.include_coded,
            run_id=args.run_id,
            project=getattr(args, "project", None),
            persist=args.persist,
            llm_model=args.llm_model,
            logger=logger,
        )
    except CodingError as exc:
        logger.error("coding.suggest.error", error=str(exc))
        message = str(exc)
        if getattr(args, "json", False):
            print(json.dumps({"error": message}, ensure_ascii=False))
        else:
            print(f"Error: {message}")
        raise SystemExit(1)
    finally:
        clients.close()
    if getattr(args, "json", False):
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    payload = result.get("suggestions", [])
    for item in payload:
        preview = (item.get('fragmento') or '').strip().replace('\n', ' ')
        print(
            f"score={item['score']:.4f} | fragmento_id={item['fragmento_id']} | archivo={item.get('archivo')} | par_idx={item.get('par_idx')}\n  {preview[:160]}..."
        )
    if result.get("llm_summary"):
        print("\nResumen GPT-5:")
        print(result["llm_summary"])
    if result.get("comparison_id"):
        print(f"\nComparación registrada con id={result['comparison_id']}")
    logger.info(
        "coding.suggest.complete",
        etapa="etapa3_codificacion",
        returned=len(payload),
        comparison_id=result.get("comparison_id"),
    )

def cmd_coding_stats(args):
    logger = args.logger
    settings, clients = build_context(args.env)
    try:
        stats = coding_statistics(clients, args.project)
    finally:
        clients.close()
    logger.info("coding.stats", etapa="etapa3_codificacion", **stats)
    if getattr(args, "json", False):
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return
    for key, value in stats.items():
        print(f"{key}: {value}")

def cmd_coding_citations(args):
    logger = args.logger
    settings, clients = build_context(args.env)
    try:
        rows = citations_for_code(clients, args.codigo, args.project)
    finally:
        clients.close()
    logger.info("coding.citations", etapa="etapa3_codificacion", codigo=args.codigo, total=len(rows))
    if getattr(args, "json", False):
        print(json.dumps({"citations": rows}, ensure_ascii=False, indent=2))
        return
    if not rows:
        print("Sin citas registradas para este codigo.")
        return
    for row in rows:
        cita = (row.get('cita') or '').replace('\n', ' ')
        print(
            f"fragmento_id={row['fragmento_id']} | archivo={row['archivo']} | fuente={row.get('fuente') or '-'} | cita={cita}"
        )


def cmd_coding_interviews(args):
    logger = args.logger
    settings, clients = build_context(args.env)
    try:
        items = list_available_interviews(clients, args.project, limit=args.limit)
    finally:
        clients.close()
    logger.info("coding.interviews", etapa="etapa3_codificacion", total=len(items))
    if getattr(args, "json", False):
        print(json.dumps({"interviews": items}, ensure_ascii=False, indent=2))
        return
    if not items:
        print("No hay entrevistas ingeridas.")
        return
    for entry in items:
        actor = entry.get("actor_principal") or "-"
        area = entry.get("area_tematica") or "-"
        updated = entry.get("actualizado") or "-"
        print(
            f"{entry['archivo']} | fragmentos={entry['fragmentos']} | actor={actor} | area={area} | actualizado={updated}"
        )


def cmd_coding_codes(args):
    logger = args.logger
    settings, clients = build_context(args.env)
    try:
        codes = list_open_codes(clients, args.project, limit=args.limit, search=args.search)
    finally:
        clients.close()
    logger.info("coding.codes", etapa="etapa3_codificacion", total=len(codes), search=args.search)
    if getattr(args, "json", False):
        print(json.dumps({"codes": codes}, ensure_ascii=False, indent=2))
        return
    if not codes:
        print("No hay codigos registrados.")
        return
    for entry in codes:
        print(
            f"{entry['codigo']} | citas={entry['citas']} | fragmentos={entry['fragmentos']} | primera={entry.get('primera_cita') or '-'} | ultima={entry.get('ultima_cita') or '-'}"
        )


def cmd_coding_fragments(args):
    logger = args.logger
    settings, clients = build_context(args.env)
    try:
        rows = list_interview_fragments(clients, args.project, archivo=args.archivo, limit=args.limit)
    finally:
        clients.close()
    logger.info(
        "coding.fragments",
        etapa="etapa3_codificacion",
        archivo=args.archivo,
        total=len(rows),
    )
    if getattr(args, "json", False):
        print(json.dumps({"fragments": rows}, ensure_ascii=False, indent=2))
        return
    if not rows:
        print("No se encontraron fragmentos para el archivo solicitado.")
        return
    for entry in rows:
        preview = (entry.get("fragmento") or "").replace("\n", " ")
        snippet = preview[:160] + ("..." if len(preview) > 160 else "")
        print(
            f"{entry.get('fragmento_id')} | par_idx={entry.get('par_idx')} | len={entry.get('char_len')}\n  {snippet}"
        )


def _parse_metadata_kv(pairs: List[str]) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {}
    for item in pairs:
        if "=" not in item:
            raise ValueError(f"Formato invalido '{item}'. Usa clave=valor.")
        key, raw_value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Clave vacia en metadata: '{item}'")
        metadata[key] = _coerce_value(raw_value.strip())
    return metadata


def cmd_metadata_set(args):
    logger = args.logger
    try:
        metadata_pairs = _parse_metadata_kv(args.metadata or [])
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    if args.requiere_protocolo_lluvia is None:
        lluvia_value: Optional[bool] = None
    else:
        try:
            lluvia_value = _coerce_bool(args.requiere_protocolo_lluvia)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc

    entry = {
        "archivo": args.archivo,
        "metadata": metadata_pairs,
        "actor_principal": args.actor_principal,
        "requiere_protocolo_lluvia": lluvia_value,
        "fragmentos": args.fragment,
    }

    settings, clients = build_context(args.env)
    try:
        summary = apply_metadata_entries(clients, settings, [entry])
    finally:
        clients.close()

    total_fragments = summary["total_fragments"]
    print(
        f"Metadatos actualizados para {total_fragments} fragmentos del archivo {args.archivo}."
    )
    logger.info(
        "metadata.set",
        archivo=args.archivo,
        fragmentos=total_fragments,
        metadata=list(metadata_pairs.keys()),
        actor=args.actor_principal,
        lluvia=lluvia_value,
        targeted=len(args.fragment or []),
    )


def cmd_metadata_apply(args):
    logger = args.logger
    try:
        if args.plan:
            entries = load_plan_from_json(args.plan)
            source = "json"
        else:
            entries = load_plan_from_csv(args.csv)
            source = "csv"
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    settings, clients = build_context(args.env)
    try:
        summary = apply_metadata_entries(clients, settings, entries)
    finally:
        clients.close()

    for detail in summary["details"]:
        print(f"{detail['archivo']}: {len(detail['fragmentos'])} fragmentos actualizados")
    print(
        f"Total fragmentos actualizados: {summary['total_fragments']} en {summary['total_files']} entrevistas."
    )
    logger.info(
        "metadata.apply",
        archivos=summary["total_files"],
        fragmentos=summary["total_fragments"],
        source=source,
    )


def cmd_axial_relate(args):
    logger = args.logger
    logger.info(
        "axial.relate.begin",
        etapa="etapa4_axial",
        categoria=args.categoria,
        codigo=args.codigo,
        relacion=args.tipo,
        evidencia=len(args.evidencia),
    )
    settings, clients = build_context(args.env)
    try:
        payload = assign_axial_relation(
            clients,
            settings,
            categoria=args.categoria,
            codigo=args.codigo,
            relacion=args.tipo,
            evidencia=args.evidencia,
            memo=args.memo,
            project=args.project,
            logger=logger,
        )
    except AxialNotReadyError as exc:
        logger.error(
            "axial.relate.blocked",
            project_id=exc.project_id,
            blocking_reasons=exc.blocking_reasons,
        )
        print(f"Error 409: {exc}")
        print(f"  Razones de bloqueo: {', '.join(exc.blocking_reasons)}")
        print(f"  Use: GET /api/admin/code-id/status?project={exc.project_id}")
        return
    except AxialError as exc:
        logger.error("axial.relate.error", error=str(exc))
        print(f"Error: {exc}")
        return
    finally:
        clients.close()
    logger.info("axial.relate.complete", etapa="etapa4_axial", **payload)
    print(f"Relacion axial registrada: {payload}")


def cmd_axial_gds(args):
    logger = args.logger
    logger.info("axial.gds.begin", etapa="etapa4_axial", algorithm=args.algorithm)
    settings, clients = build_context(args.env)
    rows: List[Dict[str, Any]] = []
    try:
        rows = run_gds_analysis(clients, settings, args.algorithm)
    except AxialError as exc:
        logger.error("axial.gds.error", error=str(exc))
        print(f"Error: {exc}")
        return
    finally:
        clients.close()
    for row in rows:
        etiquetas = row.get("etiquetas") or []
        if not isinstance(etiquetas, (list, tuple)):
            etiquetas = [etiquetas]
        etiquetas_text = ",".join(str(item) for item in etiquetas if item)
        etiquetas_text = etiquetas_text or "-"
        if "community_id" in row:
            print(f"{row['nombre']} ({etiquetas_text}) -> comunidad {row['community_id']}")
        else:
            print(f"{row['nombre']} ({etiquetas_text}) -> score {row['score']:.4f}")
    logger.info("axial.gds.complete", etapa="etapa4_axial", rows=len(rows))


def cmd_nucleus_report(args):
    logger = args.logger
    filters = {}
    if args.filter_archivo:
        filters["archivo"] = args.filter_archivo
    if args.filter_area_tematica:
        filters["area_tematica"] = args.filter_area_tematica
    if args.filter_actor_principal:
        filters["actor_principal"] = args.filter_actor_principal
    if args.filter_lluvia is not None:
        filters["requiere_protocolo_lluvia"] = args.filter_lluvia
    if not filters:
        filters = None

    logger.info(
        "nucleus.report.begin",
        etapa="etapa5_nucleo",
        categoria=args.categoria,
        prompt=bool(args.prompt),
        algorithm=args.algorithm,
        filters=filters or {},
    )

    settings, clients = build_context(args.env)
    try:
        report = nucleus_report(
            clients,
            settings,
            categoria=args.categoria,
            prompt=args.prompt,
            algorithm=args.algorithm,
            centrality_top=args.centrality_top,
            centrality_rank_max=args.centrality_rank_max,
            probe_top=args.probe_top,
            min_interviews=args.min_interviews,
            min_roles=args.min_roles,
            min_quotes=args.min_quotes,
            quote_limit=args.quote_limit,
            filters=filters,
            memo=args.memo,
            persist=args.persist,
            llm_model=args.llm_model,
            run_id=args.run_id,
            project=getattr(args, "project", None),
        )
    finally:
        clients.close()

    print(json.dumps(report, ensure_ascii=False, indent=2))
    logger.info(
        "nucleus.report.complete",
        etapa="etapa5_nucleo",
        done=report.get("done"),
        checks=report.get("checks"),
        persisted=report.get("persisted"),
        llm_model=report.get("llm_model"),
    )


def cmd_transversal_pg(args):
    logger = args.logger
    logger.info(
        "transversal.pg.begin",
        etapa="etapa6_transversal",
        dimension=args.dimension,
        categoria=args.categoria,
        limit=args.limit,
        refresh=args.refresh,
    )
    settings, clients = build_context(args.env)
    try:
        data = transversal_utils.pg_cross_tab(
            clients,
            args.dimension,
            categoria=args.categoria,
            project=args.project,
            limit=args.limit,
            refresh=args.refresh,
            logger=logger,
        )
    finally:
        clients.close()
    print(json.dumps(data, ensure_ascii=False, indent=2))
    logger.info(
        "transversal.pg.complete",
        etapa="etapa6_transversal",
        rows=len(data.get("rows", [])),
        latency=data.get("latency_seconds"),
    )


def cmd_transversal_qdrant(args):
    logger = args.logger
    raw_segments: List[str] = args.segment or []
    segments: List[Dict[str, object]] = []
    for raw in raw_segments:
        try:
            segments.append(_parse_segment_arg(raw))
        except ValueError as exc:
            logger.error("transversal.qdrant.segment_error", segment=raw, error=str(exc))
            print(f"Segmento invalido: {raw} ({exc})")
            return
    if not segments:
        segments = [{"name": "global", "filters": {}}]

    logger.info(
        "transversal.qdrant.begin",
        etapa="etapa6_transversal",
        prompt_preview=args.prompt[:40],
        segments=len(segments),
        top_k=args.top_k,
    )
    settings, clients = build_context(args.env)
    try:
        data = transversal_utils.qdrant_segment_probe(
            clients,
            settings,
            prompt=args.prompt,
            segments=segments,
            project=args.project,
            top_k=args.top_k,
            logger=logger,
        )
    finally:
        clients.close()
    print(json.dumps(data, ensure_ascii=False, indent=2))
    logger.info(
        "transversal.qdrant.complete",
        etapa="etapa6_transversal",
        segments=len(data.get("segments", [])),
    )


def cmd_transversal_neo4j(args):
    logger = args.logger
    logger.info(
        "transversal.neo4j.begin",
        etapa="etapa6_transversal",
        attribute=args.attribute,
        values=args.values,
        limit=args.limit,
    )
    settings, clients = build_context(args.env)
    try:
        data = transversal_utils.neo4j_multi_summary(
            clients,
            settings,
            attribute=args.attribute,
            values=args.values,
            project=args.project,
            limit=args.limit,
            logger=logger,
        )
    finally:
        clients.close()
    print(json.dumps(data, ensure_ascii=False, indent=2))
    logger.info(
        "transversal.neo4j.complete",
        etapa="etapa6_transversal",
        values=len(data.get("values", [])),
    )


def cmd_transversal_dashboard(args):
    logger = args.logger
    raw_segments: List[str] = args.segment or []
    segments: List[Dict[str, object]] = []
    for raw in raw_segments:
        try:
            segments.append(_parse_segment_arg(raw))
        except ValueError as exc:
            logger.error("transversal.dashboard.segment_error", segment=raw, error=str(exc))
            print(f"Segmento invalido: {raw} ({exc})")
            return
    if not segments:
        segments = [{"name": "global", "filters": {}}]

    logger.info(
        "transversal.dashboard.begin",
        etapa="etapa6_transversal",
        dimension=args.dimension,
        categoria=args.categoria,
        attribute=args.attribute,
        values=args.values,
        segments=len(segments),
    )

    settings, clients = build_context(args.env)
    try:
        payload = transversal_utils.build_dashboard_payload(
            clients,
            settings,
            dimension=args.dimension,
            categoria=args.categoria,
            prompt=args.prompt,
            segments=segments,
            attribute=args.attribute,
            values=args.values,
            project=args.project,
            top_k=args.top_k,
            limit=args.limit,
            refresh_views=args.refresh,
        )
    finally:
        clients.close()

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    logger.info("transversal.dashboard.complete", etapa="etapa6_transversal")


def cmd_report_outline(args):
    logger = args.logger
    logger.info("report.outline.begin", etapa="etapa9_informe")
    settings, clients = build_context(args.env)
    try:
        outline = reporting_utils.graph_outline(clients, settings, project=args.project)
    finally:
        clients.close()
    print(json.dumps(outline, ensure_ascii=False, indent=2))
    logger.info("report.outline.complete", etapa="etapa9_informe", categorias=len(outline))


def cmd_report_build(args):
    logger = args.logger
    logger.info(
        "report.build.begin",
        etapa="etapa9_informe",
        output=str(args.output),
        annex=str(args.annex_dir),
        manifest=str(args.manifest),
    )
    settings, clients = build_context(args.env)
    try:
        payload = reporting_utils.build_integrated_report(
            clients,
            settings,
            project=args.project,
            categoria_nucleo=args.categoria_nucleo,
            prompt_nucleo=args.prompt_nucleo,
            quote_limit=args.quote_limit,
            cross_tab_limit=args.cross_tab_limit,
            dimensions=args.dimension,
            output_path=args.output,
            annex_dir=args.annex_dir,
            manifest_path=args.manifest,
        )
    finally:
        clients.close()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    logger.info(
        "report.build.complete",
        etapa="etapa9_informe",
        report=payload.get("report_path"),
    )


def cmd_validation_curve(args):
    logger = args.logger
    logger.info(
        "validation.curve.begin",
        etapa="etapa8_validacion",
        window=args.window,
        threshold=args.threshold,
    )
    settings, clients = build_context(args.env)
    try:
        payload = validation_utils.saturation_curve(
            clients.postgres,
            project=args.project,
            window=args.window,
            threshold=args.threshold,
        )
    finally:
        clients.close()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    plateau = payload.get("plateau", {}).get("plateau")
    logger.info("validation.curve.complete", etapa="etapa8_validacion", plateau=plateau)


def cmd_validation_outliers(args):
    logger = args.logger
    fragment_ids = args.fragment_id or []
    logger.info(
        "validation.outliers.begin",
        etapa="etapa8_validacion",
        fragmentos=len(fragment_ids),
        archivo=args.archivo,
        threshold=args.threshold,
    )
    settings, clients = build_context(args.env)
    try:
        payload = validation_utils.semantic_outliers(
            clients,
            settings,
            project=args.project,
            fragment_ids=fragment_ids or None,
            archivo=args.archivo,
            limit=args.limit,
            neighbor_k=args.neighbors,
            threshold=args.threshold,
        )
    finally:
        clients.close()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    logger.info(
        "validation.outliers.complete",
        etapa="etapa8_validacion",
        outliers=payload.get("outliers"),
    )


def cmd_validation_overlap(args):
    logger = args.logger
    logger.info("validation.overlap.begin", etapa="etapa8_validacion", limit=args.limit)
    settings, clients = build_context(args.env)
    try:
        payload = validation_utils.neo4j_source_overlap(
            clients,
            settings,
            project=args.project,
            limit=args.limit,
        )
    finally:
        clients.close()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    logger.info("validation.overlap.complete", etapa="etapa8_validacion")


def cmd_validation_member(args):
    logger = args.logger
    logger.info(
        "validation.member.begin",
        etapa="etapa8_validacion",
        actor=args.actor,
        archivo=args.archivo,
        limit=args.limit,
    )
    settings, clients = build_context(args.env)
    try:
        payload = validation_utils.member_checking(
            clients,
            project=args.project,
            actor_principal=args.actor,
            archivo=args.archivo,
            limit=args.limit,
        )
    finally:
        clients.close()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    logger.info(
        "validation.member.complete",
        etapa="etapa8_validacion",
        paquetes=payload.get("total_paquetes"),
    )


def cmd_transcribe(args):
    """Transcribe archivo de audio con diarización."""
    logger = args.logger
    audio_path = Path(args.audio_file)
    
    logger.info(
        "transcribe.command.begin",
        etapa="etapa0_transcripcion",
        audio=str(audio_path),
        diarize=args.diarize,
        output=str(args.output) if args.output else None,
        ingest=args.ingest,
    )
    
    settings = load_settings(args.env)
    
    try:
        # Transcribir audio (usa ffmpeg para dividir archivos grandes automáticamente)
        result = transcribe_audio_chunked(
            audio_path,
            settings,
            diarize=args.diarize,
            language=args.language,
        )
        
        print(f"Transcripción completada:")
        print(f"  Speakers detectados: {result.speaker_count}")
        print(f"  Segmentos: {len(result.segments)}")
        print(f"  Duración: {result.duration_seconds:.1f}s")
        
        # Guardar DOCX si se solicita
        if args.output:
            output_path = save_transcription_docx(result, args.output)
            print(f"  DOCX guardado: {output_path}")
            logger.info("transcribe.docx_saved", path=str(output_path))
        
        # Ingestar directamente si se solicita
        if args.ingest:
            from app.clients import build_service_clients
            from app.ingestion import ingest_documents
            
            clients = build_service_clients(settings)
            try:
                # Convertir a fragmentos
                fragments = audio_to_fragments(
                    audio_path,
                    settings,
                    diarize=args.diarize,
                    min_chars=args.min_chars,
                    max_chars=args.max_chars,
                )
                
                if fragments:
                    # Crear archivo DOCX temporal para ingesta
                    import tempfile
                    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
                        tmp_path = Path(tmp.name)
                    
                    save_transcription_docx(result, tmp_path)
                    
                    # Ingestar usando el pipeline existente
                    ingest_result = ingest_documents(
                        clients,
                        settings,
                        files=[tmp_path],
                        batch_size=20,
                        min_chars=args.min_chars,
                        max_chars=args.max_chars,
                        run_id=args.run_id,
                        logger=logger,
                        project=args.project,
                    )
                    
                    # Limpiar archivo temporal
                    tmp_path.unlink(missing_ok=True)
                    
                    totals = ingest_result.get("totals", {})
                    print(f"  Fragmentos ingestados: {totals.get('fragments_total', 0)}")
                    logger.info(
                        "transcribe.ingested",
                        fragments=totals.get("fragments_total", 0),
                        project=args.project,
                    )
            finally:
                clients.close()
        
        # Mostrar preview de transcripción
        if args.preview:
            print("\n--- Preview de transcripción ---")
            for seg in result.segments[:5]:
                speaker = seg.speaker
                text = seg.text[:100] + ("..." if len(seg.text) > 100 else "")
                print(f"[{speaker}] {text}")
            if len(result.segments) > 5:
                print(f"... y {len(result.segments) - 5} segmentos más")
        
    except ValueError as exc:
        logger.error("transcribe.error", error=str(exc))
        print(f"Error: {exc}")
        raise SystemExit(1)
    except Exception as exc:
        logger.exception("transcribe.error", error=str(exc))
        print(f"Error inesperado: {exc}")
        raise SystemExit(1)
    
    logger.info("transcribe.command.complete", etapa="etapa0_transcripcion")


def cmd_analyze(args):
    logger = args.logger
    docx_path = Path(args.docx)
    run_id = getattr(args, "run_id", None)
    logger.info(
        "analyze.command.begin",
        etapa="etapa_llm",
        docx=str(docx_path),
        persist=args.persist,
        table=args.table,
        table_axial=args.table_axial,
    )
    settings, clients = build_context(args.env)
    try:
        fragments = load_fragments(docx_path)
        logger.info("analyze.fragments", etapa="etapa_llm", count=len(fragments))
        result = analyze_interview_text(
            clients,
            settings,
            fragments,
            fuente=docx_path.name,
            project_id=getattr(args, "project", None),
            run_id=run_id,
            request_id=None,
        )
        if args.persist:
            persist_analysis(clients, settings, docx_path.name, result, run_id=run_id, request_id=None)
            logger.info("analyze.persisted", etapa="etapa_llm", archivo=docx_path.name)
        if args.table:
            df = matriz_etapa3(result)
            print(df)
        if args.table_axial:
            df_axial = matriz_etapa4(result)
            print(df_axial)
        print(modelo_ascii(result))
    finally:
        clients.close()

    logger.info("analyze.command.complete", etapa="etapa_llm")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pipeline de entrevistas en mini bloques")
    parser.add_argument("--env", help="Ruta a archivo .env", default=None)
    parser.add_argument("--log-level", default="INFO", help="Nivel de logging estructurado")
    parser.add_argument("--run-id", help="Identificador de ejecucion (auto generado si se omite)")
    parser.add_argument("--project", help="Proyecto activo (slug o nombre)", default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="Ingestar entrevistas .docx")
    p_ingest.add_argument("inputs", nargs="+", type=Path, help="Archivos .docx a procesar")
    p_ingest.add_argument("--batch-size", type=int, default=64)
    p_ingest.add_argument("--min-chars", type=int, default=200)
    p_ingest.add_argument("--max-chars", type=int, default=1200)
    p_ingest.add_argument("--meta-json", type=Path, help="Ruta a JSON con metadatos por archivo")
    p_ingest.set_defaults(func=cmd_ingest)

    # Transcripción de audio con diarización
    p_transcribe = sub.add_parser("transcribe", help="Transcribir audio con diarización")
    p_transcribe.add_argument("audio_file", type=Path, help="Archivo de audio a transcribir (MP3, WAV, etc)")
    p_transcribe.add_argument("-o", "--output", type=Path, help="Guardar transcripción como DOCX")
    p_transcribe.add_argument("--ingest", action="store_true", help="Ingestar directamente al pipeline")
    p_transcribe.add_argument("--no-diarize", dest="diarize", action="store_false", 
                              help="Desactivar diarización (usar transcripción simple)")
    p_transcribe.add_argument("--language", default="es", help="Código de idioma (default: es)")
    p_transcribe.add_argument("--min-chars", type=int, default=200,
                              help="Mínimo de caracteres por fragmento (para ingesta)")
    p_transcribe.add_argument("--max-chars", type=int, default=1200,
                              help="Máximo de caracteres por fragmento (para ingesta)")
    p_transcribe.add_argument("--preview", action="store_true", help="Mostrar preview de la transcripción")
    p_transcribe.set_defaults(func=cmd_transcribe, diarize=True)

    p_search = sub.add_parser("search", help="Consulta semantica en Qdrant")
    p_search.add_argument("query", help="Texto de busqueda")
    p_search.add_argument("--top-k", type=int, default=5)
    p_search.set_defaults(func=cmd_search)

    p_counts = sub.add_parser("counts", help="Conteo de fragmentos en Neo4j")
    p_counts.set_defaults(func=cmd_counts)

    p_neo4j = sub.add_parser("neo4j", help="Consultas directas en Neo4j")
    neo4j_sub = p_neo4j.add_subparsers(dest="neo4j_command", required=True)

    pn_query = neo4j_sub.add_parser("query", help="Ejecuta una sentencia Cypher arbitraria")
    pn_query.add_argument("--cypher", required=True, help="Instruccion Cypher a ejecutar")
    pn_query.add_argument(
        "--param",
        action="append",
        help="Parametro clave=valor. Puede repetirse.",
    )
    pn_query.add_argument(
        "--format",
        action="append",
        choices=["raw", "table", "graph", "all"],
        help="Formato de salida (repetible). Usa 'all' para devolver los tres.",
    )
    pn_query.add_argument(
        "--json",
        action="store_true",
        help="Imprime la salida en JSON (indentado).",
    )
    pn_query.set_defaults(func=cmd_neo4j_query, neo4j_command="query")

    p_sample = sub.add_parser("sample", help="Muestra filas desde PostgreSQL")
    p_sample.add_argument("--limit", type=int, default=3)
    p_sample.add_argument("--json", action="store_true", help="Imprime salida en formato JSON")
    p_sample.set_defaults(func=cmd_sample)

    p_status = sub.add_parser("status", help="Estado consolidado del proyecto iterativo")
    p_status.add_argument("--json", action="store_true", help="Imprime salida en formato JSON")
    p_status.add_argument(
        "--no-update",
        action="store_true",
        help="No persiste metadata/projects/<proyecto>.json con el snapshot detectado",
    )
    p_status.set_defaults(func=cmd_status, no_update=False)

    p_project = sub.add_parser("project", help="Gestion de proyectos")
    project_sub = p_project.add_subparsers(dest="project_command", required=True)

    pj_list = project_sub.add_parser("list", help="Lista proyectos registrados")
    pj_list.add_argument("--json", action="store_true")
    pj_list.set_defaults(func=cmd_project_list, project_command="list")

    pj_create = project_sub.add_parser("create", help="Crea un nuevo proyecto")
    pj_create.add_argument("--name", required=True, help="Nombre descriptivo del proyecto")
    pj_create.add_argument("--description", help="Descripcion opcional del proyecto")
    pj_create.add_argument("--json", action="store_true")
    pj_create.set_defaults(func=cmd_project_create, project_command="create")

    pj_info = project_sub.add_parser("info", help="Detalle de un proyecto")
    pj_info.add_argument("--project", help="Slug o nombre del proyecto", required=True)
    pj_info.add_argument("--json", action="store_true")
    pj_info.set_defaults(func=cmd_project_info, project_command="info")

    p_metadata = sub.add_parser("metadata", help="Gestión de metadatos de entrevistas")
    metadata_sub = p_metadata.add_subparsers(dest="metadata_command", required=True)

    pm_set = metadata_sub.add_parser("set", help="Actualiza metadatos manualmente para una entrevista")
    pm_set.add_argument("--archivo", required=True, help="Nombre del archivo .docx a actualizar")
    pm_set.add_argument(
        "--metadata",
        action="append",
        default=[],
        help="Par clave=valor para metadata adicional (repetible)",
    )
    pm_set.add_argument("--actor-principal", help="Actor principal asociado a la entrevista")
    pm_set.add_argument(
        "--requiere-protocolo-lluvia",
        help="Marca si requiere protocolo de lluvia (true/false)",
    )
    pm_set.add_argument(
        "--fragment",
        action="append",
        help="ID de fragmento específico a actualizar (repetible)",
    )
    pm_set.set_defaults(func=cmd_metadata_set, metadata_command="set")

    pm_apply = metadata_sub.add_parser("apply", help="Aplica metadatos desde archivo JSON o CSV")
    plan_group = pm_apply.add_mutually_exclusive_group(required=True)
    plan_group.add_argument("--plan", type=Path, help="Archivo JSON con entradas de metadatos")
    plan_group.add_argument("--csv", type=Path, help="Archivo CSV con columnas de metadatos")
    pm_apply.set_defaults(func=cmd_metadata_apply, metadata_command="apply")

    p_workflow = sub.add_parser("workflow", help="Avance manual por etapas")
    workflow_sub = p_workflow.add_subparsers(dest="workflow_command", required=True)

    pw_complete = workflow_sub.add_parser("complete", help="Marca una etapa como completada")
    pw_complete.add_argument("--stage", required=True, choices=list(STAGE_DEFINITIONS.keys()))
    pw_complete.add_argument("--notes", help="Notas opcionales registradas con la etapa")
    pw_complete.add_argument("--json", action="store_true")
    pw_complete.set_defaults(func=cmd_workflow_complete, workflow_command="complete")

    p_coding = sub.add_parser("coding", help="Operaciones de codificación abierta")
    coding_sub = p_coding.add_subparsers(dest="coding_command", required=True)

    pc_assign = coding_sub.add_parser("assign", help="Asigna un codigo a un fragmento existente")
    pc_assign.add_argument("--fragment-id", required=True, help="ID del fragmento en entrevista_fragmentos")
    pc_assign.add_argument("--codigo", required=True, help="Nombre del codigo a asignar")
    pc_assign.add_argument("--cita", required=True, help="Cita o justificación para el codigo")
    pc_assign.add_argument("--fuente", help="Fuente / entrevistado/a")
    pc_assign.add_argument("--memo", help="Memo analítico opcional")
    pc_assign.add_argument("--json", action="store_true", help="Imprime salida en formato JSON")
    pc_assign.set_defaults(func=cmd_coding_assign, coding_command='assign')

    pc_suggest = coding_sub.add_parser("suggest", help="Sugerir fragmentos semánticamente similares")
    pc_suggest.add_argument("--fragment-id", required=True, help="Fragmento semilla")
    pc_suggest.add_argument("--top-k", type=int, default=5)
    pc_suggest.add_argument("--archivo", help="Filtra por archivo")
    pc_suggest.add_argument("--area-tematica", help="Filtra por área temática")
    pc_suggest.add_argument("--actor-principal", help="Filtra por actor principal")
    pc_suggest.add_argument("--requiere-protocolo-lluvia", type=lambda v: v.lower() in {"true","1","yes"}, help="Filtra por flag de protocolo de lluvia")
    pc_suggest.add_argument("--include-coded", action="store_true", help="Incluye fragmentos ya codificados")
    pc_suggest.add_argument("--persist", action="store_true", help="Persiste la comparación constante")
    pc_suggest.add_argument(
        "--llm-model",
        choices=["gpt-5.2-chat", "gpt-5-chat", "gpt-5-mini", "gpt-4o-mini"],
        help="Modelo GPT-5 a utilizar para resúmenes",
    )
    pc_suggest.add_argument("--json", action="store_true", help="Imprime salida en formato JSON")
    pc_suggest.set_defaults(func=cmd_coding_suggest, coding_command='suggest')

    pc_stats = coding_sub.add_parser("stats", help="Resumen de cobertura de codificación")
    pc_stats.add_argument("--json", action="store_true", help="Imprime salida en formato JSON")
    pc_stats.set_defaults(func=cmd_coding_stats, coding_command='stats')

    pc_show = coding_sub.add_parser("citations", help="Lista citas registradas para un codigo")
    pc_show.add_argument("--codigo", required=True)
    pc_show.add_argument("--json", action="store_true", help="Imprime salida en formato JSON")
    pc_show.set_defaults(func=cmd_coding_citations, coding_command='citations')

    pc_interviews = coding_sub.add_parser("interviews", help="Lista entrevistas disponibles para codificación")
    pc_interviews.add_argument("--limit", type=int, default=25)
    pc_interviews.add_argument("--json", action="store_true", help="Imprime salida en formato JSON")
    pc_interviews.set_defaults(func=cmd_coding_interviews, coding_command='interviews')

    pc_codes = coding_sub.add_parser("codes", help="Lista códigos abiertos registrados")
    pc_codes.add_argument("--limit", type=int, default=50)
    pc_codes.add_argument("--search", help="Filtra por nombre de código")
    pc_codes.add_argument("--json", action="store_true", help="Imprime salida en formato JSON")
    pc_codes.set_defaults(func=cmd_coding_codes, coding_command='codes')

    pc_fragments = coding_sub.add_parser("fragments", help="Lista fragmentos de una entrevista específica")
    pc_fragments.add_argument("--archivo", required=True, help="Nombre del archivo de entrevista")
    pc_fragments.add_argument("--limit", type=int, default=25)
    pc_fragments.add_argument("--json", action="store_true", help="Imprime salida en formato JSON")
    pc_fragments.set_defaults(func=cmd_coding_fragments, coding_command='fragments')

    p_axial = sub.add_parser("axial", help="Operaciones de codificación axial")
    axial_sub = p_axial.add_subparsers(dest="axial_command", required=True)

    pa_relate = axial_sub.add_parser("relate", help="Crea una relación axial Categoria->Codigo")
    pa_relate.add_argument("--categoria", required=True)
    pa_relate.add_argument("--codigo", required=True)
    pa_relate.add_argument("--tipo", required=True, choices=sorted(ALLOWED_REL_TYPES))
    pa_relate.add_argument("--evidencia", nargs='+', required=True, help="IDs de fragmentos (>=2)")
    pa_relate.add_argument("--memo")
    pa_relate.set_defaults(func=cmd_axial_relate, axial_command='relate')

    pa_gds = axial_sub.add_parser("gds", help="Ejecuta algoritmos GDS sobre el grafo axial")
    pa_gds.add_argument("--algorithm", required=True, choices=['louvain', 'pagerank', 'betweenness'])
    pa_gds.set_defaults(func=cmd_axial_gds, axial_command='gds')

    p_nucleus = sub.add_parser("nucleus", help="Diagnósticos para el núcleo selectivo")
    nucleus_sub = p_nucleus.add_subparsers(dest="nucleus_command", required=True)

    pn_report = nucleus_sub.add_parser("report", help="Genera reporte integral (Neo4j + PG + Qdrant)")
    pn_report.add_argument("--categoria", required=True, help="Nombre de la categoría candidata a núcleo")
    pn_report.add_argument("--prompt", required=True, help="Descripción semántica del núcleo para las probes de Qdrant")
    pn_report.add_argument("--algorithm", default="pagerank", choices=['pagerank', 'betweenness', 'louvain'], help="Algoritmo de centralidad a utilizar")
    pn_report.add_argument("--centrality-top", type=int, default=10, help="Número de categorías a listar en el ranking")
    pn_report.add_argument("--centrality-rank-max", type=int, default=5, help="Rango máximo aceptable para considerar centralidad alta")
    pn_report.add_argument("--probe-top", type=int, default=10, help="Cantidad de citas semánticas a recuperar desde Qdrant")
    pn_report.add_argument("--min-interviews", type=int, default=3, help="Mínimo de entrevistas distintas requeridas")
    pn_report.add_argument("--min-roles", type=int, default=2, help="Mínimo de roles/actores distintos en la evidencia")
    pn_report.add_argument("--min-quotes", type=int, default=5, help="Cantidad mínima de citas icónicas")
    pn_report.add_argument("--quote-limit", type=int, default=10, help="Número de citas a recuperar como muestra")
    pn_report.add_argument("--filter-archivo", help="Filtro opcional de archivo para probe semántica")
    pn_report.add_argument("--filter-area-tematica", help="Filtro opcional de área temática para probe semántica")
    pn_report.add_argument("--filter-actor-principal", help="Filtro opcional de actor principal para probe semántica")
    pn_report.add_argument(
        "--filter-lluvia",
        type=lambda v: v.lower() in {"true", "1", "yes"},
        help="Filtra probes por bandera requiere_protocolo_lluvia (true/false)",
    )
    pn_report.add_argument("--memo", help="Memo analítico para la decisión del núcleo")
    pn_report.add_argument("--persist", action="store_true", help="Persiste memo y resumen del núcleo en PostgreSQL")
    pn_report.add_argument(
        "--llm-model",
        choices=["gpt-5.2-chat", "gpt-5-chat", "gpt-5-mini", "gpt-4o-mini"],
        help="Modelo GPT-5 para generar resumen del núcleo",
    )
    pn_report.set_defaults(func=cmd_nucleus_report, nucleus_command='report')

    p_report = sub.add_parser("report", help="Empaquetado del informe final (Etapa 9)")
    report_sub = p_report.add_subparsers(dest="report_command", required=True)

    pr_outline = report_sub.add_parser("outline", help="Imprime la estructura Categoria->Codigo desde Neo4j")
    pr_outline.set_defaults(func=cmd_report_outline, report_command='outline')

    pr_build = report_sub.add_parser("build", help="Genera informe_integrado.md, anexos y manifiesto")
    pr_build.add_argument("--categoria-nucleo", help="Categoría núcleo opcional para destacar")
    pr_build.add_argument("--prompt-nucleo", help="Prompt asociado al núcleo (usado en nucleus_report)")
    pr_build.add_argument("--quote-limit", type=int, default=5)
    pr_build.add_argument("--cross-tab-limit", type=int, default=50)
    pr_build.add_argument(
        "--dimension",
        choices=['rol', 'genero', 'periodo'],
        default=['rol', 'genero', 'periodo'],
        nargs='+',
        help="Dimensiones para anexos de cross-tab",
    )
    pr_build.add_argument("--output", type=Path, default=Path("informes/informe_integrado.md"))
    pr_build.add_argument("--annex-dir", type=Path, default=Path("informes/anexos"))
    pr_build.add_argument("--manifest", type=Path, default=Path("informes/report_manifest.json"))
    pr_build.set_defaults(func=cmd_report_build, report_command='build')

    p_transversal = sub.add_parser("transversal", help="Comparativas transversales (Etapa 6)")
    transversal_sub = p_transversal.add_subparsers(dest="transversal_command", required=True)

    pt_pg = transversal_sub.add_parser("pg", help="Cross-tab en PostgreSQL")
    pt_pg.add_argument("--dimension", choices=['rol', 'genero', 'periodo'], default='rol')
    pt_pg.add_argument("--categoria", help="Filtra por categoría específica")
    pt_pg.add_argument("--limit", type=int, default=20)
    pt_pg.add_argument("--refresh", action="store_true", help="Refresca materialized views antes de consultar")
    pt_pg.set_defaults(func=cmd_transversal_pg, transversal_command='pg')

    pt_qdrant = transversal_sub.add_parser("qdrant", help="Probes semánticas segmentadas")
    pt_qdrant.add_argument("--prompt", required=True, help="Consulta semántica base")
    pt_qdrant.add_argument(
        "--segment",
        action="append",
        help="Segmento en formato nombre|campo=valor|campo=valor (repetible)",
    )
    pt_qdrant.add_argument("--top-k", type=int, default=10)
    pt_qdrant.set_defaults(func=cmd_transversal_qdrant, transversal_command='qdrant')

    pt_neo = transversal_sub.add_parser("neo4j", help="Resumen de subgrafos por atributo")
    pt_neo.add_argument("--attribute", required=True, choices=['actor_principal', 'genero', 'periodo'])
    pt_neo.add_argument("--values", nargs='+', required=True, help="Valores a comparar")
    pt_neo.add_argument("--limit", type=int, default=10)
    pt_neo.set_defaults(func=cmd_transversal_neo4j, transversal_command='neo4j')

    pt_dash = transversal_sub.add_parser("dashboard", help="Payload consolidado (PG+Qdrant+Neo4j)")
    pt_dash.add_argument("--dimension", choices=['rol', 'genero', 'periodo'], default='genero')
    pt_dash.add_argument("--categoria")
    pt_dash.add_argument("--prompt", required=True)
    pt_dash.add_argument(
        "--segment",
        action="append",
        help="Segmento en formato nombre|campo=valor|campo=valor (repetible)",
    )
    pt_dash.add_argument("--attribute", required=True, choices=['actor_principal', 'genero', 'periodo'])
    pt_dash.add_argument("--values", nargs='+', required=True)
    pt_dash.add_argument("--top-k", type=int, default=10)
    pt_dash.add_argument("--limit", type=int, default=10)
    pt_dash.add_argument("--refresh", action="store_true")
    pt_dash.set_defaults(func=cmd_transversal_dashboard, transversal_command='dashboard')

    p_validation = sub.add_parser("validation", help="Verificación, validación y saturación (Etapa 8)")
    validation_sub = p_validation.add_subparsers(dest="validation_command", required=True)

    pv_curve = validation_sub.add_parser("curve", help="Curva de saturación (nuevos códigos por entrevista)")
    pv_curve.add_argument("--window", type=int, default=3, help="Tamaño de ventana para evaluar plateau")
    pv_curve.add_argument("--threshold", type=int, default=0, help="Máx. de nuevos códigos aceptado en la ventana")
    pv_curve.set_defaults(func=cmd_validation_curve, validation_command='curve')

    pv_out = validation_sub.add_parser("outliers", help="Detección de outliers semánticos en Qdrant")
    pv_out.add_argument("--fragment-id", action="append", help="IDs de fragmentos a evaluar (repetible)")
    pv_out.add_argument("--archivo", help="Limita la búsqueda a un archivo específico (últimos fragmentos si no se indica ID)")
    pv_out.add_argument("--limit", type=int, default=25, help="Cantidad de fragmentos recientes a analizar si no se pasan IDs")
    pv_out.add_argument("--neighbors", type=int, default=2, help="Número de vecinos a consultar en Qdrant")
    pv_out.add_argument("--threshold", type=float, default=0.8, help="Umbral mínimo de score para no considerar outlier")
    pv_out.set_defaults(func=cmd_validation_outliers, validation_command='outliers')

    pv_overlap = validation_sub.add_parser("overlap", help="Triangulación de categorías por fuente en Neo4j")
    pv_overlap.add_argument("--limit", type=int, default=25)
    pv_overlap.set_defaults(func=cmd_validation_overlap, validation_command='overlap')

    pv_member = validation_sub.add_parser("member", help="Paquetes para member checking desde PostgreSQL")
    pv_member.add_argument("--actor", help="Filtra por actor_principal")
    pv_member.add_argument("--archivo", help="Filtra por archivo específico")
    pv_member.add_argument("--limit", type=int, default=50)
    pv_member.set_defaults(func=cmd_validation_member, validation_command='member')

    p_analyze = sub.add_parser("analyze", help="Analiza una entrevista y opcionalmente persiste resultados")
    p_analyze.add_argument("docx", type=Path)
    p_analyze.add_argument("--persist", action="store_true")
    p_analyze.add_argument("--table", action="store_true", help="Imprime tabla de codificacion abierta")
    p_analyze.add_argument("--table-axial", action="store_true", help="Imprime tabla axial")
    p_analyze.set_defaults(func=cmd_analyze)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    run_id = args.run_id or uuid4().hex
    logger = configure_logging(args.log_level)
    logger = bind_run(logger, run_id)

    project_slug: Optional[str] = None
    if args.command != "project":
        if not getattr(args, "project", None):
            print("Error: debes especificar --project para todas las operaciones.")
            return 1
        try:
            project_slug = resolve_project(getattr(args, "project", None), allow_create=False)
        except ValueError as exc:
            print(f"Error: {exc}")
            return 1
        args.project = project_slug
        logger = logger.bind(project=project_slug)
    else:
        # Solo resolvemos el slug si el subcomando lo requiere explícitamente
        if getattr(args, "project_command", None) in {"info"} and getattr(args, "project", None):
            try:
                project_slug = resolve_project(args.project, allow_create=False)
                args.project = project_slug
            except ValueError as exc:
                print(f"Error: {exc}")
                return 1

    args.logger = logger
    args.run_id = run_id

    extra = {}
    if project_slug:
        extra["project"] = project_slug
    if hasattr(args, 'coding_command') and args.coding_command:
        extra['coding_command'] = args.coding_command
    if hasattr(args, 'axial_command') and args.axial_command:
        extra['axial_command'] = args.axial_command
    if hasattr(args, 'nucleus_command') and args.nucleus_command:
        extra['nucleus_command'] = args.nucleus_command
    if hasattr(args, 'transversal_command') and args.transversal_command:
        extra['transversal_command'] = args.transversal_command
    if hasattr(args, 'report_command') and args.report_command:
        extra['report_command'] = args.report_command
    if hasattr(args, 'validation_command') and args.validation_command:
        extra['validation_command'] = args.validation_command
    if hasattr(args, 'project_command') and args.project_command:
        extra['project_command'] = args.project_command
    if hasattr(args, 'workflow_command') and args.workflow_command:
        extra['workflow_command'] = args.workflow_command
    if hasattr(args, 'neo4j_command') and args.neo4j_command:
        extra['neo4j_command'] = args.neo4j_command
    logger.info("command.start", command=args.command, **extra)
    try:
        args.func(args)
        stage_key = STAGE_COMMAND_MAP.get(args.command)
        if stage_key:
            sub_attr = SUBCOMMAND_ATTR.get(args.command)
            subcommand = getattr(args, sub_attr, None) if sub_attr else None
            required = STAGE_REQUIRED_SUBCOMMAND.get(args.command)
            project_for_stage = getattr(args, "project", None)
            if project_for_stage and (not required or (subcommand in required)):
                # Need valid connection for mark_stage
                settings, clients = build_context(args.env)
                try:
                    mark_stage(
                        clients.postgres,
                        project_for_stage,
                        stage_key,
                        run_id=run_id,
                        command=args.command,
                        subcommand=subcommand,
                    )
                except Exception as exc:
                    logger.warning("command.auto_mark_stage.error", error=str(exc))
                finally:
                    clients.close()
        extra = {}
        if hasattr(args, 'coding_command') and args.coding_command:
            extra['coding_command'] = args.coding_command
        if hasattr(args, 'axial_command') and args.axial_command:
            extra['axial_command'] = args.axial_command
        if hasattr(args, 'nucleus_command') and args.nucleus_command:
            extra['nucleus_command'] = args.nucleus_command
        if hasattr(args, 'transversal_command') and args.transversal_command:
            extra['transversal_command'] = args.transversal_command
        if hasattr(args, 'report_command') and args.report_command:
            extra['report_command'] = args.report_command
        if hasattr(args, 'validation_command') and args.validation_command:
            extra['validation_command'] = args.validation_command
        if hasattr(args, 'project_command') and args.project_command:
            extra['project_command'] = args.project_command
        if hasattr(args, 'workflow_command') and args.workflow_command:
            extra['workflow_command'] = args.workflow_command
        if hasattr(args, 'neo4j_command') and args.neo4j_command:
            extra['neo4j_command'] = args.neo4j_command
        logger.info("command.complete", command=args.command, **extra)
    except Exception:
        logger.exception(
            "command.error",
            command=args.command,
            coding_command=getattr(args, "coding_command", None),
            axial_command=getattr(args, "axial_command", None),
            nucleus_command=getattr(args, "nucleus_command", None),
            transversal_command=getattr(args, "transversal_command", None),
            report_command=getattr(args, "report_command", None),
            validation_command=getattr(args, "validation_command", None),
            project_command=getattr(args, "project_command", None),
            workflow_command=getattr(args, "workflow_command", None),
            neo4j_command=getattr(args, "neo4j_command", None),
        )
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
