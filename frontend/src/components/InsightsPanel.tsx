/**
 * @fileoverview Panel de Insights - Muestreo Teórico Automatizado
 * 
 * Muestra insights generados automáticamente que sugieren
 * nuevas búsquedas siguiendo el principio de saturación teórica.
 */

import React, { useState, useEffect, useCallback } from "react";
import { apiFetchJson } from "../services/api";

interface Insight {
    id: number;
    source_type: string;
    source_id: string | null;
    insight_type: string;
    content: string;
    suggested_query: Record<string, unknown> | null;
    priority: number;
    status: string;
    created_at: string | null;
}

interface InsightCounts {
    pending: number;
    executed: number;
    dismissed: number;
}

interface InsightsPanelProps {
    project: string;
}

export function InsightsPanel({ project }: InsightsPanelProps) {
    const [insights, setInsights] = useState<Insight[]>([]);
    const [counts, setCounts] = useState<InsightCounts>({ pending: 0, executed: 0, dismissed: 0 });
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [filter, setFilter] = useState<string>("pending");
    const [generating, setGenerating] = useState(false);
    const [executingId, setExecutingId] = useState<number | null>(null);

    const loadInsights = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const data = await apiFetchJson<{ insights: Insight[]; counts: InsightCounts }>("/api/insights/list", {
                method: "POST",
                body: JSON.stringify({ project, status: filter === "all" ? null : filter }),
            });
            setInsights(data.insights || []);
            setCounts(data.counts || { pending: 0, executed: 0, dismissed: 0 });
        } catch (err) {
            setError(err instanceof Error ? err.message : "Error cargando insights");
        } finally {
            setLoading(false);
        }
    }, [project, filter]);

    useEffect(() => {
        loadInsights();
    }, [loadInsights]);

    const handleExecute = async (insightId: number) => {
        setExecutingId(insightId);
        try {
            const result = await apiFetchJson<{ executed: boolean; message: string }>("/api/insights/execute", {
                method: "POST",
                body: JSON.stringify({ insight_id: insightId, project }),
            });
            if (result.executed) {
                loadInsights();
            }
            alert(result.message);
        } catch (err) {
            alert("Error ejecutando insight");
        } finally {
            setExecutingId(null);
        }
    };

    const handleDismiss = async (insightId: number) => {
        try {
            await apiFetchJson("/api/insights/dismiss", {
                method: "POST",
                body: JSON.stringify({ insight_id: insightId, project }),
            });
            loadInsights();
        } catch (err) {
            alert("Error descartando insight");
        }
    };

    const handleGenerate = async () => {
        setGenerating(true);
        try {
            const result = await apiFetchJson<{ insights_created: number }>("/api/insights/generate", {
                method: "POST",
                body: JSON.stringify({ project, source: "coding" }),
            });
            alert(`${result.insights_created} insights generados`);
            loadInsights();
        } catch (err) {
            alert("Error generando insights");
        } finally {
            setGenerating(false);
        }
    };

    const getSourceIcon = (source: string) => {
        switch (source) {
            case "discovery": return "🔍";
            case "coding": return "🧬";
            case "link_prediction": return "🔮";
            case "report": return "📊";
            default: return "💡";
        }
    };

    const getTypeLabel = (type: string) => {
        switch (type) {
            case "explore": return { label: "Explorar", color: "#3b82f6" };
            case "validate": return { label: "Validar", color: "#10b981" };
            case "saturate": return { label: "Saturar", color: "#f59e0b" };
            case "merge": return { label: "Fusionar", color: "#8b5cf6" };
            default: return { label: type, color: "#64748b" };
        }
    };

    return (
        <div className="insights-panel">
            <header className="insights-panel__header">
                <div>
                    <h2>💡 Insights - Muestreo Teórico</h2>
                    <p>Sugerencias automáticas para saturar categorías</p>
                </div>
                <button
                    className="insights-panel__generate"
                    onClick={handleGenerate}
                    disabled={generating}
                >
                    {generating ? "Generando..." : "🔄 Generar desde Códigos"}
                </button>
            </header>

            {/* Filtros */}
            <nav className="insights-panel__filters">
                <button
                    className={`insights-panel__filter ${filter === "pending" ? "active" : ""}`}
                    onClick={() => setFilter("pending")}
                >
                    ⏳ Pendientes ({counts.pending})
                </button>
                <button
                    className={`insights-panel__filter ${filter === "executed" ? "active" : ""}`}
                    onClick={() => setFilter("executed")}
                >
                    ✅ Ejecutados ({counts.executed})
                </button>
                <button
                    className={`insights-panel__filter ${filter === "dismissed" ? "active" : ""}`}
                    onClick={() => setFilter("dismissed")}
                >
                    ❌ Descartados ({counts.dismissed})
                </button>
                <button
                    className={`insights-panel__filter ${filter === "all" ? "active" : ""}`}
                    onClick={() => setFilter("all")}
                >
                    📋 Todos
                </button>
            </nav>

            {loading && <div className="insights-panel__loading">Cargando insights...</div>}
            {error && <div className="insights-panel__error">{error}</div>}

            {/* Lista de insights */}
            <div className="insights-panel__list">
                {insights.length === 0 ? (
                    <p className="insights-panel__empty">
                        No hay insights {filter !== "all" ? filter : ""}.
                        Usa Discovery, Link Prediction o genera desde códigos.
                    </p>
                ) : (
                    insights.map((insight) => {
                        const typeInfo = getTypeLabel(insight.insight_type);
                        return (
                            <div key={insight.id} className="insights-panel__card">
                                <div className="insights-panel__card-header">
                                    <span className="insights-panel__source">
                                        {getSourceIcon(insight.source_type)} {insight.source_type}
                                    </span>
                                    <span
                                        className="insights-panel__type"
                                        style={{ backgroundColor: typeInfo.color }}
                                    >
                                        {typeInfo.label}
                                    </span>
                                    <span className="insights-panel__priority">
                                        ⭐ {(insight.priority * 100).toFixed(0)}%
                                    </span>
                                </div>

                                <p className="insights-panel__content">{insight.content}</p>

                                {insight.suggested_query && (
                                    <div className="insights-panel__query">
                                        <strong>Sugerencia:</strong>{" "}
                                        {JSON.stringify(insight.suggested_query).slice(0, 100)}...
                                    </div>
                                )}

                                {insight.status === "pending" && (
                                    <div className="insights-panel__actions">
                                        <button
                                            className="insights-panel__btn insights-panel__btn--execute"
                                            onClick={() => handleExecute(insight.id)}
                                            disabled={executingId === insight.id}
                                        >
                                            {executingId === insight.id ? "Ejecutando..." : "▶️ Ejecutar"}
                                        </button>
                                        <button
                                            className="insights-panel__btn insights-panel__btn--dismiss"
                                            onClick={() => handleDismiss(insight.id)}
                                        >
                                            ❌ Descartar
                                        </button>
                                    </div>
                                )}

                                {insight.status !== "pending" && (
                                    <div className="insights-panel__status">
                                        Estado: {insight.status === "executed" ? "✅ Ejecutado" : "❌ Descartado"}
                                    </div>
                                )}
                            </div>
                        );
                    })
                )}
            </div>

            <style>{`
        .insights-panel {
          padding: 1.5rem;
          background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
          border-radius: 0.75rem;
        }
        .insights-panel__header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          margin-bottom: 1rem;
        }
        .insights-panel__header h2 {
          margin: 0 0 0.25rem 0;
          font-size: 1.25rem;
          color: #92400e;
        }
        .insights-panel__header p {
          margin: 0;
          color: #a16207;
          font-size: 0.875rem;
        }
        .insights-panel__generate {
          padding: 0.5rem 1rem;
          background: linear-gradient(135deg, #f59e0b, #d97706);
          color: white;
          border: none;
          border-radius: 0.5rem;
          cursor: pointer;
          font-weight: 600;
        }
        .insights-panel__generate:hover {
          background: linear-gradient(135deg, #d97706, #b45309);
        }
        .insights-panel__generate:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
        .insights-panel__filters {
          display: flex;
          gap: 0.5rem;
          margin-bottom: 1rem;
          flex-wrap: wrap;
        }
        .insights-panel__filter {
          padding: 0.4rem 0.8rem;
          background: white;
          border: 1px solid #fbbf24;
          border-radius: 1rem;
          cursor: pointer;
          font-size: 0.85rem;
        }
        .insights-panel__filter.active {
          background: #f59e0b;
          color: white;
          border-color: #d97706;
        }
        .insights-panel__loading {
          text-align: center;
          padding: 2rem;
          color: #92400e;
        }
        .insights-panel__error {
          padding: 1rem;
          background: #fef2f2;
          border: 1px solid #fecaca;
          border-radius: 0.5rem;
          color: #dc2626;
        }
        .insights-panel__empty {
          text-align: center;
          padding: 2rem;
          color: #a16207;
          font-style: italic;
        }
        .insights-panel__list {
          display: flex;
          flex-direction: column;
          gap: 1rem;
        }
        .insights-panel__card {
          background: white;
          border-radius: 0.75rem;
          padding: 1rem;
          border-left: 4px solid #f59e0b;
          box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .insights-panel__card-header {
          display: flex;
          gap: 0.75rem;
          align-items: center;
          margin-bottom: 0.75rem;
        }
        .insights-panel__source {
          font-size: 0.8rem;
          color: #64748b;
          background: #f1f5f9;
          padding: 0.2rem 0.5rem;
          border-radius: 0.25rem;
        }
        .insights-panel__type {
          font-size: 0.7rem;
          color: white;
          padding: 0.2rem 0.5rem;
          border-radius: 0.25rem;
          font-weight: 600;
        }
        .insights-panel__priority {
          font-size: 0.75rem;
          color: #f59e0b;
          margin-left: auto;
        }
        .insights-panel__content {
          margin: 0 0 0.75rem 0;
          color: #1e293b;
          line-height: 1.5;
        }
        .insights-panel__query {
          font-size: 0.8rem;
          color: #64748b;
          background: #f8fafc;
          padding: 0.5rem;
          border-radius: 0.25rem;
          margin-bottom: 0.75rem;
          overflow: hidden;
        }
        .insights-panel__actions {
          display: flex;
          gap: 0.5rem;
        }
        .insights-panel__btn {
          padding: 0.4rem 0.8rem;
          border: none;
          border-radius: 0.5rem;
          cursor: pointer;
          font-size: 0.85rem;
          font-weight: 500;
        }
        .insights-panel__btn--execute {
          background: linear-gradient(135deg, #10b981, #059669);
          color: white;
        }
        .insights-panel__btn--execute:hover {
          background: linear-gradient(135deg, #059669, #047857);
        }
        .insights-panel__btn--execute:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
        .insights-panel__btn--dismiss {
          background: #f1f5f9;
          color: #64748b;
        }
        .insights-panel__btn--dismiss:hover {
          background: #e2e8f0;
        }
        .insights-panel__status {
          font-size: 0.8rem;
          color: #64748b;
          font-style: italic;
        }
      `}</style>
        </div>
    );
}
