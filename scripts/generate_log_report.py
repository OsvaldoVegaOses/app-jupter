"""
Script para generar informes automáticos del registro de logs.
Analiza archivos JSONL y genera un reporte Markdown estructurado.

Run: python scripts/generate_log_report.py [--output ruta/informe.md]
"""
import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

LOGS_DIR = Path(__file__).parent.parent / "logs"
DEFAULT_OUTPUT = Path(__file__).parent.parent / "docs" / "informe_logs" / "INFORME_AUTOMATICO.md"


def parse_jsonl_file(filepath: Path) -> list[dict]:
    """Parse a JSONL file and return list of log entries."""
    entries = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    entries.append(entry)
                except json.JSONDecodeError as e:
                    print(f"  Warning: Line {line_num} in {filepath.name} - JSON parse error: {e}")
    except Exception as e:
        print(f"  Error reading {filepath}: {e}")
    return entries


def collect_all_logs(logs_dir: Path) -> list[dict]:
    """Collect all log entries from all JSONL files."""
    all_entries = []
    log_files = sorted(logs_dir.glob("app.jsonl*"))
    
    print(f"\nAnalizando {len(log_files)} archivo(s) de log...")
    for log_file in log_files:
        entries = parse_jsonl_file(log_file)
        print(f"  - {log_file.name}: {len(entries)} registros")
        all_entries.extend(entries)
    
    return all_entries


def analyze_logs(entries: list[dict]) -> dict:
    """Analyze log entries and extract statistics."""
    stats = {
        "total_entries": len(entries),
        "levels": Counter(),
        "events": Counter(),
        "errors": [],
        "warnings": [],
        "projects": set(),
        "files_processed": set(),
        "operations": defaultdict(list),
        "time_range": {"start": None, "end": None},
        "api_calls": Counter(),
        "db_operations": {"neo4j": [], "qdrant": [], "postgres": []},
    }
    
    for entry in entries:
        # Count by level
        level = entry.get("level", "unknown")
        stats["levels"][level] += 1
        
        # Count by event type
        event = entry.get("event", "unknown")
        stats["events"][event] += 1
        
        # Track time range
        timestamp = entry.get("timestamp")
        if timestamp:
            if stats["time_range"]["start"] is None or timestamp < stats["time_range"]["start"]:
                stats["time_range"]["start"] = timestamp
            if stats["time_range"]["end"] is None or timestamp > stats["time_range"]["end"]:
                stats["time_range"]["end"] = timestamp
        
        # Collect errors
        if level == "error":
            stats["errors"].append({
                "event": event,
                "error": entry.get("error", entry.get("message", "Unknown error")),
                "timestamp": timestamp,
                "module": entry.get("module", ""),
                "details": {k: v for k, v in entry.items() 
                          if k not in ["level", "event", "error", "timestamp", "module", "message"]}
            })
        
        # Collect warnings
        if level == "warning":
            stats["warnings"].append({
                "event": event,
                "message": entry.get("message", entry.get("warning", "")),
                "timestamp": timestamp,
            })
        
        # Track projects
        project = entry.get("project") or entry.get("project_id")
        if project:
            stats["projects"].add(project)
        
        # Track files processed
        filename = entry.get("filename") or entry.get("file")
        if filename:
            stats["files_processed"].add(filename)
        
        # Track API calls
        if "api." in event or event.startswith("api_"):
            stats["api_calls"][event] += 1
        
        # Track database operations
        if "neo4j" in event.lower() or "gds" in event.lower():
            stats["db_operations"]["neo4j"].append(entry)
        if "qdrant" in event.lower():
            stats["db_operations"]["qdrant"].append(entry)
        if "postgres" in event.lower() or "pg." in event.lower():
            stats["db_operations"]["postgres"].append(entry)
        
        # Track specific operations
        if "ingest" in event.lower():
            stats["operations"]["ingest"].append(entry)
        if "transcri" in event.lower():
            stats["operations"]["transcription"].append(entry)
        if "analy" in event.lower() or "axial" in event.lower():
            stats["operations"]["analysis"].append(entry)
        if "graphrag" in event.lower():
            stats["operations"]["graphrag"].append(entry)
    
    return stats


def categorize_errors(errors: list[dict]) -> dict:
    """Group errors by category."""
    categories = defaultdict(list)
    
    for err in errors:
        event = err.get("event", "")
        error_msg = str(err.get("error", ""))
        
        # Categorize by type
        if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
            categories["Timeouts"].append(err)
        elif "neo4j" in event.lower() or "gds" in event.lower():
            categories["Neo4j/GDS"].append(err)
        elif "qdrant" in event.lower():
            categories["Qdrant"].append(err)
        elif "postgres" in event.lower():
            categories["PostgreSQL"].append(err)
        elif "transcri" in event.lower() or "audio" in event.lower():
            categories["Transcripción"].append(err)
        elif "api." in event or "azure" in error_msg.lower() or "openai" in error_msg.lower():
            categories["Azure OpenAI API"].append(err)
        elif "validation" in error_msg.lower() or "invalid" in error_msg.lower():
            categories["Validación"].append(err)
        elif "axial" in event.lower() or "analysis" in event.lower():
            categories["Análisis Cualitativo"].append(err)
        else:
            categories["Otros"].append(err)
    
    return dict(categories)


def generate_markdown_report(stats: dict) -> str:
    """Generate a Markdown report from the statistics."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    report = []
    report.append("# INFORME AUTOMÁTICO DE LOGS")
    report.append(f"## Sistema de Análisis Cualitativo - APP_Jupter\n")
    report.append(f"**Generado:** {now}  ")
    
    if stats["time_range"]["start"] and stats["time_range"]["end"]:
        report.append(f"**Período de logs:** {stats['time_range']['start'][:19]} → {stats['time_range']['end'][:19]}  ")
    
    report.append(f"**Total de registros:** {stats['total_entries']}\n")
    
    # Summary section
    report.append("---\n")
    report.append("## 📋 RESUMEN EJECUTIVO\n")
    
    error_count = stats["levels"].get("error", 0)
    warning_count = stats["levels"].get("warning", 0)
    info_count = stats["levels"].get("info", 0)
    
    if error_count == 0:
        report.append("✅ **Estado:** Sin errores críticos detectados\n")
    else:
        report.append(f"⚠️ **Estado:** {error_count} error(es) detectado(s)\n")
    
    # Level distribution
    report.append("### Distribución por Nivel\n")
    report.append("| Nivel | Cantidad | Porcentaje |")
    report.append("|-------|----------|------------|")
    total = stats["total_entries"] or 1
    for level in ["error", "warning", "info", "debug"]:
        count = stats["levels"].get(level, 0)
        pct = (count / total) * 100
        emoji = {"error": "🔴", "warning": "⚠️", "info": "ℹ️", "debug": "🔍"}.get(level, "")
        report.append(f"| {emoji} {level} | {count} | {pct:.1f}% |")
    report.append("")
    
    # Projects
    if stats["projects"]:
        report.append("### Proyectos Activos\n")
        for proj in sorted(stats["projects"]):
            report.append(f"- `{proj}`")
        report.append("")
    
    # Files processed
    if stats["files_processed"]:
        report.append("### Archivos Procesados\n")
        report.append(f"Total: **{len(stats['files_processed'])}** archivos\n")
        for f in sorted(stats["files_processed"]):
            report.append(f"- {f}")
        report.append("")
    
    # Errors section
    report.append("---\n")
    report.append("## 🔴 ERRORES DETECTADOS\n")
    
    if not stats["errors"]:
        report.append("✅ No se detectaron errores durante el período analizado.\n")
    else:
        categorized = categorize_errors(stats["errors"])
        
        for category, errors in sorted(categorized.items(), key=lambda x: -len(x[1])):
            report.append(f"### {category} ({len(errors)} errores)\n")
            
            # Group similar errors
            error_groups = defaultdict(list)
            for err in errors:
                key = str(err.get("error", ""))[:100]
                error_groups[key].append(err)
            
            for error_msg, occurrences in error_groups.items():
                report.append(f"**Error:** `{error_msg[:200]}`  ")
                report.append(f"**Ocurrencias:** {len(occurrences)}  ")
                if occurrences[0].get("event"):
                    report.append(f"**Evento:** `{occurrences[0]['event']}`  ")
                report.append("")
    
    # Warnings section
    report.append("---\n")
    report.append("## ⚠️ ADVERTENCIAS\n")
    
    if not stats["warnings"]:
        report.append("✅ No se detectaron advertencias durante el período analizado.\n")
    else:
        report.append(f"Total: **{len(stats['warnings'])}** advertencias\n")
        
        # Group by event type
        warning_groups = defaultdict(int)
        for w in stats["warnings"]:
            warning_groups[w.get("event", "unknown")] += 1
        
        report.append("| Tipo de Evento | Cantidad |")
        report.append("|----------------|----------|")
        for event, count in sorted(warning_groups.items(), key=lambda x: -x[1])[:10]:
            report.append(f"| `{event}` | {count} |")
        report.append("")
    
    # Operations section
    report.append("---\n")
    report.append("## ✅ OPERACIONES REALIZADAS\n")
    
    ops = stats["operations"]
    
    if ops["ingest"]:
        report.append(f"### Ingesta de Documentos: {len(ops['ingest'])} eventos\n")
        # Count successful ingests
        successes = [e for e in ops["ingest"] if "success" in e.get("event", "") or "complete" in e.get("event", "")]
        if successes:
            report.append(f"- Completados exitosamente: {len(successes)}")
        report.append("")
    
    if ops["transcription"]:
        report.append(f"### Transcripción de Audio: {len(ops['transcription'])} eventos\n")
        report.append("")
    
    if ops["analysis"]:
        report.append(f"### Análisis Cualitativo: {len(ops['analysis'])} eventos\n")
        report.append("")
    
    if ops["graphrag"]:
        report.append(f"### Consultas GraphRAG: {len(ops['graphrag'])} eventos\n")
        report.append("")
    
    # Database operations
    report.append("---\n")
    report.append("## 🗄️ OPERACIONES DE BASE DE DATOS\n")
    
    db_ops = stats["db_operations"]
    report.append("| Base de Datos | Operaciones |")
    report.append("|---------------|-------------|")
    report.append(f"| Neo4j | {len(db_ops['neo4j'])} |")
    report.append(f"| Qdrant | {len(db_ops['qdrant'])} |")
    report.append(f"| PostgreSQL | {len(db_ops['postgres'])} |")
    report.append("")
    
    # Top events
    report.append("---\n")
    report.append("## 📊 EVENTOS MÁS FRECUENTES\n")
    report.append("| Evento | Cantidad |")
    report.append("|--------|----------|")
    for event, count in stats["events"].most_common(15):
        if event != "logging_configured":  # Skip noise
            report.append(f"| `{event}` | {count} |")
    report.append("")
    
    # Footer
    report.append("---\n")
    report.append("*Informe generado automáticamente por `scripts/generate_log_report.py`*")
    
    return "\n".join(report)


def main():
    parser = argparse.ArgumentParser(description="Genera un informe de análisis de logs")
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Ruta del archivo de salida (default: {DEFAULT_OUTPUT})"
    )
    parser.add_argument(
        "--logs-dir", "-l",
        type=Path,
        default=LOGS_DIR,
        help=f"Directorio de logs (default: {LOGS_DIR})"
    )
    args = parser.parse_args()
    
    print("=" * 60)
    print("GENERADOR DE INFORME DE LOGS")
    print("=" * 60)
    
    # Collect logs
    entries = collect_all_logs(args.logs_dir)
    
    if not entries:
        print("\n⚠️ No se encontraron registros de log.")
        return
    
    # Analyze
    print("\nAnalizando registros...")
    stats = analyze_logs(entries)
    
    # Generate report
    print("Generando informe...")
    report = generate_markdown_report(stats)
    
    # Save report
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    
    print(f"\n✅ Informe guardado en: {args.output}")
    print(f"   - Total registros: {stats['total_entries']}")
    print(f"   - Errores: {stats['levels'].get('error', 0)}")
    print(f"   - Advertencias: {stats['levels'].get('warning', 0)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
