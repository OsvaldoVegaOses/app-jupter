/**
 * @fileoverview Panel de Validación de Códigos Candidatos.
 * 
 * Permite validar, rechazar o fusionar códigos propuestos desde:
 * - Discovery (búsqueda exploratoria)
 * - Sugerencias semánticas
 * - LLM (análisis asistido)
 * - Codificación manual
 * 
 * @module components/CodeValidationPanel
 */

import React, { useState, useCallback, useEffect } from "react";
import {
    listCandidates,
    validateCandidate,
    rejectCandidate,
    mergeCandidates,
    promoteCandidates,
    getCodeHistory,
    getCandidateStatsBySource,
    getBacklogHealth,
    getCanonicalExamples,
    getSimilarCodes,
    detectDuplicates,
    CandidateCode,
    CandidateStats,
    BacklogHealth,
    CanonicalExample,
    SimilarCode,
    DuplicatePair,
    CodeHistoryEntry,
} from "../services/api";

import { CodeHistoryModal } from "./CodeHistoryModal";

interface CodeValidationPanelProps {
    project: string;
}

type FilterEstado = "" | "pendiente" | "validado" | "rechazado" | "fusionado";
type FilterFuente = "" | "llm" | "manual" | "discovery" | "semantic_suggestion";

const FUENTE_LABELS: Record<string, string> = {
    llm: "🤖 LLM",
    manual: "📝 Manual",
    discovery: "🔍 Discovery",
    semantic_suggestion: "💡 Sugerencias",
    legacy: "📦 Legacy",
};

const ESTADO_LABELS: Record<string, { label: string; color: string }> = {
    pendiente: { label: "⏳ Pendiente", color: "#f59e0b" },
    validado: { label: "✅ Validado", color: "#10b981" },
    rechazado: { label: "❌ Rechazado", color: "#ef4444" },
    fusionado: { label: "🔗 Fusionado", color: "#6366f1" },
};

export function CodeValidationPanel({ project }: CodeValidationPanelProps) {
    const [candidates, setCandidates] = useState<CandidateCode[]>([]);
    const [stats, setStats] = useState<CandidateStats | null>(null);
    const [health, setHealth] = useState<BacklogHealth | null>(null);
    const [loading, setLoading] = useState(false);
    const [statsLoading, setStatsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Filters
    const [filterEstado, setFilterEstado] = useState<FilterEstado>("pendiente");
    const [filterFuente, setFilterFuente] = useState<FilterFuente>("");
    const [sortOrder, setSortOrder] = useState<"desc" | "asc">("desc");

    // Selection for batch operations
    const [selected, setSelected] = useState<Set<number>>(new Set());

    // Merge modal
    const [showMerge, setShowMerge] = useState(false);
    const [mergeTarget, setMergeTarget] = useState("");
    const [similarCodes, setSimilarCodes] = useState<SimilarCode[]>([]);
    const [loadingSimilar, setLoadingSimilar] = useState(false);

    // Examples modal
    const [showExamples, setShowExamples] = useState(false);
    const [selectedCandidate, setSelectedCandidate] = useState<CandidateCode | null>(null);
    const [canonicalExamples, setCanonicalExamples] = useState<CanonicalExample[]>([]);
    const [loadingExamples, setLoadingExamples] = useState(false);

    // Duplicate detection
    const [showDuplicates, setShowDuplicates] = useState(false);
    const [duplicates, setDuplicates] = useState<DuplicatePair[]>([]);
    const [loadingDuplicates, setLoadingDuplicates] = useState(false);
    const [duplicateThreshold, setDuplicateThreshold] = useState(0.80);

    // Code history modal
    const [showHistory, setShowHistory] = useState(false);
    const [historyCodigo, setHistoryCodigo] = useState<string>("");
    const [historyItems, setHistoryItems] = useState<CodeHistoryEntry[]>([]);
    const [historyLoading, setHistoryLoading] = useState(false);
    const [historyError, setHistoryError] = useState<string | null>(null);

    const loadCandidates = useCallback(async () => {
        if (!project) {
            setCandidates([]);
            setSelected(new Set());
            setError("Selecciona un proyecto para ver candidatos.");
            return;
        }
        setLoading(true);
        setError(null);
        try {
            const result = await listCandidates(project, {
                estado: filterEstado || undefined,
                fuente_origen: filterFuente || undefined,
                limit: 100,
                sort_order: sortOrder,
            });
            setCandidates(result.candidates);
            setSelected(new Set());
        } catch (err) {
            setError(err instanceof Error ? err.message : "Error al cargar candidatos");
        } finally {
            setLoading(false);
        }
    }, [project, filterEstado, filterFuente, sortOrder]);

    const loadStats = useCallback(async () => {
        if (!project) {
            setStats(null);
            return;
        }
        setStatsLoading(true);
        try {
            const result = await getCandidateStatsBySource(project);
            setStats(result);
        } catch (err) {
            console.error("Error loading stats:", err);
        } finally {
            setStatsLoading(false);
        }
    }, [project]);

    const loadHealth = useCallback(async () => {
        if (!project) {
            setHealth(null);
            return;
        }
        try {
            const result = await getBacklogHealth(project);
            setHealth(result);
        } catch (err) {
            console.error("Error loading health:", err);
        }
    }, [project]);

    useEffect(() => {
        // Wrap in async IIFE to handle errors gracefully
        (async () => {
            try {
                await loadCandidates();
            } catch (err) {
                console.error("Failed to load candidates:", err);
                setError("Error al conectar con el servidor. Verifica que la tabla codigos_candidatos exista.");
            }
        })();
        (async () => {
            try {
                await loadStats();
            } catch (err) {
                console.error("Failed to load stats:", err);
            }
        })();
        (async () => {
            try {
                await loadHealth();
            } catch (err) {
                console.error("Failed to load health:", err);
            }
        })();
    }, [project, filterEstado, filterFuente, sortOrder]);

    const handleValidate = async (id: number) => {
        try {
            await validateCandidate(id, project);
            await loadCandidates();
            await loadStats();
        } catch (err) {
            alert("Error: " + (err instanceof Error ? err.message : String(err)));
        }
    };

    const handleReject = async (id: number) => {
        const memo = prompt("Razón del rechazo (opcional):");
        try {
            await rejectCandidate(id, project, memo || undefined);
            await loadCandidates();
            await loadStats();
        } catch (err) {
            alert("Error: " + (err instanceof Error ? err.message : String(err)));
        }
    };

    const handleBatchValidate = async () => {
        if (selected.size === 0) return;
        for (const id of selected) {
            try {
                await validateCandidate(id, project);
            } catch (err) {
                console.error(`Error validating ${id}:`, err);
            }
        }
        await loadCandidates();
        await loadStats();
    };

    const handleBatchReject = async () => {
        if (selected.size === 0) return;
        const memo = prompt("Razón del rechazo (opcional):");
        for (const id of selected) {
            try {
                await rejectCandidate(id, project, memo || undefined);
            } catch (err) {
                console.error(`Error rejecting ${id}:`, err);
            }
        }
        await loadCandidates();
        await loadStats();
    };

    const handleMerge = async () => {
        if (selected.size < 2 || !mergeTarget.trim()) {
            alert("Selecciona al menos 2 candidatos y un código destino.");
            return;
        }
        try {
            await mergeCandidates(project, Array.from(selected), mergeTarget.trim());
            setShowMerge(false);
            setMergeTarget("");
            await loadCandidates();
            await loadStats();
        } catch (err) {
            alert("Error: " + (err instanceof Error ? err.message : String(err)));
        }
    };

    const handlePromote = async () => {
        const validados = candidates.filter(c => c.estado === "validado").map(c => c.id);
        if (validados.length === 0) {
            alert("No hay códigos validados para promover.");
            return;
        }
        if (!confirm(`¿Promover ${validados.length} códigos validados a la lista definitiva?`)) return;
        try {
            const result = await promoteCandidates(project, validados);
            alert(`✅ ${result.promoted_count} códigos promovidos a la lista definitiva.`);
            await loadCandidates();
            await loadStats();
        } catch (err) {
            alert("Error: " + (err instanceof Error ? err.message : String(err)));
        }
    };

    const handleShowHistory = async (codigo: string) => {
        if (!project) {
            alert("Selecciona un proyecto primero.");
            return;
        }
        const clean = (codigo || "").trim();
        if (!clean) return;

        setShowHistory(true);
        setHistoryCodigo(clean);
        setHistoryItems([]);
        setHistoryError(null);
        setHistoryLoading(true);
        try {
            const result = await getCodeHistory(project, clean, 50);
            setHistoryItems(result.history || []);
        } catch (err) {
            setHistoryError(err instanceof Error ? err.message : String(err));
        } finally {
            setHistoryLoading(false);
        }
    };

    // Open examples modal for a candidate
    const handleShowExamples = async (candidate: CandidateCode) => {
        setSelectedCandidate(candidate);
        setShowExamples(true);
        setLoadingExamples(true);
        setCanonicalExamples([]);
        try {
            const result = await getCanonicalExamples(candidate.id, project, 3);
            setCanonicalExamples(result.examples);
        } catch (err) {
            console.error("Error loading examples:", err);
        } finally {
            setLoadingExamples(false);
        }
    };

    // Load similar codes when opening merge modal
    const handleOpenMerge = async () => {
        setShowMerge(true);
        setLoadingSimilar(true);
        setSimilarCodes([]);

        // Get the first selected code to find similar ones
        const firstSelectedId = Array.from(selected)[0];
        const firstCandidate = candidates.find(c => c.id === firstSelectedId);
        if (firstCandidate?.codigo) {
            try {
                const result = await getSimilarCodes(firstCandidate.codigo, project, 5);
                setSimilarCodes(result.similar_codes);
            } catch (err) {
                console.error("Error loading similar codes:", err);
            }
        }
        setLoadingSimilar(false);
    };

    // Detect duplicates Post-Hoc
    const handleDetectDuplicates = async () => {
        setShowDuplicates(true);
        setLoadingDuplicates(true);
        setDuplicates([]);
        try {
            const result = await detectDuplicates(project, duplicateThreshold);
            setDuplicates(result.duplicates);
        } catch (err) {
            console.error("Error detecting duplicates:", err);
            alert("Error al detectar duplicados: " + (err instanceof Error ? err.message : String(err)));
        } finally {
            setLoadingDuplicates(false);
        }
    };

    const toggleSelect = (id: number) => {
        const newSet = new Set(selected);
        if (newSet.has(id)) {
            newSet.delete(id);
        } else {
            newSet.add(id);
        }
        setSelected(newSet);
    };

    const toggleSelectAll = () => {
        if (selected.size === candidates.length) {
            setSelected(new Set());
        } else {
            setSelected(new Set(candidates.map(c => c.id)));
        }
    };

    return (
        <div className="validation-panel">
            <header className="validation-panel__header">
                <div>
                    <h3>🗃️ Bandeja de Códigos Candidatos</h3>
                    <p>Valida, rechaza o fusiona códigos propuestos desde todas las fuentes.</p>
                </div>
                <button onClick={loadCandidates} disabled={loading}>
                    {loading ? "Cargando..." : "🔄 Refrescar"}
                </button>
            </header>

            {/* Stats Summary */}
            {stats && (
                <div className="validation-panel__stats">
                    <div className="stat stat--pending">
                        <span>Pendientes</span>
                        <strong>{stats.totals.pendiente || 0}</strong>
                    </div>
                    <div className="stat stat--validated">
                        <span>Validados</span>
                        <strong>{stats.totals.validado || 0}</strong>
                    </div>
                    <div className="stat stat--rejected">
                        <span>Rechazados</span>
                        <strong>{stats.totals.rechazado || 0}</strong>
                    </div>
                    <div className="stat stat--merged">
                        <span>Fusionados</span>
                        <strong>{stats.totals.fusionado || 0}</strong>
                    </div>
                    <div className="stat stat--total">
                        <span>Total</span>
                        <strong>{stats.total_candidatos}</strong>
                    </div>
                </div>
            )}

            {/* Health Alert */}
            {health && !health.is_healthy && (
                <div className="validation-panel__health-alert">
                    <span>⚠️</span>
                    <div>
                        {health.alerts.map((alert, i) => (
                            <div key={i}>{alert}</div>
                        ))}
                    </div>
                </div>
            )}

            {/* Filters */}
            <div className="validation-panel__filters">
                <label>
                    Estado:
                    <select value={filterEstado} onChange={e => setFilterEstado(e.target.value as FilterEstado)}>
                        <option value="">Todos</option>
                        <option value="pendiente">⏳ Pendiente</option>
                        <option value="validado">✅ Validado</option>
                        <option value="rechazado">❌ Rechazado</option>
                        <option value="fusionado">🔗 Fusionado</option>
                    </select>
                </label>
                <label>
                    Origen:
                    <select value={filterFuente} onChange={e => setFilterFuente(e.target.value as FilterFuente)}>
                        <option value="">Todos</option>
                        <option value="llm">🤖 LLM</option>
                        <option value="manual">📝 Manual</option>
                        <option value="discovery">🔍 Discovery</option>
                        <option value="semantic_suggestion">💡 Sugerencias</option>
                    </select>
                </label>
                <label>
                    Orden:
                    <select value={sortOrder} onChange={e => setSortOrder(e.target.value as "desc" | "asc")}>
                        <option value="desc">📅 Más recientes</option>
                        <option value="asc">📆 Más antiguos</option>
                    </select>
                </label>
                <button
                    onClick={handleDetectDuplicates}
                    className="btn btn--duplicates"
                    disabled={loadingDuplicates}
                >
                    {loadingDuplicates ? "🔄 Analizando..." : "🔍 Detectar Duplicados"}
                </button>
            </div>

            {/* Batch Actions */}
            {filterEstado === "pendiente" && selected.size > 0 && (
                <div className="validation-panel__batch">
                    <span>{selected.size} seleccionados</span>
                    <button onClick={handleBatchValidate} className="btn btn--validate">
                        ✅ Validar todos
                    </button>
                    <button onClick={handleBatchReject} className="btn btn--reject">
                        ❌ Rechazar todos
                    </button>
                    <button onClick={handleOpenMerge} className="btn btn--merge">
                        🔗 Fusionar
                    </button>
                </div>
            )}

            {/* Merge Modal with Similar Codes */}
            {showMerge && (
                <div className="validation-panel__modal">
                    <div className="modal-content modal-content--wide">
                        <h4>🔗 Fusionar {selected.size} códigos</h4>
                        <p>Los códigos seleccionados se marcarán como "fusionados" y sus citas se asignarán al código destino.</p>

                        <input
                            type="text"
                            placeholder="Nombre del código destino"
                            value={mergeTarget}
                            onChange={e => setMergeTarget(e.target.value)}
                        />

                        {/* Similar Codes Suggestions */}
                        {similarCodes.length > 0 && (
                            <div className="similar-codes">
                                <h5>💡 Códigos similares sugeridos:</h5>
                                <div className="similar-codes__list">
                                    {similarCodes.map((sc, i) => (
                                        <button
                                            key={i}
                                            className="similar-code-chip"
                                            onClick={() => setMergeTarget(sc.codigo)}
                                            title={`Score: ${sc.score.toFixed(3)} | ${sc.occurrences} ocurrencias`}
                                        >
                                            {sc.codigo}
                                            <span className="similar-code-score">{(sc.score * 100).toFixed(0)}%</span>
                                        </button>
                                    ))}
                                </div>
                            </div>
                        )}
                        {loadingSimilar && <p className="loading-text">Buscando códigos similares...</p>}

                        <div className="modal-actions">
                            <button onClick={() => { setShowMerge(false); setSimilarCodes([]); }}>Cancelar</button>
                            <button onClick={handleMerge} className="btn btn--merge">Fusionar</button>
                        </div>
                    </div>
                </div>
            )}

            {/* Canonical Examples Modal */}
            {showExamples && selectedCandidate && (
                <div className="validation-panel__modal">
                    <div className="modal-content modal-content--wide">
                        <h4>📋 Ejemplos canónicos de "{selectedCandidate.codigo}"</h4>
                        <p>Citas previamente validadas para este código:</p>

                        {loadingExamples && <p className="loading-text">Cargando ejemplos...</p>}

                        {!loadingExamples && canonicalExamples.length === 0 && (
                            <p className="no-examples">No hay citas validadas previas para este código.</p>
                        )}

                        {!loadingExamples && canonicalExamples.length > 0 && (
                            <div className="examples-list">
                                {canonicalExamples.map((ex, i) => (
                                    <div key={i} className="example-item">
                                        <div className="example-cita">"{ex.cita}"</div>
                                        <div className="example-meta">
                                            📁 {ex.archivo?.slice(0, 25) || "N/A"}
                                            {ex.fuente && <span> | {ex.fuente}</span>}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}

                        <div className="modal-actions">
                            <button onClick={() => { setShowExamples(false); setSelectedCandidate(null); }}>Cerrar</button>
                            <button onClick={() => handleValidate(selectedCandidate.id)} className="btn btn--validate">
                                ✅ Validar este código
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Duplicates Detection Modal */}
            {showDuplicates && (
                <div className="validation-panel__modal">
                    <div className="modal-content modal-content--wide">
                        <h4>🔍 Códigos Duplicados Detectados</h4>
                        <p>
                            Pares de códigos con similitud ≥{(duplicateThreshold * 100).toFixed(0)}%
                            (Levenshtein Post-Hoc)
                        </p>

                        {loadingDuplicates && <p className="loading-text">Analizando...</p>}

                        {!loadingDuplicates && duplicates.length === 0 && (
                            <p className="no-examples">
                                ✅ No se encontraron duplicados con el umbral {(duplicateThreshold * 100).toFixed(0)}%
                            </p>
                        )}

                        {!loadingDuplicates && duplicates.length > 0 && (() => {
                            // Filter out exact duplicates (100% = same code string)
                            const exactDuplicates = duplicates.filter(p => p.code1 === p.code2);
                            const similarPairs = duplicates.filter(p => p.code1 !== p.code2);

                            return (
                                <div className="duplicates-list">
                                    {/* Summary */}
                                    <div style={{
                                        background: '#f0f9ff',
                                        padding: '0.5rem 0.75rem',
                                        borderRadius: '0.375rem',
                                        marginBottom: '0.75rem',
                                        fontSize: '0.85rem'
                                    }}>
                                        <strong>📊 Resumen:</strong>{' '}
                                        {exactDuplicates.length > 0 && (
                                            <span style={{ color: '#6b7280' }}>
                                                {exactDuplicates.length} código(s) repetido(s) exactamente (ignorados) •{' '}
                                            </span>
                                        )}
                                        <span style={{ color: '#0369a1', fontWeight: 600 }}>
                                            {similarPairs.length} par(es) similar(es) para revisar
                                        </span>
                                    </div>

                                    {similarPairs.length === 0 ? (
                                        <p className="no-examples">
                                            ✅ Todos los duplicados son el mismo código repetido (sin variaciones a fusionar)
                                        </p>
                                    ) : (
                                        <>
                                            <table>
                                                <thead>
                                                    <tr>
                                                        <th>Código 1</th>
                                                        <th>Código 2</th>
                                                        <th>Similitud</th>
                                                        <th>Sugerencia</th>
                                                    </tr>
                                                </thead>
                                                <tbody>
                                                    {similarPairs.map((pair, i) => {
                                                        // Suggest keeping the shorter code (usually cleaner)
                                                        const suggested = pair.code1.length <= pair.code2.length ? pair.code1 : pair.code2;
                                                        return (
                                                            <tr key={i}>
                                                                <td>{pair.code1}</td>
                                                                <td>{pair.code2}</td>
                                                                <td>{(pair.similarity * 100).toFixed(0)}%</td>
                                                                <td style={{ color: '#059669', fontWeight: 500 }}>
                                                                    → {suggested}
                                                                </td>
                                                            </tr>
                                                        );
                                                    })}
                                                </tbody>
                                            </table>

                                            <div style={{
                                                marginTop: '1rem',
                                                padding: '0.75rem',
                                                background: 'linear-gradient(135deg, #dcfce7, #d1fae5)',
                                                borderRadius: '0.5rem',
                                                display: 'flex',
                                                justifyContent: 'space-between',
                                                alignItems: 'center',
                                                flexWrap: 'wrap',
                                                gap: '0.5rem'
                                            }}>
                                                <span style={{ fontSize: '0.85rem', color: '#065f46' }}>
                                                    💡 Auto-fusionar usará el código más corto como destino
                                                </span>
                                                <button
                                                    onClick={async () => {
                                                        if (!confirm(`¿Fusionar y validar automáticamente ${similarPairs.length} par(es) de códigos similares?\n\nAcciones:\n1. Fusionar códigos similares al más corto\n2. Validar los códigos destino\n3. Opción de promover a lista definitiva`)) {
                                                            return;
                                                        }

                                                        let mergeSuccess = 0;
                                                        let validateSuccess = 0;
                                                        let errorCount = 0;
                                                        const targetCodes = new Set<string>();

                                                        console.log("🔄 Iniciando proceso de auto-fusión...");
                                                        console.log(`🔍 Pares a procesar: ${similarPairs.length}`);

                                                        // Pre-load ALL pending candidates to ensure we find them for merging
                                                        // (Default load limit is 100, which might miss some duplicates)
                                                        try {
                                                            const allCandidates = await listCandidates(project, {
                                                                estado: 'pendiente',
                                                                limit: 500
                                                            });
                                                            console.log(`📋 Candidatos pendientes cargados: ${allCandidates.candidates.length}`);

                                                            // Step 1: Merge all similar pairs
                                                            for (const pair of similarPairs) {
                                                                const target = pair.code1.length <= pair.code2.length ? pair.code1 : pair.code2;
                                                                const toMerge = pair.code1.length <= pair.code2.length ? pair.code2 : pair.code1;
                                                                targetCodes.add(target.toLowerCase());

                                                                try {
                                                                    // Find candidate IDs for the code to merge using the full list
                                                                    const toMergeCandidates = allCandidates.candidates.filter(c =>
                                                                        c.codigo.trim().toLowerCase() === toMerge.trim().toLowerCase()
                                                                    );

                                                                    console.log(`🔎 Buscando '${toMerge}' -> Encontrados: ${toMergeCandidates.length} IDs: ${toMergeCandidates.map(c => c.id).join(',')}`);

                                                                    if (toMergeCandidates.length > 0) {
                                                                        const result = await mergeCandidates(
                                                                            project,
                                                                            toMergeCandidates.map(c => c.id),
                                                                            target
                                                                        );
                                                                        if (result.success) {
                                                                            mergeSuccess++;
                                                                            console.log(`✅ Fusionado: ${toMerge} -> ${target} (${result.merged_count} registros)`);
                                                                        }
                                                                    } else {
                                                                        console.warn(`⚠️ No se encontraron candidatos pendientes para '${toMerge}'`);
                                                                    }
                                                                } catch (err) {
                                                                    console.error(`❌ Error fusionando ${toMerge} -> ${target}:`, err);
                                                                    errorCount++;
                                                                }
                                                            }
                                                        } catch (err) {
                                                            console.error("❌ Error cargando candidatos para fusión:", err);
                                                            alert("Error crítico cargando candidatos. Revisa la consola.");
                                                            return;
                                                        }

                                                        // Step 2: Validate target codes
                                                        if (mergeSuccess > 0) {
                                                            console.log("🔄 Validando códigos destino...");
                                                            // Reload again to get updated state after merges
                                                            const pageLimit = 500;
                                                            const allPending: CandidateCode[] = [];
                                                            let offset = 0;
                                                            for (let page = 0; page < 20; page++) {
                                                                const pageResult = await listCandidates(project, {
                                                                    estado: 'pendiente',
                                                                    limit: pageLimit,
                                                                    offset,
                                                                });
                                                                allPending.push(...pageResult.candidates);
                                                                if (pageResult.candidates.length < pageLimit) break;
                                                                offset += pageLimit;
                                                            }
                                                            const updatedCandidates: { candidates: CandidateCode[] } = { candidates: allPending };

                                                            for (const targetCode of targetCodes) {
                                                                const targetCandidates = updatedCandidates.candidates.filter((c) =>
                                                                    c.codigo.trim().toLowerCase() === targetCode.trim().toLowerCase()
                                                                );

                                                                for (const candidate of targetCandidates) {
                                                                    try {
                                                                        await validateCandidate(candidate.id, project);
                                                                        validateSuccess++;
                                                                        console.log(`✅ Validado automáticamente: ${candidate.codigo} (ID: ${candidate.id})`);
                                                                    } catch (err) {
                                                                        console.error(`Error validando ${targetCode}:`, err);
                                                                    }
                                                                }
                                                            }
                                                        }

                                                        // Step 3: Reload and offer promotion
                                                        await loadCandidates();
                                                        await loadStats();
                                                        setShowDuplicates(false);

                                                        console.log("🏁 Proceso finalizado.");

                                                        const shouldPromote = confirm(
                                                            `✅ Auto-fusión completada:\n\n` +
                                                            `• ${mergeSuccess} fusiones exitosas\n` +
                                                            `• ${validateSuccess} códigos validados\n` +
                                                            `${errorCount > 0 ? `• ${errorCount} errores\n` : ''}` +
                                                            `\n¿Deseas promover los códigos validados a la Lista Definitiva ahora?`
                                                        );

                                                        if (shouldPromote) {
                                                            const validados = (await listCandidates(project, { estado: 'validado', limit: 200 })).candidates;
                                                            if (validados.length > 0) {
                                                                try {
                                                                    const result = await promoteCandidates(project, validados.map(c => c.id));
                                                                    alert(`✅ ${result.promoted_count} códigos promovidos a la Lista Definitiva.`);
                                                                    await loadCandidates();
                                                                    await loadStats();
                                                                } catch (err) {
                                                                    alert(`Error al promover: ${err instanceof Error ? err.message : String(err)}`);
                                                                }
                                                            } else {
                                                                alert('No hay códigos validados para promover.');
                                                            }
                                                        }
                                                    }}
                                                    style={{
                                                        padding: '0.5rem 1rem',
                                                        background: 'linear-gradient(135deg, #059669, #10b981)',
                                                        color: 'white',
                                                        border: 'none',
                                                        borderRadius: '0.375rem',
                                                        cursor: 'pointer',
                                                        fontWeight: 600,
                                                        fontSize: '0.9rem'
                                                    }}
                                                >
                                                    🔄 Auto-fusionar {similarPairs.length} par(es)
                                                </button>
                                            </div>
                                        </>
                                    )}
                                </div>
                            );
                        })()}

                        <div className="modal-actions">
                            <label>
                                Umbral:
                                <input
                                    type="range"
                                    min="50"
                                    max="95"
                                    value={duplicateThreshold * 100}
                                    onChange={e => setDuplicateThreshold(parseInt(e.target.value) / 100)}
                                />
                                {(duplicateThreshold * 100).toFixed(0)}%
                            </label>
                            <button onClick={handleDetectDuplicates} disabled={loadingDuplicates}>
                                🔄 Re-analizar
                            </button>
                            <button onClick={() => setShowDuplicates(false)}>Cerrar</button>
                        </div>
                    </div>
                </div>
            )}

            {/* Promote Button */}
            {stats && stats.totals.validado > 0 && (
                <div className="validation-panel__promote">
                    <button onClick={handlePromote} className="btn btn--promote">
                        ⬆️ Promover {stats.totals.validado} códigos validados a Lista Definitiva
                    </button>
                </div>
            )}

            {/* Error */}
            {error && <div className="validation-panel__error">{error}</div>}

            {/* Table */}
            <div className="validation-panel__table-container">
                <table className="validation-panel__table">
                    <thead>
                        <tr>
                            <th>
                                <input
                                    type="checkbox"
                                    checked={selected.size === candidates.length && candidates.length > 0}
                                    onChange={toggleSelectAll}
                                />
                            </th>
                            <th>Código</th>
                            <th>Origen</th>
                            <th>Estado</th>
                            <th>Archivo</th>
                            <th>Score</th>
                            <th>Cita</th>
                            <th>Acciones</th>
                        </tr>
                    </thead>
                    <tbody>
                        {loading && (
                            <tr><td colSpan={8}>Cargando...</td></tr>
                        )}
                        {!loading && candidates.length === 0 && (
                            <tr>
                                <td colSpan={8}>
                                    {filterEstado === "pendiente" ? (
                                        <div style={{ display: "flex", gap: "0.75rem", alignItems: "center", flexWrap: "wrap" }}>
                                            <span>No hay candidatos ⏳ pendientes con estos filtros.</span>
                                            <button
                                                type="button"
                                                className="btn btn--validate"
                                                onClick={() => setFilterEstado("validado")}
                                            >
                                                ✅ Ver validados
                                            </button>
                                            <button
                                                type="button"
                                                className="btn"
                                                onClick={() => setFilterEstado("")}
                                            >
                                                👁️ Ver todos
                                            </button>
                                        </div>
                                    ) : (
                                        <span>No hay candidatos con estos filtros.</span>
                                    )}
                                </td>
                            </tr>
                        )}
                        {!loading && candidates.map(c => (
                            <tr key={c.id} className={selected.has(c.id) ? "selected" : ""}>
                                <td>
                                    <input
                                        type="checkbox"
                                        checked={selected.has(c.id)}
                                        onChange={() => toggleSelect(c.id)}
                                    />
                                </td>
                                <td className="td-codigo"><strong>{c.codigo}</strong></td>
                                <td>{FUENTE_LABELS[c.fuente_origen] || c.fuente_origen}</td>
                                <td style={{ color: ESTADO_LABELS[c.estado]?.color }}>
                                    {ESTADO_LABELS[c.estado]?.label || c.estado}
                                </td>
                                <td>{c.archivo?.slice(0, 20) || "-"}</td>
                                <td>{c.score_confianza?.toFixed(3) || "-"}</td>
                                <td className="td-cita" title={c.cita || ""}>
                                    {(c.cita || "").slice(0, 60)}...
                                </td>
                                <td className="td-actions">
                                    <button
                                        onClick={() => handleShowHistory(c.codigo)}
                                        className="btn-sm btn--history"
                                        title="Ver historial del código"
                                    >
                                        🕒
                                    </button>
                                    {c.estado === "pendiente" && (
                                        <>
                                            <button onClick={() => handleShowExamples(c)} className="btn-sm btn--examples" title="Ver ejemplos canónicos">📋</button>
                                            <button onClick={() => handleValidate(c.id)} className="btn-sm btn--validate">✅</button>
                                            <button onClick={() => handleReject(c.id)} className="btn-sm btn--reject">❌</button>
                                        </>
                                    )}
                                    {c.estado === "fusionado" && c.fusionado_a && (
                                        <span title={`Fusionado a: ${c.fusionado_a}`}>→ {c.fusionado_a.slice(0, 12)}</span>
                                    )}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            <CodeHistoryModal
                isOpen={showHistory}
                codigo={historyCodigo}
                loading={historyLoading}
                error={historyError}
                history={historyItems}
                onClose={() => {
                    setShowHistory(false);
                    setHistoryItems([]);
                    setHistoryError(null);
                    setHistoryCodigo("");
                }}
            />

            <style>{`
        .validation-panel {
          background: #fefce8;
          border-radius: 0.75rem;
          padding: 1.25rem;
          margin-bottom: 1rem;
        }
        .validation-panel__header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          margin-bottom: 1rem;
        }
        .validation-panel__header h3 {
          margin: 0 0 0.25rem 0;
          color: #854d0e;
        }
        .validation-panel__header p {
          margin: 0;
          color: #78716c;
          font-size: 0.875rem;
        }
        .validation-panel__stats {
          display: flex;
          gap: 0.75rem;
          margin-bottom: 1rem;
          flex-wrap: wrap;
        }
        .stat {
          padding: 0.5rem 1rem;
          border-radius: 0.5rem;
          display: flex;
          flex-direction: column;
          align-items: center;
          min-width: 80px;
        }
        .stat span { font-size: 0.7rem; text-transform: uppercase; }
        .stat strong { font-size: 1.25rem; }
        .stat--pending { background: #fef3c7; color: #92400e; }
        .stat--validated { background: #d1fae5; color: #065f46; }
        .stat--rejected { background: #fee2e2; color: #991b1b; }
        .stat--merged { background: #e0e7ff; color: #3730a3; }
        .stat--total { background: #f3f4f6; color: #374151; }
        .validation-panel__health-alert {
          display: flex;
          align-items: center;
          gap: 0.75rem;
          padding: 0.75rem 1rem;
          background: linear-gradient(135deg, #fef3c7, #fde68a);
          border: 1px solid #f59e0b;
          border-radius: 0.5rem;
          margin-bottom: 1rem;
          color: #92400e;
          font-size: 0.875rem;
        }
        .validation-panel__health-alert span:first-child {
          font-size: 1.25rem;
        }
        .validation-panel__filters {
          display: flex;
          gap: 1rem;
          margin-bottom: 1rem;
        }
        .validation-panel__filters label {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          font-size: 0.875rem;
        }
        .validation-panel__filters select {
          padding: 0.4rem;
          border-radius: 0.375rem;
          border: 1px solid #d1d5db;
        }
        .validation-panel__batch {
          display: flex;
          gap: 0.5rem;
          align-items: center;
          margin-bottom: 1rem;
          padding: 0.5rem;
          background: #fef9c3;
          border-radius: 0.5rem;
        }
        .validation-panel__batch span {
          font-weight: 600;
          color: #854d0e;
        }
        .validation-panel__promote {
          margin-bottom: 1rem;
        }
        .btn { padding: 0.4rem 0.8rem; border: none; border-radius: 0.375rem; cursor: pointer; font-size: 0.8rem; }
        .btn--validate { background: #10b981; color: white; }
        .btn--reject { background: #ef4444; color: white; }
        .btn--merge { background: #6366f1; color: white; }
        .btn--examples { background: #8b5cf6; color: white; }
        .btn--history { background: #334155; color: white; }
        .btn--promote { background: linear-gradient(135deg, #059669, #10b981); color: white; padding: 0.6rem 1.2rem; font-size: 0.9rem; }
        .btn-sm { padding: 0.25rem 0.5rem; font-size: 0.75rem; border: none; border-radius: 0.25rem; cursor: pointer; margin-right: 0.25rem; }
        .validation-panel__error {
          background: #fee2e2;
          color: #991b1b;
          padding: 0.5rem;
          border-radius: 0.375rem;
          margin-bottom: 1rem;
        }
        .validation-panel__table-container {
          overflow-x: auto;
          max-height: 400px;
          overflow-y: auto;
        }
        .validation-panel__table {
          width: 100%;
          border-collapse: collapse;
          font-size: 0.85rem;
        }
        .validation-panel__table th {
          background: #fef9c3;
          padding: 0.5rem;
          text-align: left;
          border-bottom: 2px solid #fde047;
          position: sticky;
          top: 0;
        }
        .validation-panel__table td {
          padding: 0.5rem;
          border-bottom: 1px solid #fef3c7;
        }
        .validation-panel__table tr:hover {
          background: #fffbeb;
        }
        .validation-panel__table tr.selected {
          background: #fef08a;
        }
        .td-codigo { max-width: 150px; word-break: break-word; }
        .td-cita { max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .td-actions { white-space: nowrap; }
        .validation-panel__modal {
          position: fixed;
          inset: 0;
          background: rgba(0,0,0,0.5);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 1000;
        }
        .modal-content {
          background: white;
          padding: 1.5rem;
          border-radius: 0.75rem;
          max-width: 400px;
          width: 90%;
        }
        .modal-content--wide {
          max-width: 550px;
        }
        .modal-content h4 { margin: 0 0 0.5rem 0; }
        .modal-content h5 { margin: 0.5rem 0; font-size: 0.85rem; color: #6366f1; }
        .modal-content p { margin: 0 0 1rem 0; color: #64748b; font-size: 0.9rem; }
        .modal-content input { width: 100%; padding: 0.5rem; border: 1px solid #d1d5db; border-radius: 0.375rem; margin-bottom: 1rem; }
        .modal-actions { display: flex; gap: 0.5rem; justify-content: flex-end; margin-top: 1rem; }
        
        /* Similar codes chips */
        .similar-codes { background: #f0f9ff; padding: 0.75rem; border-radius: 0.5rem; margin-bottom: 1rem; }
        .similar-codes__list { display: flex; flex-wrap: wrap; gap: 0.5rem; }
        .similar-code-chip {
          background: #dbeafe;
          border: 1px solid #93c5fd;
          padding: 0.25rem 0.75rem;
          border-radius: 1rem;
          font-size: 0.8rem;
          cursor: pointer;
          display: flex;
          align-items: center;
          gap: 0.5rem;
          transition: all 0.15s;
        }
        .similar-code-chip:hover { background: #bfdbfe; border-color: #3b82f6; }
        .similar-code-score { font-size: 0.7rem; color: #1d4ed8; font-weight: 600; }
        
        /* Canonical examples */
        .examples-list { max-height: 250px; overflow-y: auto; }
        .example-item {
          background: #f8fafc;
          border-left: 3px solid #8b5cf6;
          padding: 0.75rem;
          margin-bottom: 0.5rem;
          border-radius: 0 0.375rem 0.375rem 0;
        }
        .example-cita { font-style: italic; font-size: 0.9rem; color: #374151; margin-bottom: 0.25rem; }
        .example-meta { font-size: 0.75rem; color: #6b7280; }
        .loading-text { color: #6b7280; font-style: italic; text-align: center; }
        .no-examples { color: #9ca3af; font-style: italic; text-align: center; background: #f3f4f6; padding: 1rem; border-radius: 0.375rem; }
      `}</style>
        </div>
    );
}

export default CodeValidationPanel;
