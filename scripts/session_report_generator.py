#!/usr/bin/env python3
"""
Session Report Generator - Análisis de logs por sesión.

Genera informes estructurados de cada sesión de usuario que alimentan
métricas de mejora continua para la aplicación.

Uso:
    python scripts/session_report_generator.py --project jd-007 --session 1768744412691-5f4ue11na
    python scripts/session_report_generator.py --project jd-007 --latest
    python scripts/session_report_generator.py --all-recent --days 7
"""
from __future__ import annotations

import argparse
import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class EndpointMetrics:
    """Métricas por endpoint."""
    path: str
    total_calls: int = 0
    success_count: int = 0
    error_count: int = 0
    warning_count: int = 0
    latencies_ms: List[float] = field(default_factory=list)
    error_types: Dict[str, int] = field(default_factory=dict)
    
    @property
    def avg_latency_ms(self) -> float:
        return sum(self.latencies_ms) / len(self.latencies_ms) if self.latencies_ms else 0.0
    
    @property
    def max_latency_ms(self) -> float:
        return max(self.latencies_ms) if self.latencies_ms else 0.0
    
    @property
    def min_latency_ms(self) -> float:
        return min(self.latencies_ms) if self.latencies_ms else 0.0
    
    @property
    def success_rate(self) -> float:
        total = self.success_count + self.error_count
        return (self.success_count / total * 100) if total > 0 else 100.0


@dataclass
class SessionReport:
    """Informe estructurado de una sesión."""
    project_id: str
    session_id: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_minutes: float = 0.0
    
    # Métricas generales
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    warning_count: int = 0
    
    # Autenticación
    auth_failures: int = 0
    auth_success_after_retry: bool = False
    
    # Pool de conexiones
    pool_warnings: int = 0
    pool_exhaustion_events: int = 0
    
    # LLM
    llm_calls: int = 0
    llm_failures: int = 0
    llm_avg_latency_ms: float = 0.0
    
    # Runner
    runner_executions: int = 0
    runner_steps_total: int = 0
    runner_memos_generated: int = 0
    
    # Endpoints más usados
    top_endpoints: List[Dict[str, Any]] = field(default_factory=list)
    
    # Errores únicos
    unique_errors: List[Dict[str, Any]] = field(default_factory=list)
    
    # Patrones de uso
    usage_patterns: Dict[str, Any] = field(default_factory=dict)
    
    # Insights para mejoras
    improvement_insights: List[Dict[str, str]] = field(default_factory=list)
    
    # Métricas de UX
    ux_metrics: Dict[str, Any] = field(default_factory=dict)


class SessionAnalyzer:
    """Analiza logs de sesión y genera informes."""
    
    def __init__(self, logs_dir: Path):
        self.logs_dir = logs_dir
        self.endpoint_metrics: Dict[str, EndpointMetrics] = {}
        self.events: List[Dict[str, Any]] = []
        
    def load_session_logs(self, project: str, session_id: str) -> List[Dict[str, Any]]:
        """Carga logs de una sesión específica."""
        session_log = self.logs_dir / project / session_id / "app.jsonl"
        if not session_log.exists():
            raise FileNotFoundError(f"Session log not found: {session_log}")
        
        events = []
        with open(session_log, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return events
    
    def analyze_session(self, project: str, session_id: str) -> SessionReport:
        """Analiza una sesión y genera el informe."""
        events = self.load_session_logs(project, session_id)
        self.events = events
        
        report = SessionReport(project_id=project, session_id=session_id)
        
        if not events:
            return report
        
        # Tiempos
        timestamps = [e.get("timestamp") for e in events if e.get("timestamp")]
        if timestamps:
            report.start_time = min(timestamps)
            report.end_time = max(timestamps)
            try:
                start = datetime.fromisoformat(report.start_time.replace("Z", "+00:00"))
                end = datetime.fromisoformat(report.end_time.replace("Z", "+00:00"))
                report.duration_minutes = (end - start).total_seconds() / 60
            except Exception:
                pass
        
        # Analizar eventos
        request_starts: Dict[str, Dict[str, Any]] = {}
        
        for event in events:
            evt_type = event.get("event", "")
            level = event.get("level", "info")
            path = event.get("path", "")
            request_id = event.get("request_id", "")
            
            # Contadores generales
            if evt_type == "request.start":
                report.total_requests += 1
                request_starts[request_id] = event
                
            elif evt_type == "request.end":
                status = event.get("status_code") or event.get("status", 0)
                latency = event.get("duration_ms", 0)
                
                # Actualizar métricas de endpoint
                if path not in self.endpoint_metrics:
                    self.endpoint_metrics[path] = EndpointMetrics(path=path)
                em = self.endpoint_metrics[path]
                em.total_calls += 1
                if latency:
                    em.latencies_ms.append(latency)
                
                if 200 <= status < 400:
                    report.successful_requests += 1
                    em.success_count += 1
                else:
                    report.failed_requests += 1
                    em.error_count += 1
                    if status == 401:
                        report.auth_failures += 1
            
            # Warnings
            if level == "warning":
                report.warning_count += 1
                if path not in self.endpoint_metrics:
                    self.endpoint_metrics[path] = EndpointMetrics(path=path)
                self.endpoint_metrics[path].warning_count += 1
                
                # Pool warnings
                if "pool" in event.get("logger", "") or "connection" in str(event.get("error", "")):
                    report.pool_warnings += 1
                    if "exhausted" in str(event.get("error", "")):
                        report.pool_exhaustion_events += 1
            
            # LLM metrics
            if "llm" in evt_type.lower() or "suggest_code" in evt_type:
                if "error" in evt_type or level == "error":
                    report.llm_failures += 1
                else:
                    report.llm_calls += 1
            
            # Runner metrics
            if "runner" in evt_type.lower():
                if "start" in evt_type:
                    report.runner_executions += 1
                if "memo" in evt_type and "saved" in evt_type:
                    report.runner_memos_generated += 1
            
            # Errores únicos
            if level == "error":
                error_msg = str(event.get("error", event.get("message", "")))[:200]
                error_entry = {
                    "timestamp": event.get("timestamp"),
                    "event": evt_type,
                    "error": error_msg,
                    "path": path,
                }
                if not any(e["error"] == error_msg for e in report.unique_errors):
                    report.unique_errors.append(error_entry)
        
        # Top endpoints
        sorted_endpoints = sorted(
            self.endpoint_metrics.values(),
            key=lambda x: x.total_calls,
            reverse=True
        )[:10]
        report.top_endpoints = [
            {
                "path": em.path,
                "calls": em.total_calls,
                "success_rate": round(em.success_rate, 1),
                "avg_latency_ms": round(em.avg_latency_ms, 1),
                "max_latency_ms": round(em.max_latency_ms, 1),
                "warnings": em.warning_count,
            }
            for em in sorted_endpoints
        ]
        
        # Patrones de uso
        report.usage_patterns = self._detect_usage_patterns(events)
        
        # UX Metrics
        report.ux_metrics = self._calculate_ux_metrics(events, report)
        
        # Generar insights para mejoras
        report.improvement_insights = self._generate_improvement_insights(report)
        
        return report
    
    def _detect_usage_patterns(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Detecta patrones de uso del usuario."""
        patterns: Dict[str, Any] = {
            "coding_cycles": 0,
            "discovery_sessions": 0,
            "validation_actions": 0,
            "idle_periods": [],
            "peak_activity_periods": [],
        }
        
        coding_endpoints = ["/api/coding/fragments", "/api/coding/codes"]
        discovery_endpoints = ["/api/discover", "/api/search"]
        validation_endpoints = ["/api/codes/candidates"]
        
        timestamps = []
        for e in events:
            path = e.get("path", "")
            ts = e.get("timestamp")
            
            if any(ep in path for ep in coding_endpoints):
                patterns["coding_cycles"] += 1
            if any(ep in path for ep in discovery_endpoints):
                patterns["discovery_sessions"] += 1
            if any(ep in path for ep in validation_endpoints):
                patterns["validation_actions"] += 1
            
            if ts:
                try:
                    timestamps.append(datetime.fromisoformat(ts.replace("Z", "+00:00")))
                except Exception:
                    pass
        
        # Detectar períodos de inactividad
        if len(timestamps) > 1:
            timestamps.sort()
            for i in range(1, len(timestamps)):
                gap = (timestamps[i] - timestamps[i-1]).total_seconds()
                if gap > 300:  # 5+ minutos
                    patterns["idle_periods"].append({
                        "start": timestamps[i-1].isoformat(),
                        "end": timestamps[i].isoformat(),
                        "duration_seconds": gap,
                    })
        
        return patterns
    
    def _calculate_ux_metrics(self, events: List[Dict[str, Any]], report: SessionReport) -> Dict[str, Any]:
        """Calcula métricas de experiencia de usuario."""
        ux = {
            "time_to_first_action_ms": None,
            "errors_per_minute": 0.0,
            "recovery_from_errors": True,
            "session_completion": "unknown",
            "latency_percentiles": {},
        }
        
        # Time to first successful action
        first_success_ts = None
        first_ts = None
        for e in events:
            ts = e.get("timestamp")
            if not ts:
                continue
            if not first_ts:
                first_ts = ts
            if e.get("event") == "request.end" and 200 <= e.get("status", 0) < 400:
                first_success_ts = ts
                break
        
        if first_ts and first_success_ts:
            try:
                start = datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
                success = datetime.fromisoformat(first_success_ts.replace("Z", "+00:00"))
                ux["time_to_first_action_ms"] = (success - start).total_seconds() * 1000
            except Exception:
                pass
        
        # Errores por minuto
        if report.duration_minutes > 0:
            ux["errors_per_minute"] = round(report.failed_requests / report.duration_minutes, 2)
        
        # ¿Se recuperó de errores iniciales?
        if report.auth_failures > 0:
            ux["recovery_from_errors"] = report.successful_requests > report.auth_failures
        
        # Latencia percentiles
        all_latencies = []
        for em in self.endpoint_metrics.values():
            all_latencies.extend(em.latencies_ms)
        
        if all_latencies:
            all_latencies.sort()
            n = len(all_latencies)
            ux["latency_percentiles"] = {
                "p50": round(all_latencies[int(n * 0.5)], 1),
                "p90": round(all_latencies[int(n * 0.9)], 1),
                "p99": round(all_latencies[min(int(n * 0.99), n-1)], 1),
            }
        
        return ux
    
    def _generate_improvement_insights(self, report: SessionReport) -> List[Dict[str, str]]:
        """Genera insights accionables para mejoras."""
        insights = []
        
        # Insight: Errores de autenticación
        if report.auth_failures > 5:
            insights.append({
                "category": "authentication",
                "priority": "high",
                "issue": f"{report.auth_failures} errores de autenticación detectados",
                "recommendation": "Implementar refresh token automático o mejorar UI de re-login",
                "metric_impact": "Reducir time_to_first_action y fricciones de UX",
            })
        
        # Insight: Pool de conexiones
        if report.pool_warnings > 3:
            insights.append({
                "category": "infrastructure",
                "priority": "medium",
                "issue": f"{report.pool_warnings} warnings de pool de conexiones",
                "recommendation": "Revisar min/max pool size y connection timeout en PostgreSQL",
                "metric_impact": "Reducir latencia y errores de conexión",
            })
        
        if report.pool_exhaustion_events > 0:
            insights.append({
                "category": "infrastructure",
                "priority": "critical",
                "issue": f"Pool exhaustion detectado {report.pool_exhaustion_events} veces",
                "recommendation": "Aumentar pool_maxconn o revisar queries lentas que bloquean conexiones",
                "metric_impact": "Prevenir degradación total del servicio",
            })
        
        # Insight: Fallos LLM
        if report.llm_failures > 0:
            total_llm = report.llm_calls + report.llm_failures
            failure_rate = (report.llm_failures / total_llm * 100) if total_llm > 0 else 0
            if failure_rate > 5:
                insights.append({
                    "category": "ai_integration",
                    "priority": "high",
                    "issue": f"{failure_rate:.1f}% de fallos LLM ({report.llm_failures}/{total_llm})",
                    "recommendation": "Revisar max_tokens, mejorar parsing de JSON, agregar retry con backoff",
                    "metric_impact": "Mejorar tasa de éxito de sugerencias IA",
                })
        
        # Insight: Latencia alta
        ux = report.ux_metrics
        if ux.get("latency_percentiles", {}).get("p90", 0) > 500:
            insights.append({
                "category": "performance",
                "priority": "medium",
                "issue": f"P90 latency > 500ms ({ux['latency_percentiles'].get('p90')}ms)",
                "recommendation": "Optimizar queries lentas, agregar índices, o implementar caché",
                "metric_impact": "Mejorar percepción de velocidad del usuario",
            })
        
        # Insight: Muchos períodos idle
        idle_periods = report.usage_patterns.get("idle_periods", [])
        if len(idle_periods) > 3:
            insights.append({
                "category": "ux",
                "priority": "low",
                "issue": f"{len(idle_periods)} períodos de inactividad detectados",
                "recommendation": "Considerar guías in-app o tooltips para mantener engagement",
                "metric_impact": "Aumentar session duration activa",
            })
        
        # Insight: Endpoints con baja tasa de éxito
        for ep in report.top_endpoints:
            if ep["success_rate"] < 95 and ep["calls"] > 5:
                insights.append({
                    "category": "reliability",
                    "priority": "high",
                    "issue": f"Endpoint {ep['path']} con {ep['success_rate']}% de éxito",
                    "recommendation": f"Investigar errores en este endpoint (avg latency: {ep['avg_latency_ms']}ms)",
                    "metric_impact": "Mejorar fiabilidad de funcionalidad core",
                })
        
        return insights


def generate_markdown_report(report: SessionReport) -> str:
    """Genera informe en formato Markdown."""
    lines = [
        f"# 📊 Informe de Sesión",
        f"",
        f"| Campo | Valor |",
        f"|-------|-------|",
        f"| **Proyecto** | `{report.project_id}` |",
        f"| **Sesión** | `{report.session_id}` |",
        f"| **Inicio** | {report.start_time or 'N/A'} |",
        f"| **Fin** | {report.end_time or 'N/A'} |",
        f"| **Duración** | {report.duration_minutes:.1f} minutos |",
        f"",
        f"---",
        f"",
        f"## 📈 Métricas Generales",
        f"",
        f"| Métrica | Valor |",
        f"|---------|-------|",
        f"| Total requests | {report.total_requests} |",
        f"| Exitosos | {report.successful_requests} |",
        f"| Fallidos | {report.failed_requests} |",
        f"| Warnings | {report.warning_count} |",
        f"| Tasa de éxito | {(report.successful_requests / report.total_requests * 100) if report.total_requests > 0 else 0:.1f}% |",
        f"",
    ]
    
    # Autenticación
    if report.auth_failures > 0:
        lines.extend([
            f"## 🔐 Autenticación",
            f"",
            f"- Errores 401: **{report.auth_failures}**",
            f"- Recuperación: {'✅ Sí' if report.ux_metrics.get('recovery_from_errors') else '❌ No'}",
            f"",
        ])
    
    # Infraestructura
    if report.pool_warnings > 0:
        lines.extend([
            f"## 🔧 Infraestructura",
            f"",
            f"| Métrica | Valor |",
            f"|---------|-------|",
            f"| Pool warnings | {report.pool_warnings} |",
            f"| Pool exhaustion | {report.pool_exhaustion_events} |",
            f"",
        ])
    
    # LLM
    total_llm = report.llm_calls + report.llm_failures
    if total_llm > 0:
        lines.extend([
            f"## 🤖 Integración LLM",
            f"",
            f"| Métrica | Valor |",
            f"|---------|-------|",
            f"| Llamadas totales | {total_llm} |",
            f"| Exitosas | {report.llm_calls} |",
            f"| Fallidas | {report.llm_failures} |",
            f"| Tasa de éxito | {(report.llm_calls / total_llm * 100):.1f}% |",
            f"",
        ])
    
    # Top endpoints
    if report.top_endpoints:
        lines.extend([
            f"## 🔝 Top Endpoints",
            f"",
            f"| Endpoint | Calls | Success % | Avg Latency | Max Latency |",
            f"|----------|-------|-----------|-------------|-------------|",
        ])
        for ep in report.top_endpoints[:8]:
            lines.append(
                f"| `{ep['path'][:40]}` | {ep['calls']} | {ep['success_rate']}% | {ep['avg_latency_ms']}ms | {ep['max_latency_ms']}ms |"
            )
        lines.append("")
    
    # UX Metrics
    ux = report.ux_metrics
    if ux:
        lines.extend([
            f"## 👤 Métricas de UX",
            f"",
            f"| Métrica | Valor |",
            f"|---------|-------|",
            f"| Time to first action | {ux.get('time_to_first_action_ms', 'N/A')}ms |",
            f"| Errores/minuto | {ux.get('errors_per_minute', 0)} |",
        ])
        if ux.get("latency_percentiles"):
            lp = ux["latency_percentiles"]
            lines.extend([
                f"| P50 latency | {lp.get('p50', 'N/A')}ms |",
                f"| P90 latency | {lp.get('p90', 'N/A')}ms |",
                f"| P99 latency | {lp.get('p99', 'N/A')}ms |",
            ])
        lines.append("")
    
    # Patrones de uso
    patterns = report.usage_patterns
    if patterns:
        lines.extend([
            f"## 🔄 Patrones de Uso",
            f"",
            f"| Patrón | Conteo |",
            f"|--------|--------|",
            f"| Ciclos de codificación | {patterns.get('coding_cycles', 0)} |",
            f"| Sesiones de discovery | {patterns.get('discovery_sessions', 0)} |",
            f"| Acciones de validación | {patterns.get('validation_actions', 0)} |",
            f"| Períodos idle | {len(patterns.get('idle_periods', []))} |",
            f"",
        ])
    
    # Errores únicos
    if report.unique_errors:
        lines.extend([
            f"## ❌ Errores Únicos",
            f"",
        ])
        for err in report.unique_errors[:5]:
            lines.append(f"- `{err.get('event', 'unknown')}`: {err.get('error', '')[:100]}")
        lines.append("")
    
    # Insights de mejora (LO MÁS IMPORTANTE)
    if report.improvement_insights:
        lines.extend([
            f"## 💡 Insights para Mejoras",
            f"",
        ])
        for insight in report.improvement_insights:
            priority_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(
                insight.get("priority", "low"), "⚪"
            )
            lines.extend([
                f"### {priority_emoji} [{insight.get('category', 'general').upper()}] {insight.get('issue', '')}",
                f"",
                f"- **Recomendación:** {insight.get('recommendation', '')}",
                f"- **Impacto esperado:** {insight.get('metric_impact', '')}",
                f"",
            ])
    
    lines.extend([
        f"---",
        f"",
        f"*Generado: {datetime.now(tz=None).isoformat()}*",
    ])
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Session Report Generator")
    parser.add_argument("--project", help="Project ID")
    parser.add_argument("--session", help="Session ID")
    parser.add_argument("--latest", action="store_true", help="Analyze latest session")
    parser.add_argument("--all-recent", action="store_true", help="Analyze all recent sessions")
    parser.add_argument("--days", type=int, default=7, help="Days to look back for --all-recent")
    parser.add_argument("--output", help="Output directory for reports")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    args = parser.parse_args()
    
    # Determine logs directory
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    logs_dir = repo_root / "logs"
    
    if not logs_dir.exists():
        print(f"Logs directory not found: {logs_dir}")
        return 1
    
    analyzer = SessionAnalyzer(logs_dir)
    
    if args.latest and args.project:
        # Find latest session
        project_dir = logs_dir / args.project
        if not project_dir.exists():
            print(f"Project not found: {args.project}")
            return 1
        
        sessions = sorted(
            [d for d in project_dir.iterdir() if d.is_dir()],
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )
        if not sessions:
            print(f"No sessions found for project: {args.project}")
            return 1
        
        session_id = sessions[0].name
        print(f"Analyzing latest session: {session_id}")
        
    elif args.session and args.project:
        session_id = args.session
        
    else:
        parser.print_help()
        return 1
    
    try:
        report = analyzer.analyze_session(args.project, session_id)
        
        if args.format == "json":
            output = json.dumps(asdict(report), indent=2, default=str)
        else:
            output = generate_markdown_report(report)
        
        if args.output:
            output_path = Path(args.output)
            output_path.mkdir(parents=True, exist_ok=True)
            ext = ".json" if args.format == "json" else ".md"
            filename = f"session_report_{args.project}_{session_id}{ext}"
            (output_path / filename).write_text(output, encoding="utf-8")
            print(f"Report saved: {output_path / filename}")
        else:
            print(output)
        
        return 0
        
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
