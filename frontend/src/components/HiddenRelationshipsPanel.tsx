/**
 * @fileoverview Panel de Relaciones Ocultas.
 *
 * Descubre relaciones latentes que no son obvias a simple vista.
 * Permite confirmar o descartar las sugerencias.
 *
 * @module components/HiddenRelationshipsPanel
 */

import React, { useState, useCallback, useEffect, useMemo } from "react";
import {
    apiFetchJson,
    analyzeHiddenRelationships,
    EpistemicStatement,
    getDiscoveryNavigationHistory,
    getHiddenRelationshipsMetrics,
    logDiscoveryNavigation,
    NavigationHistoryEntry,
    saveAnalysisReport,
    listAnalysisReports,
    AnalysisReport,
} from "../services/api";

function memoBadgeStyle(type: string): React.CSSProperties {
    const t = (type || "").toUpperCase();
    if (t === "OBSERVATION") return { background: "#dcfce7", color: "#166534", borderRadius: "999px", padding: "0.15rem 0.5rem", fontSize: "0.75rem", fontWeight: 700 };
    if (t === "INTERPRETATION") return { background: "#dbeafe", color: "#1e40af", borderRadius: "999px", padding: "0.15rem 0.5rem", fontSize: "0.75rem", fontWeight: 700 };
    if (t === "HYPOTHESIS") return { background: "#fde68a", color: "#92400e", borderRadius: "999px", padding: "0.15rem 0.5rem", fontSize: "0.75rem", fontWeight: 700 };
    if (t === "NORMATIVE_INFERENCE") return { background: "#fbcfe8", color: "#9d174d", borderRadius: "999px", padding: "0.15rem 0.5rem", fontSize: "0.75rem", fontWeight: 700 };
    return { background: "#e5e7eb", color: "#374151", borderRadius: "999px", padding: "0.15rem 0.5rem", fontSize: "0.75rem", fontWeight: 700 };
}

interface HiddenRelationship {
    source: string;
    source_type: string;
    target: string;
    target_type: string;
    score: number;
    reason: string;
    method: string;
    confidence: string;
    evidence_ids?: string[];
    evidence_count?: number;
    supporting_evidence_ids?: string[];
    supporting_evidence_count?: number;
    evidence_kind?: string;
    evidence_gap_reason?: string;
    epistemic_status?: string;
    origin?: string;
    evidence_required?: boolean;
}

interface HiddenRelationshipsResponse {
    suggestions: HiddenRelationship[];
    by_method: Record<string, HiddenRelationship[]>;
    total: number;
}

interface HiddenRelationshipsPanelProps {
    project: string;
}

export function HiddenRelationshipsPanel({ project }: HiddenRelationshipsPanelProps) {
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [response, setResponse] = useState<HiddenRelationshipsResponse | null>(null);
    const [confirming, setConfirming] = useState<string | null>(null);
    const [metrics, setMetrics] = useState<null | {
        coverage_unique_ids_ratio: number;
        avg_pairwise_jaccard: number;
        max_pairwise_jaccard: number;
        max_triple_repeat: number;
        total_evidence_ids: number;
        unique_evidence_ids: number;
        suggestions_total?: number;
        suggestions_with_direct_evidence?: number;
        direct_evidence_ratio?: number;
        suggestions_with_any_evidence?: number;
        any_evidence_ratio?: number;
    }>(null);
    const [navHistory, setNavHistory] = useState<NavigationHistoryEntry[]>([]);
    const [navLimit, setNavLimit] = useState(5);
    const [navFilter, setNavFilter] = useState<"all" | "search" | "refine" | "send_codes">("all");
    const [navExpanded, setNavExpanded] = useState<Record<number, boolean>>({});
    const [selectedKeys, setSelectedKeys] = useState<Record<string, boolean>>({});
    const [batchConfirming, setBatchConfirming] = useState(false);
    const [evidenceExpanded, setEvidenceExpanded] = useState<Record<string, boolean>>({});
    const [previousResponse, setPreviousResponse] = useState<HiddenRelationshipsResponse | null>(null);
    const [previousRunAt, setPreviousRunAt] = useState<string | null>(null);
    const [comparisonAnalysis, setComparisonAnalysis] = useState<string | null>(null);
    const [comparisonLoading, setComparisonLoading] = useState(false);
    const [comparisonError, setComparisonError] = useState<string | null>(null);
    const [aiAnalysis, setAiAnalysis] = useState<string | null>(null);
    const [aiMemoStatements, setAiMemoStatements] = useState<EpistemicStatement[]>([]);
    const [aiLoading, setAiLoading] = useState(false);
    const [aiError, setAiError] = useState<string | null>(null);
    const [reportSaving, setReportSaving] = useState(false);
    const [reportSaved, setReportSaved] = useState<string | null>(null);
    const [reportList, setReportList] = useState<AnalysisReport[]>([]);
    const [reportListLoading, setReportListLoading] = useState(false);
    const [reportListError, setReportListError] = useState<string | null>(null);

    const refreshHistory = useCallback(async () => {
        try {
            const res = await getDiscoveryNavigationHistory(project, navLimit);
            setNavHistory(res.history || []);
        } catch {
            setNavHistory([]);
        }
    }, [project, navLimit]);

    const formatReportDate = useCallback((value?: string | null) => {
        if (!value) return "-";
        try {
            const d = new Date(value);
            if (Number.isNaN(d.getTime())) return String(value);
            return d.toLocaleString();
        } catch {
            return String(value);
        }
    }, []);

    const loadReports = useCallback(async () => {
        if (!project) return;
        setReportListLoading(true);
        setReportListError(null);
        try {
            const res = await listAnalysisReports(project, "hidden_relationships", 50);
            setReportList(Array.isArray(res.reports) ? res.reports : []);
        } catch (err) {
            setReportListError(err instanceof Error ? err.message : "Error cargando informes");
        } finally {
            setReportListLoading(false);
        }
    }, [project]);

    useEffect(() => {
        void refreshHistory();
    }, [refreshHistory]);

    useEffect(() => {
        void loadReports();
    }, [loadReports]);

    const runDiscover = useCallback(async (mode: "parallel" | "replace") => {
        setLoading(true);
        setError(null);
        setAiAnalysis(null);
        setAiMemoStatements([]);
        setAiError(null);
        setComparisonAnalysis(null);
        setComparisonError(null);
        try {
            const result = await apiFetchJson<HiddenRelationshipsResponse>(
                `/api/axial/hidden-relationships?project=${encodeURIComponent(project)}&top_k=30`
            );
            if (mode === "parallel" && response) {
                setPreviousResponse(response);
                setPreviousRunAt(new Date().toISOString());
            }
            if (mode === "replace") {
                setPreviousResponse(null);
                setPreviousRunAt(null);
            }
            setResponse(result);
            const codes = result.suggestions.map((s) => `${s.source}↔${s.target}`);
            await logDiscoveryNavigation({
                project,
                positivos: [],
                negativos: [],
                target_text: null,
                fragments_count: result.total,
                codigos_sugeridos: codes,
                refinamientos_aplicados: {
                    module: "hidden_relationships",
                    top_k: 30,
                    replay_mode: mode,
                },
                action_taken: "search",
            });
            const metricsRes = await getHiddenRelationshipsMetrics(result.suggestions, project);
            setMetrics({
                coverage_unique_ids_ratio: metricsRes.metrics.coverage_unique_ids_ratio,
                avg_pairwise_jaccard: metricsRes.metrics.avg_pairwise_jaccard,
                max_pairwise_jaccard: metricsRes.metrics.max_pairwise_jaccard,
                max_triple_repeat: metricsRes.metrics.max_triple_repeat,
                total_evidence_ids: metricsRes.metrics.total_evidence_ids,
                unique_evidence_ids: metricsRes.metrics.unique_evidence_ids,
                suggestions_total: metricsRes.metrics.suggestions_total,
                suggestions_with_direct_evidence: metricsRes.metrics.suggestions_with_direct_evidence,
                direct_evidence_ratio: metricsRes.metrics.direct_evidence_ratio,
                suggestions_with_any_evidence: metricsRes.metrics.suggestions_with_any_evidence,
                any_evidence_ratio: metricsRes.metrics.any_evidence_ratio,
            });
            await refreshHistory();

            if (mode === "replace") {
                setAiLoading(true);
                try {
                    const aiRes = await analyzeHiddenRelationships(
                        result.suggestions.map((s) => ({
                            source: s.source,
                            target: s.target,
                            score: s.score,
                            reason: s.reason,
                            evidence_ids: s.evidence_ids || [],
                        })),
                        project
                    );
                    setAiAnalysis(aiRes.analysis || null);
                    setAiMemoStatements(Array.isArray(aiRes.memo_statements) ? aiRes.memo_statements : []);
                } catch (err) {
                    setAiError(err instanceof Error ? err.message : "Error en análisis IA");
                } finally {
                    setAiLoading(false);
                }
            }

            if (mode === "parallel" && response) {
                setComparisonLoading(true);
                try {
                    const prevKeys = new Map<string, HiddenRelationship>();
                    response.suggestions.forEach((s) => prevKeys.set(`${s.source}↔${s.target}`, s));
                    const nextKeys = new Map<string, HiddenRelationship>();
                    result.suggestions.forEach((s) => nextKeys.set(`${s.source}↔${s.target}`, s));
                    const diffSuggestions: Array<{ source: string; target: string; score: number; reason?: string; evidence_ids?: string[] }> = [];

                    result.suggestions.forEach((s) => {
                        const key = `${s.source}↔${s.target}`;
                        const status = prevKeys.has(key) ? "mantenida" : "nueva";
                        diffSuggestions.push({
                            source: s.source,
                            target: s.target,
                            score: s.score,
                            reason: `Relación ${status} en nueva corrida`,
                            evidence_ids: s.evidence_ids || [],
                        });
                    });

                    response.suggestions.forEach((s) => {
                        const key = `${s.source}↔${s.target}`;
                        if (!nextKeys.has(key)) {
                            diffSuggestions.push({
                                source: s.source,
                                target: s.target,
                                score: s.score,
                                reason: "Relación removida en nueva corrida",
                                evidence_ids: s.evidence_ids || [],
                            });
                        }
                    });

                    const compareRes = await analyzeHiddenRelationships(diffSuggestions, project);
                    setComparisonAnalysis(compareRes.analysis || null);
                } catch (err) {
                    setComparisonError(err instanceof Error ? err.message : "Error en comparación IA");
                } finally {
                    setComparisonLoading(false);
                }
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : "Error desconocido");
        } finally {
            setLoading(false);
        }
    }, [project, refreshHistory, response]);

    const handleDiscover = useCallback(() => runDiscover("parallel"), [runDiscover]);

    const handleReplayReplace = useCallback(() => runDiscover("replace"), [runDiscover]);

    const handleAIAnalysis = useCallback(async () => {
        if (!response?.suggestions?.length) return;
        setAiLoading(true);
        setAiError(null);
        setReportSaved(null);
        try {
            const result = await analyzeHiddenRelationships(
                response.suggestions.map((s) => ({
                    source: s.source,
                    target: s.target,
                    score: s.score,
                    reason: s.reason,
                    evidence_ids: s.evidence_ids || [],
                })),
                project
            );
            setAiAnalysis(result.analysis || null);
            setAiMemoStatements(Array.isArray(result.memo_statements) ? result.memo_statements : []);
        } catch (err) {
            setAiError(err instanceof Error ? err.message : "Error en análisis IA");
        } finally {
            setAiLoading(false);
        }
    }, [project, response]);

    const handleSaveReport = useCallback(async () => {
        if (!aiAnalysis && aiMemoStatements.length === 0) return;
        setReportSaving(true);
        setReportSaved(null);
        try {
            const title = `Relaciones ocultas - memo IA (${new Date().toLocaleDateString()})`;
            let content = aiAnalysis || "";
            if (aiMemoStatements.length > 0) {
                const lines = aiMemoStatements.map((stmt) => {
                    const evid = Array.isArray((stmt as any).evidence_ids) ? (stmt as any).evidence_ids : [];
                    const evidTxt = evid.length ? ` (evid: ${evid.join(", ")})` : "";
                    return `- [${stmt.type}] ${stmt.text}${evidTxt}`;
                });
                content = `## Memo IA (Relaciones Ocultas)\n\n${lines.join("\n")}`;
            }
            const meta = {
                module: "hidden_relationships",
                suggestions: response?.total || 0,
                metrics: metrics || null,
                suggestions_detail: (response?.suggestions || []).map((s) => ({
                    source: s.source,
                    target: s.target,
                    score: s.score,
                    method: s.method,
                    confidence: s.confidence,
                    reason: s.reason,
                    origin: s.origin,
                    evidence_ids: s.evidence_ids || [],
                    evidence_count: s.evidence_count ?? 0,
                    epistemic_status: s.epistemic_status,
                    evidence_required: s.evidence_required,
                })),
                comparison: previousResponse ? {
                    previous_run_at: previousRunAt,
                    previous_total: previousResponse.total,
                    previous_suggestions: previousResponse.suggestions.map((s) => ({
                        source: s.source,
                        target: s.target,
                        score: s.score,
                        method: s.method,
                        confidence: s.confidence,
                        reason: s.reason,
                        origin: s.origin,
                        evidence_ids: s.evidence_ids || [],
                        evidence_count: s.evidence_count ?? 0,
                        epistemic_status: s.epistemic_status,
                        evidence_required: s.evidence_required,
                    })),
                    comparison_analysis: comparisonAnalysis || null,
                } : null,
                navigation_log: navHistory.map((entry) => ({
                    id: entry.id,
                    busqueda_id: entry.busqueda_id,
                    busqueda_origen_id: entry.busqueda_origen_id,
                    action_taken: entry.action_taken,
                    created_at: entry.created_at,
                    positivos: entry.positivos,
                    negativos: entry.negativos,
                    target_text: entry.target_text,
                    codigos_sugeridos: entry.codigos_sugeridos,
                    fragments_count: entry.fragments_count,
                    refinamientos_aplicados: entry.refinamientos_aplicados,
                    ai_synthesis: entry.ai_synthesis,
                })),
            };
            const res = await saveAnalysisReport(project, "hidden_relationships", title, content, meta);
            if (res?.success) {
                setReportSaved("✅ Informe guardado en analysis_reports");
                await loadReports();
            }
        } catch (err) {
            setReportSaved(`❌ Error al guardar: ${err instanceof Error ? err.message : "Error desconocido"}`);
        } finally {
            setReportSaving(false);
        }
    }, [aiAnalysis, aiMemoStatements, comparisonAnalysis, metrics, navHistory, previousResponse, previousRunAt, project, response, loadReports]);
    const handleConfirm = useCallback(async (rel: HiddenRelationship, relationType: string) => {
        const key = `${rel.source}-${rel.target}`;
        setConfirming(key);
        try {
            const res = await apiFetchJson<{
                prediction_id?: number;
                estado?: string;
                source?: string;
                target?: string;
            }>("/api/axial/confirm-relationship", {
                method: "POST",
                body: JSON.stringify({
                    source: rel.source,
                    target: rel.target,
                    relation_type: relationType,
                    project,
                }),
            });
            const estado = res?.estado || "pendiente";
            const a = res?.source || rel.source;
            const b = res?.target || rel.target;
            const pid = res?.prediction_id ? ` (prediction_id=${res.prediction_id})` : "";
            alert(`Hipotesis encolada: ${a} <-> ${b} (${relationType}) estado=${estado}${pid}`);
            // Remover de la lista
            if (response) {
                setResponse({
                    ...response,
                    suggestions: response.suggestions.filter(
                        s => !(s.source === rel.source && s.target === rel.target)
                    ),
                    total: response.total - 1,
                });
            }
            setSelectedKeys((prev) => {
                if (!prev[key]) return prev;
                const copy = { ...prev };
                delete copy[key];
                return copy;
            });
        } catch (err) {
            alert("Error al confirmar: " + (err instanceof Error ? err.message : String(err)));
        } finally {
            setConfirming(null);
        }
    }, [project, response]);
    const handleConfirmBatch = useCallback(async (relationType: string) => {
        if (!response?.suggestions?.length) return;
        const selected = response.suggestions.filter((rel) => selectedKeys[`${rel.source}-${rel.target}`]);
        if (selected.length === 0) return;
        setBatchConfirming(true);
        let ok = 0;
        let fail = 0;
        const confirmedKeys = new Set<string>();
        for (const rel of selected) {
            const key = `${rel.source}-${rel.target}`;
            try {
                await apiFetchJson("/api/axial/confirm-relationship", {
                    method: "POST",
                    body: JSON.stringify({
                        source: rel.source,
                        target: rel.target,
                        relation_type: relationType,
                        project,
                    }),
                });
                ok += 1;
                confirmedKeys.add(key);
            } catch {
                fail += 1;
            }
        }
        if (response && confirmedKeys.size > 0) {
            setResponse({
                ...response,
                suggestions: response.suggestions.filter(
                    (s) => !confirmedKeys.has(`${s.source}-${s.target}`)
                ),
                total: response.total - confirmedKeys.size,
            });
        }
        setSelectedKeys({});
        setBatchConfirming(false);
        alert(`Encoladas (hipotesis): ${ok}. Fallidas: ${fail}.`);
    }, [project, response, selectedKeys]);
    const getConfidenceColor = (confidence: string) => {
        switch (confidence) {
            case "high": return "#16a34a";
            case "medium": return "#ca8a04";
            case "low": return "#9ca3af";
            default: return "#6b7280";
        }
    };

    const getMethodIcon = (method: string) => {
        switch (method) {
            case "cooccurrence": return "🔗";
            case "shared_category": return "📂";
            case "community": return "🏘️";
            default: return "❓";
        }
    };

    const filteredHistory = navFilter === "all"
        ? navHistory
        : navHistory.filter((entry) => entry.action_taken === navFilter);

    const overlapWarning = metrics && (
        metrics.avg_pairwise_jaccard > 0.35 || metrics.max_pairwise_jaccard > 0.6
    );

    const evidenceSummary = useMemo(() => {
        if (!response?.suggestions?.length) return [] as Array<{ id: string; count: number }>;
        const counts = new Map<string, number>();
        for (const rel of response.suggestions) {
            for (const id of rel.evidence_ids || []) {
                counts.set(id, (counts.get(id) || 0) + 1);
            }
        }
        return Array.from(counts.entries())
            .sort((a, b) => b[1] - a[1])
            .slice(0, 10)
            .map(([id, count]) => ({ id, count }));
    }, [response]);

    return (
        <div className="hidden-rel-panel">
            <h3 className="hidden-rel-panel__title">
                🔍 Descubrir Relaciones Ocultas
            </h3>
            <p className="hidden-rel-panel__desc">
                Encuentra relaciones latentes entre códigos que no son evidentes a simple vista.
            </p>

            <button
                onClick={handleDiscover}
                disabled={loading}
                className="hidden-rel-panel__btn"
            >
                {loading ? "Buscando..." : "🔎 Descubrir Relaciones"}
            </button>

            <button
                onClick={handleReplayReplace}
                disabled={loading}
                className="hidden-rel-panel__btn secondary"
            >
                {loading ? "Re-ejecutando..." : "🔁 Replay (reemplazar)"}
            </button>

            {response && response.suggestions.length > 0 && (
                <button
                    onClick={handleAIAnalysis}
                    disabled={aiLoading}
                    className="hidden-rel-panel__btn secondary"
                >
                    {aiLoading ? "Analizando..." : "🧠 Analizar con IA"}
                </button>
            )}

            {error && <div className="hidden-rel-panel__error">{error}</div>}
            {aiError && <div className="hidden-rel-panel__error">{aiError}</div>}

            {metrics && (
                <div className="hidden-rel-panel__metrics">
                    <h4>Auditoría de evidencia</h4>
                    <div className="hidden-rel-panel__metrics-grid">
                        <div>
                            <strong>Relaciones con evidencia</strong>
                            <div>
                                {(metrics.suggestions_with_direct_evidence ?? 0)}/{(metrics.suggestions_total ?? 0)}
                            </div>
                        </div>
                        <div>
                            <strong>Cobertura</strong>
                            <div>{Math.round(metrics.coverage_unique_ids_ratio * 100)}%</div>
                        </div>
                        <div>
                            <strong>Overlap prom.</strong>
                            <div>{metrics.avg_pairwise_jaccard.toFixed(2)}</div>
                        </div>
                        <div>
                            <strong>Overlap máx.</strong>
                            <div>{metrics.max_pairwise_jaccard.toFixed(2)}</div>
                        </div>
                        <div>
                            <strong>Máx. repetición</strong>
                            <div>{metrics.max_triple_repeat}</div>
                        </div>
                        <div>
                            <strong>Evidencias</strong>
                            <div>{metrics.unique_evidence_ids}/{metrics.total_evidence_ids}</div>
                        </div>
                    </div>
                    {(metrics.suggestions_total ?? 0) > 0 && (metrics.direct_evidence_ratio ?? 0) < 0.6 && (
                        <div className="hidden-rel-panel__metrics-warning">
                            ⚠️ Muchas relaciones no tienen evidencia directa todavía. Son hipótesis estructurales (p.ej. misma categoría/comunidad) y requieren validación.
                        </div>
                    )}
                    {evidenceSummary.length > 0 && (
                        <div className="hidden-rel-panel__evidence-summary">
                            <strong>Evidencias más repetidas</strong>
                            <div className="hidden-rel-panel__evidence-summary-list">
                                {evidenceSummary.map((item) => (
                                    <span key={item.id} className="hidden-rel-panel__evidence-chip">
                                        {item.id} · {item.count}
                                    </span>
                                ))}
                            </div>
                        </div>
                    )}
                    {overlapWarning && (
                        <div className="hidden-rel-panel__metrics-warning">
                            ⚠️ Evidencia con solapamiento alto. Considera diversificar fragmentos de soporte.
                        </div>
                    )}
                </div>
            )}

            {navHistory.length > 0 && (
                <div className="hidden-rel-panel__history">
                    <div className="hidden-rel-panel__history-header">
                        <h4>Log de navegación</h4>
                        <div className="hidden-rel-panel__history-controls">
                            <select
                                value={navFilter}
                                onChange={(e) => setNavFilter(e.target.value as any)}
                                className="hidden-rel-panel__select"
                            >
                                <option value="all">Todas</option>
                                <option value="search">Search</option>
                                <option value="refine">Refine</option>
                                <option value="send_codes">Send codes</option>
                            </select>
                            <button
                                onClick={() => setNavLimit((prev) => (prev === 5 ? 20 : 5))}
                                className="hidden-rel-panel__btn secondary"
                            >
                                {navLimit === 5 ? "Ver 20" : "Ver 5"}
                            </button>
                        </div>
                    </div>
                    <ul>
                        {filteredHistory.map((entry) => (
                            <li key={entry.id}>
                                <div className="hidden-rel-panel__history-row">
                                    <span>{new Date(entry.created_at).toLocaleString()}</span>
                                    <span> · {entry.action_taken}</span>
                                    <span> · sugerencias: {entry.codigos_sugeridos?.length || 0}</span>
                                    <button
                                        onClick={() =>
                                            setNavExpanded((prev) => ({
                                                ...prev,
                                                [entry.id]: !prev[entry.id],
                                            }))
                                        }
                                        className="hidden-rel-panel__link-btn"
                                    >
                                        {navExpanded[entry.id] ? "Ocultar" : "Detalles"}
                                    </button>
                                </div>
                                {navExpanded[entry.id] && (
                                    <div className="hidden-rel-panel__history-detail">
                                        <div>
                                            <strong>Positivos:</strong> {(entry.positivos || []).join(" | ") || "-"}
                                        </div>
                                        <div>
                                            <strong>Negativos:</strong> {(entry.negativos || []).join(" | ") || "-"}
                                        </div>
                                        <div>
                                            <strong>Target:</strong> {entry.target_text || "-"}
                                        </div>
                                        <div>
                                            <strong>Refinamientos:</strong> {entry.refinamientos_aplicados ? JSON.stringify(entry.refinamientos_aplicados) : "-"}
                                        </div>
                                        <div>
                                            <strong>IA:</strong> {entry.ai_synthesis || "-"}
                                        </div>
                                    </div>
                                )}
                            </li>
                        ))}
                    </ul>
                </div>
            )}

            {previousResponse && (
                <div className="hidden-rel-panel__comparison">
                    <h4>Comparación de corridas</h4>
                    <div className="hidden-rel-panel__comparison-meta">
                        <span>Anterior: {previousResponse.total} relaciones</span>
                        {previousRunAt && <span> · {new Date(previousRunAt).toLocaleString()}</span>}
                        {response && <span> · Actual: {response.total} relaciones</span>}
                    </div>
                    {comparisonLoading && <div className="hidden-rel-panel__comparison-loading">Analizando diferencias...</div>}
                    {comparisonError && <div className="hidden-rel-panel__error">{comparisonError}</div>}
                    {comparisonAnalysis && !comparisonLoading && (
                        <div className="hidden-rel-panel__ai">
                            <h4>IA: diferencias entre corridas</h4>
                            <pre>{comparisonAnalysis}</pre>
                        </div>
                    )}
                </div>
            )}

            {response && (
                <div className="hidden-rel-panel__results">
                    <h4>Relaciones Descubiertas ({response.total})</h4>

                    {aiMemoStatements.length > 0 && (
                        <div className="hidden-rel-panel__ai">
                            <h4>Memo IA</h4>
                            <div className="hidden-rel-panel__memo-list">
                                {aiMemoStatements.map((stmt, idx) => (
                                    <div key={`${stmt.type}-${idx}`} className="hidden-rel-panel__memo-item">
                                        <span style={memoBadgeStyle(stmt.type)}>{stmt.type}</span>
                                        <span className="hidden-rel-panel__memo-text">{stmt.text}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {aiAnalysis && aiMemoStatements.length === 0 && (
                        <div className="hidden-rel-panel__ai">
                            <h4>Memo IA</h4>
                            <pre>{aiAnalysis}</pre>
                        </div>
                    )}

                    {(aiAnalysis || aiMemoStatements.length > 0) && (
                        <div className="hidden-rel-panel__ai-actions">
                            <button
                                onClick={handleSaveReport}
                                disabled={reportSaving}
                                className="hidden-rel-panel__btn secondary"
                            >
                                {reportSaving ? "Guardando..." : "💾 Guardar informe"}
                            </button>
                            {reportSaved && <div className="hidden-rel-panel__save-msg">{reportSaved}</div>}
                        </div>
                    )}

                    {response.suggestions.length === 0 ? (
                        <p>No se encontraron relaciones ocultas.</p>
                    ) : (
                        <div className="hidden-rel-panel__list">
                            <div className="hidden-rel-panel__batch">
                                <div>
                                    <strong>Seleccionadas:</strong> {Object.keys(selectedKeys).length}
                                </div>
                                <div className="hidden-rel-panel__batch-actions">
                                    <button
                                        onClick={() => {
                                            if (!response?.suggestions?.length) return;
                                            const all: Record<string, boolean> = {};
                                            response.suggestions.forEach((s) => {
                                                all[`${s.source}-${s.target}`] = true;
                                            });
                                            setSelectedKeys(all);
                                        }}
                                        className="hidden-rel-panel__btn secondary"
                                    >
                                        Seleccionar todo
                                    </button>
                                    <button
                                        onClick={() => setSelectedKeys({})}
                                        className="hidden-rel-panel__btn secondary"
                                    >
                                        Limpiar
                                    </button>
                                </div>
                                <div className="hidden-rel-panel__batch-actions">
                                    <span>Confirmar selección:</span>
                                    {["partede", "causa", "condicion", "consecuencia"].map((tipo) => (
                                        <button
                                            key={tipo}
                                            onClick={() => handleConfirmBatch(tipo)}
                                            disabled={batchConfirming || Object.keys(selectedKeys).length === 0}
                                            className="hidden-rel-panel__action-btn"
                                            title={`Confirmar selección como "${tipo}"`}
                                        >
                                            {tipo}
                                        </button>
                                    ))}
                                </div>
                            </div>
                            {response.suggestions.map((rel, idx) => {
                                const key = `${rel.source}-${rel.target}`;
                                const isConfirming = confirming === key;
                                const selected = !!selectedKeys[key];
                                const evidenceList = rel.evidence_ids || [];
                                const supportingList: string[] = rel.supporting_evidence_ids || [];
                                const showAllEvidence = !!evidenceExpanded[key];
                                const visibleEvidence = showAllEvidence ? evidenceList : evidenceList.slice(0, 8);
                                const remainingEvidence = Math.max(evidenceList.length - visibleEvidence.length, 0);

                                return (
                                    <div key={idx} className="hidden-rel-panel__item">
                                        <div className="hidden-rel-panel__item-header">
                                            <label className="hidden-rel-panel__select-row">
                                                <input
                                                    type="checkbox"
                                                    checked={selected}
                                                    onChange={() =>
                                                        setSelectedKeys((prev) => ({
                                                            ...prev,
                                                            [key]: !prev[key],
                                                        }))
                                                    }
                                                />
                                                <span>Seleccionar</span>
                                            </label>
                                            <span className="hidden-rel-panel__method">
                                                {getMethodIcon(rel.method)}
                                            </span>
                                            <span
                                                className="hidden-rel-panel__confidence"
                                                style={{ color: getConfidenceColor(rel.confidence) }}
                                            >
                                                {rel.confidence === "high" ? "⭐ Alta" :
                                                    rel.confidence === "medium" ? "● Media" : "○ Baja"}
                                            </span>
                                        </div>

                                        <div className="hidden-rel-panel__item-content">
                                            <strong>{rel.source}</strong>
                                            <span className="hidden-rel-panel__arrow">↔</span>
                                            <strong>{rel.target}</strong>
                                        </div>

                                        <div className="hidden-rel-panel__meta">
                                            <span className="hidden-rel-panel__badge">Hipótesis</span>
                                            {rel.origin && (
                                                <span className="hidden-rel-panel__meta-text">Origen: {rel.origin}</span>
                                            )}
                                            <span className="hidden-rel-panel__meta-text">
                                                Evidencia directa: {rel.evidence_count ?? 0}
                                            </span>
                                            {supportingList.length > 0 && (
                                                <span className="hidden-rel-panel__meta-text">
                                                    · soporte: {rel.supporting_evidence_count ?? supportingList.length}
                                                </span>
                                            )}
                                            {rel.evidence_required && (
                                                <span className="hidden-rel-panel__meta-text warning">Requiere evidencia</span>
                                            )}
                                            {rel.epistemic_status && (
                                                <span className="hidden-rel-panel__meta-text">Estado: {rel.epistemic_status}</span>
                                            )}
                                        </div>

                                        <div className="hidden-rel-panel__reason">
                                            {rel.reason}
                                        </div>

                                        {evidenceList.length > 0 ? (
                                            <div className="hidden-rel-panel__evidence">
                                                {visibleEvidence.map((id) => (
                                                    <span key={id} className="hidden-rel-panel__evidence-chip">
                                                        {id}
                                                    </span>
                                                ))}
                                                {remainingEvidence > 0 && (
                                                    <button
                                                        onClick={() =>
                                                            setEvidenceExpanded((prev) => ({
                                                                ...prev,
                                                                [key]: true,
                                                            }))
                                                        }
                                                        className="hidden-rel-panel__link-btn"
                                                    >
                                                        Ver {remainingEvidence} más
                                                    </button>
                                                )}
                                                {showAllEvidence && evidenceList.length > 8 && (
                                                    <button
                                                        onClick={() =>
                                                            setEvidenceExpanded((prev) => ({
                                                                ...prev,
                                                                [key]: false,
                                                            }))
                                                        }
                                                        className="hidden-rel-panel__link-btn"
                                                    >
                                                        Ocultar
                                                    </button>
                                                )}
                                            </div>
                                        ) : (
                                            <div className="hidden-rel-panel__evidence-empty">
                                                Sin evidencia directa todavía
                                                {rel.evidence_gap_reason && (
                                                    <div className="hidden-rel-panel__meta-text">
                                                        Motivo: {rel.evidence_gap_reason}
                                                    </div>
                                                )}
                                                {supportingList.length > 0 && (
                                                    <div className="hidden-rel-panel__evidence supporting">
                                                        <div className="hidden-rel-panel__meta-text">
                                                            Evidencia sugerida (indirecta)
                                                        </div>
                                                        <div>
                                                            {supportingList.slice(0, 8).map((id) => (
                                                                <span key={`support-${id}`} className="hidden-rel-panel__evidence-chip">
                                                                    {id}
                                                                </span>
                                                            ))}
                                                        </div>
                                                    </div>
                                                )}
                                            </div>
                                        )}

                                        <div className="hidden-rel-panel__actions">
                                            <span>Confirmar como:</span>
                                            {["partede", "causa", "condicion", "consecuencia"].map(tipo => (
                                                <button
                                                    key={tipo}
                                                    onClick={() => handleConfirm(rel, tipo)}
                                                    disabled={isConfirming}
                                                    className="hidden-rel-panel__action-btn"
                                                    title={`Confirmar como "${tipo}"`}
                                                >
                                                    {tipo}
                                                </button>
                                            ))}
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>
            )}

            <div className="hidden-rel-panel__reports">
                <div className="hidden-rel-panel__reports-header">
                    <h4>Informes IA guardados (Relaciones Ocultas)</h4>
                    <button
                        onClick={() => void loadReports()}
                        disabled={reportListLoading}
                        className="hidden-rel-panel__btn"
                    >
                        {reportListLoading ? "Cargando..." : "Refrescar"}
                    </button>
                </div>

                {reportListError && (
                    <div className="hidden-rel-panel__error">{reportListError}</div>
                )}

                {!reportListLoading && reportList.length === 0 && (
                    <div className="hidden-rel-panel__reports-empty">
                        No hay informes guardados. Usa "Analizar con IA" y luego "Guardar informe".
                    </div>
                )}

                {reportList.map((report) => {
                    const meta = report?.metadata && typeof report.metadata === "object" ? report.metadata : null;
                    const suggestionsCount = meta && "suggestions" in meta ? Number((meta as any).suggestions) : null;
                    return (
                        <details key={report.id} className="hidden-rel-panel__report">
                            <summary className="hidden-rel-panel__report-summary">
                                <span className="hidden-rel-panel__report-title">
                                    #{report.id} {report.title}
                                </span>
                                <span className="hidden-rel-panel__report-meta">
                                    {formatReportDate(report.created_at)}
                                    {typeof suggestionsCount === "number" && Number.isFinite(suggestionsCount)
                                        ? ` · ${suggestionsCount} sugerencias`
                                        : ""}
                                </span>
                            </summary>

                            <div className="hidden-rel-panel__report-body">
                                <div className="hidden-rel-panel__report-actions">
                                    <button
                                        className="hidden-rel-panel__btn"
                                        onClick={(e) => {
                                            e.preventDefault();
                                            const content = report.content || "";
                                            const blob = new Blob([content], { type: "text/markdown" });
                                            const url = URL.createObjectURL(blob);
                                            const a = document.createElement("a");
                                            a.href = url;
                                            a.download = `hidden-relationships-report-${report.id}.md`;
                                            a.click();
                                            URL.revokeObjectURL(url);
                                        }}
                                    >
                                        Descargar .md
                                    </button>
                                </div>

                                <div className="hidden-rel-panel__report-content">
                                    {report.content}
                                </div>

                                {meta && (
                                    <div className="hidden-rel-panel__report-meta-box">
                                        <strong>Metadata</strong>
                                        <pre>{JSON.stringify(meta, null, 2)}</pre>
                                    </div>
                                )}
                            </div>
                        </details>
                    );
                })}
            </div>

            <style>{`
                .hidden-rel-panel {
                    padding: 1rem;
                    background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
                    border-radius: 0.75rem;
                    margin-bottom: 1rem;
                }
                .hidden-rel-panel__title {
                    margin: 0 0 0.5rem 0;
                    font-size: 1.25rem;
                    color: #92400e;
                }
                .hidden-rel-panel__desc {
                    color: #78350f;
                    font-size: 0.9rem;
                    margin-bottom: 1rem;
                }
                .hidden-rel-panel__btn {
                    padding: 0.75rem 1.5rem;
                    background: #d97706;
                    color: white;
                    border: none;
                    border-radius: 0.5rem;
                    cursor: pointer;
                    font-weight: 600;
                    transition: all 0.2s;
                    margin-right: 0.5rem;
                }
                .hidden-rel-panel__btn.secondary {
                    background: #7c3aed;
                }
                .hidden-rel-panel__btn:hover {
                    background: #b45309;
                }
                .hidden-rel-panel__btn:disabled {
                    opacity: 0.6;
                    cursor: not-allowed;
                }
                .hidden-rel-panel__metrics {
                    margin-top: 1rem;
                    background: #fff7ed;
                    border-radius: 0.5rem;
                    padding: 0.75rem;
                }
                .hidden-rel-panel__metrics-grid {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
                    gap: 0.5rem;
                    font-size: 0.85rem;
                }
                .hidden-rel-panel__metrics-warning {
                    margin-top: 0.5rem;
                    padding: 0.5rem 0.75rem;
                    border-radius: 0.5rem;
                    background: #fef3c7;
                    color: #92400e;
                    font-size: 0.8rem;
                }
                .hidden-rel-panel__evidence-summary {
                    margin-top: 0.6rem;
                    font-size: 0.8rem;
                    color: #7c2d12;
                }
                .hidden-rel-panel__evidence-summary-list {
                    display: flex;
                    flex-wrap: wrap;
                    gap: 0.35rem;
                    margin-top: 0.35rem;
                }
                .hidden-rel-panel__history {
                    margin-top: 1rem;
                    background: #fff;
                    border-radius: 0.5rem;
                    padding: 0.75rem;
                    border: 1px solid #f59e0b;
                }
                .hidden-rel-panel__history-header {
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                    gap: 0.5rem;
                    flex-wrap: wrap;
                }
                .hidden-rel-panel__history-controls {
                    display: flex;
                    align-items: center;
                    gap: 0.5rem;
                }
                .hidden-rel-panel__select {
                    padding: 0.35rem 0.5rem;
                    border: 1px solid #e2e8f0;
                    border-radius: 0.4rem;
                    font-size: 0.8rem;
                    background: white;
                }
                .hidden-rel-panel__history ul {
                    margin: 0.5rem 0 0;
                    padding-left: 1rem;
                    color: #6b7280;
                    font-size: 0.8rem;
                }
                .hidden-rel-panel__history-row {
                    display: flex;
                    align-items: center;
                    gap: 0.5rem;
                    flex-wrap: wrap;
                }
                .hidden-rel-panel__link-btn {
                    background: none;
                    border: none;
                    color: #2563eb;
                    cursor: pointer;
                    padding: 0;
                    font-size: 0.75rem;
                }
                .hidden-rel-panel__link-btn:hover {
                    text-decoration: underline;
                }
                .hidden-rel-panel__history-detail {
                    margin-top: 0.35rem;
                    padding: 0.5rem;
                    background: #f8fafc;
                    border-radius: 0.4rem;
                    color: #475569;
                    font-size: 0.75rem;
                }
                .hidden-rel-panel__comparison {
                    margin-top: 1rem;
                    background: #eef2ff;
                    border-radius: 0.5rem;
                    padding: 0.75rem;
                    border: 1px solid #c7d2fe;
                }
                .hidden-rel-panel__comparison-meta {
                    font-size: 0.8rem;
                    color: #4338ca;
                    margin-bottom: 0.5rem;
                    display: flex;
                    flex-wrap: wrap;
                    gap: 0.5rem;
                }
                .hidden-rel-panel__comparison-loading {
                    font-size: 0.8rem;
                    color: #4f46e5;
                }
                .hidden-rel-panel__batch {
                    display: flex;
                    flex-direction: column;
                    gap: 0.5rem;
                    padding: 0.75rem;
                    background: #fff7ed;
                    border-radius: 0.5rem;
                    border: 1px solid #fed7aa;
                }
                .hidden-rel-panel__batch-actions {
                    display: flex;
                    flex-wrap: wrap;
                    align-items: center;
                    gap: 0.5rem;
                }
                .hidden-rel-panel__select-row {
                    display: flex;
                    align-items: center;
                    gap: 0.35rem;
                    font-size: 0.75rem;
                    color: #7c2d12;
                }
                .hidden-rel-panel__ai {
                    margin: 1rem 0;
                    background: #f5f3ff;
                    border-radius: 0.5rem;
                    padding: 0.75rem;
                }
                .hidden-rel-panel__memo-list {
                    display: flex;
                    flex-direction: column;
                    gap: 0.5rem;
                }
                .hidden-rel-panel__memo-item {
                    display: flex;
                    align-items: center;
                    gap: 0.5rem;
                    font-size: 0.85rem;
                }
                .hidden-rel-panel__memo-text {
                    color: #4c1d95;
                }
                .hidden-rel-panel__ai-actions {
                    margin-top: 0.75rem;
                    display: flex;
                    align-items: center;
                    gap: 0.5rem;
                    flex-wrap: wrap;
                }
                .hidden-rel-panel__save-msg {
                    font-size: 0.8rem;
                    color: #065f46;
                }
                .hidden-rel-panel__error {
                    color: #dc2626;
                    background: #fef2f2;
                    padding: 0.75rem;
                    border-radius: 0.5rem;
                    margin-top: 1rem;
                }
                .hidden-rel-panel__results {
                    margin-top: 1.5rem;
                }
                .hidden-rel-panel__results h4 {
                    margin: 0 0 1rem 0;
                    color: #78350f;
                }
                .hidden-rel-panel__list {
                    display: flex;
                    flex-direction: column;
                    gap: 0.75rem;
                }
                .hidden-rel-panel__item {
                    background: white;
                    border-radius: 0.5rem;
                    padding: 1rem;
                    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                }
                .hidden-rel-panel__item-header {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 0.5rem;
                }
                .hidden-rel-panel__method {
                    font-size: 1.25rem;
                }
                .hidden-rel-panel__confidence {
                    font-size: 0.8rem;
                    font-weight: 600;
                }
                .hidden-rel-panel__item-content {
                    display: flex;
                    align-items: center;
                    gap: 0.5rem;
                    font-size: 1rem;
                    color: #1f2937;
                    margin-bottom: 0.5rem;
                }
                .hidden-rel-panel__meta {
                    display: flex;
                    align-items: center;
                    gap: 0.5rem;
                    font-size: 0.75rem;
                    color: #6b7280;
                    margin-bottom: 0.35rem;
                    flex-wrap: wrap;
                }
                .hidden-rel-panel__badge {
                    background: #fff7ed;
                    color: #9a3412;
                    border: 1px solid #fed7aa;
                    padding: 0.1rem 0.4rem;
                    border-radius: 999px;
                    font-weight: 600;
                }
                .hidden-rel-panel__meta-text {
                    white-space: nowrap;
                }
                .hidden-rel-panel__arrow {
                    color: #d97706;
                }
                .hidden-rel-panel__reason {
                    font-size: 0.85rem;
                    color: #6b7280;
                    font-style: italic;
                    margin-bottom: 0.75rem;
                }
                .hidden-rel-panel__evidence {
                    display: flex;
                    flex-wrap: wrap;
                    gap: 0.35rem;
                    margin-bottom: 0.75rem;
                }
                .hidden-rel-panel__evidence.supporting {
                    padding: 0.5rem;
                    border-radius: 0.5rem;
                    background: #fffbeb;
                    border: 1px solid #fde68a;
                    margin-top: 0.5rem;
                }
                .hidden-rel-panel__evidence-chip {
                    background: #fff;
                    border: 1px dashed #d97706;
                    color: #92400e;
                    padding: 0.15rem 0.45rem;
                    border-radius: 999px;
                    font-size: 0.7rem;
                }
                .hidden-rel-panel__evidence-empty {
                    font-size: 0.75rem;
                    color: #b45309;
                    margin-bottom: 0.75rem;
                }
                .hidden-rel-panel__actions {
                    display: flex;
                    align-items: center;
                    gap: 0.5rem;
                    flex-wrap: wrap;
                }
                .hidden-rel-panel__actions span {
                    font-size: 0.8rem;
                    color: #6b7280;
                }
                .hidden-rel-panel__action-btn {
                    padding: 0.25rem 0.5rem;
                    font-size: 0.75rem;
                    background: #f3f4f6;
                    border: 1px solid #d1d5db;
                    border-radius: 0.25rem;
                    cursor: pointer;
                    transition: all 0.2s;
                }
                .hidden-rel-panel__action-btn:hover {
                    background: #e5e7eb;
                    border-color: #9ca3af;
                }
                .hidden-rel-panel__action-btn:disabled {
                    opacity: 0.5;
                }
                .hidden-rel-panel__reports {
                    margin-top: 1.25rem;
                    padding: 0.75rem;
                    background: #fff;
                    border-radius: 0.75rem;
                    border: 1px solid #f59e0b;
                }
                .hidden-rel-panel__reports-header {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    gap: 0.5rem;
                    margin-bottom: 0.75rem;
                }
                .hidden-rel-panel__reports-header h4 {
                    margin: 0;
                    font-size: 0.95rem;
                    color: #78350f;
                }
                .hidden-rel-panel__reports-empty {
                    font-size: 0.85rem;
                    color: #92400e;
                }
                .hidden-rel-panel__report {
                    background: #fffaf0;
                    border: 1px solid #fed7aa;
                    border-radius: 0.75rem;
                    padding: 0.5rem 0.75rem;
                    margin-bottom: 0.75rem;
                }
                .hidden-rel-panel__report-summary {
                    cursor: pointer;
                    display: flex;
                    flex-direction: column;
                    gap: 0.25rem;
                }
                .hidden-rel-panel__report-title {
                    font-weight: 700;
                    color: #7c2d12;
                }
                .hidden-rel-panel__report-meta {
                    font-size: 0.8rem;
                    color: #92400e;
                }
                .hidden-rel-panel__report-body {
                    margin-top: 0.75rem;
                    display: flex;
                    flex-direction: column;
                    gap: 0.75rem;
                }
                .hidden-rel-panel__report-actions {
                    display: flex;
                    justify-content: flex-end;
                }
                .hidden-rel-panel__report-content {
                    white-space: pre-wrap;
                    background: #fff7ed;
                    border: 1px solid #fed7aa;
                    border-radius: 0.5rem;
                    padding: 0.75rem;
                    font-size: 0.85rem;
                    color: #7c2d12;
                }
                .hidden-rel-panel__report-meta-box {
                    background: #fff;
                    border: 1px dashed #fdba74;
                    border-radius: 0.5rem;
                    padding: 0.5rem 0.75rem;
                    font-size: 0.8rem;
                    color: #92400e;
                }
                .hidden-rel-panel__report-meta-box pre {
                    white-space: pre-wrap;
                    margin: 0.35rem 0 0;
                    font-size: 0.75rem;
                }
            `}</style>
        </div>
    );
}
