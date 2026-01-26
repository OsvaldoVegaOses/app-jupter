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

import React, { useState, useCallback, useEffect, useRef } from "react";
import {
    listCandidates,
    validateCandidate,
    rejectCandidate,
    mergeCandidates,
    autoMergeCandidates,
    aiPlanMerges,
    promoteCandidates,
    getCodeHistory,
    getCandidateStatsBySource,
    getBacklogHealth,
    getCanonicalExamples,
    getSimilarCodes,
    detectDuplicates,
    checkBatchCodes,
    revertValidatedCandidates,
    logDiscoveryNavigation,
    CandidateCode,
    CandidateStats,
    BacklogHealth,
    CanonicalExample,
    SimilarCode,
    DuplicatePair,
    BatchCheckResult,
    CheckBatchCodesResponse,
    AiPlanMergePair,
    CodeHistoryEntry,
    syncNeo4j,
    SyncNeo4jResponse,
} from "../services/api";

import { CodeHistoryModal } from "./CodeHistoryModal";

// Global guard to prevent duplicate auto-merge submissions (across mounts)
let autoMergeInFlight = false;

interface CodeValidationPanelProps {
    project: string;
}

type FilterEstado = "" | "pendiente" | "hipotesis" | "validado" | "rechazado" | "fusionado";
type FilterFuente = "" | "llm" | "manual" | "discovery" | "semantic_suggestion" | "link_prediction";
type FilterPromovido = "" | "no" | "si";

const FUENTE_LABELS: Record<string, string> = {
    llm: "🤖 LLM",
    manual: "📝 Manual",
    discovery: "🔍 Discovery",
    semantic_suggestion: "💡 Sugerencias",
    link_prediction: "🔮 Link Prediction",
    legacy: "📦 Legacy",
};

const ESTADO_LABELS: Record<string, { label: string; color: string }> = {
    pendiente: { label: "⏳ Pendiente", color: "#f59e0b" },
    hipotesis: { label: "🔬 Hipótesis", color: "#8b5cf6" },
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
    const [filterPromovido, setFilterPromovido] = useState<FilterPromovido>("");
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

    // Pre-hoc duplicate detection (batch check)
    const [showPrehoc, setShowPrehoc] = useState(false);
    const [prehocLoading, setPrehocLoading] = useState(false);
    const [prehocThreshold, setPrehocThreshold] = useState(0.85);
    const [prehocResponse, setPrehocResponse] = useState<CheckBatchCodesResponse | null>(null);
    const [prehocShowAll, setPrehocShowAll] = useState(false);
    const [prehocSelectMode, setPrehocSelectMode] = useState<"all" | "manual">("all");
    const [prehocSelectedKeys, setPrehocSelectedKeys] = useState<Set<string>>(new Set());
    const [prehocMergeTarget, setPrehocMergeTarget] = useState<string>("");
    const [prehocMerging, setPrehocMerging] = useState(false);

    // AI Runner (high-confidence auto-merge)
    const [runnerLoading, setRunnerLoading] = useState(false);
    const [runnerMinSimilarity, setRunnerMinSimilarity] = useState(0.92);
    const [runnerLastReport, setRunnerLastReport] = useState<string>("");

    // AI Runner Plan (auditables por run_id) — validación humana uno a uno
    const [showAiPlan, setShowAiPlan] = useState(false);
    const [aiPlanRunId, setAiPlanRunId] = useState<string>("");
    const [aiPlanPairs, setAiPlanPairs] = useState<AiPlanMergePair[]>([]);
    const [aiPlanThreshold, setAiPlanThreshold] = useState<number>(0.0);
    const [aiPlanApplyingKey, setAiPlanApplyingKey] = useState<string>("");

    // Duplicate selection (merge all vs one-by-one)
    const [duplicateSelectMode, setDuplicateSelectMode] = useState<"all" | "manual">("all");
    const [selectedDuplicateKeys, setSelectedDuplicateKeys] = useState<Set<string>>(new Set());

    // Auto-merge loading state
    const [autoMerging, setAutoMerging] = useState(false);
    const autoMergingRef = useRef(false); // Ref to prevent stale closure issues
    const [mergeProgress, setMergeProgress] = useState<string>("");

    const [revertingValidated, setRevertingValidated] = useState(false);

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
                promovido:
                    filterEstado === "validado"
                        ? (filterPromovido === "si" ? true : filterPromovido === "no" ? false : undefined)
                        : undefined,
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
    }, [project, filterEstado, filterFuente, filterPromovido, sortOrder]);

    const handleRevertValidatedToPending = async () => {
        if (!project) {
            alert("Selecciona un proyecto primero.");
            return;
        }

        if (revertingValidated) return;

        const ok = confirm(
            "¿Revertir TODOS los candidatos 'validado' a 'pendiente' para este proyecto?\n\n" +
            "Esto solo cambia la bandeja de candidatos (no elimina códigos definitivos ya promovidos)."
        );
        if (!ok) return;

        const memo = prompt("Memo opcional para registrar el motivo del revert:");

        setRevertingValidated(true);
        try {
            const result = await revertValidatedCandidates(project, { memo: memo || undefined });
            const reverted = result.reverted_count ?? 0;
            alert(`✅ Revertidos: ${reverted} candidato(s) a 'pendiente'.`);

            // Si el usuario estaba viendo 'validado', cambiar a 'pendiente' para evitar pantalla vacía.
            if (filterEstado === "validado") {
                setFilterEstado("pendiente");
            }

            await loadCandidates();
            await loadStats();
            await loadHealth();
        } catch (err) {
            alert("Error: " + (err instanceof Error ? err.message : String(err)));
        } finally {
            setRevertingValidated(false);
        }
    };

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
    }, [project, filterEstado, filterFuente, filterPromovido, sortOrder]);

    // Si el usuario deja de ver "validado", limpiar subfiltro de promoción para evitar confusión.
    useEffect(() => {
        if (filterEstado !== "validado" && filterPromovido !== "") {
            setFilterPromovido("");
        }
    }, [filterEstado, filterPromovido]);

    const handleValidate = async (id: number) => {
        try {
            await validateCandidate(id, project);
            // E3-1.2: Log validation action
            try {
                const candidate = candidates.find(c => c.id === id);
                await logDiscoveryNavigation({
                    project,
                    positivos: candidate ? [candidate.codigo] : [],
                    negativos: [],
                    target_text: candidate?.cita || null,
                    fragments_count: 1,
                    codigos_sugeridos: [],
                    action_taken: "e3_validate",
                });
            } catch { /* non-blocking */ }
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
            // E3-1.2: Log rejection action
            try {
                const candidate = candidates.find(c => c.id === id);
                await logDiscoveryNavigation({
                    project,
                    positivos: [],
                    negativos: candidate ? [candidate.codigo] : [],
                    target_text: candidate?.cita || null,
                    fragments_count: 1,
                    codigos_sugeridos: [],
                    action_taken: "e3_reject",
                });
            } catch { /* non-blocking */ }
            await loadCandidates();
            await loadStats();
        } catch (err) {
            alert("Error: " + (err instanceof Error ? err.message : String(err)));
        }
    };

    const handleBatchValidate = async () => {
        if (selected.size === 0) return;
        // E3-4.1: Confirmación antes de batch validate
        if (!confirm(`¿Validar ${selected.size} candidato(s) seleccionado(s)?\n\nEsta acción marca los candidatos como listos para promoción.`)) {
            return;
        }
        let successCount = 0;
        const validatedCodes: string[] = [];
        for (const id of selected) {
            try {
                await validateCandidate(id, project);
                const candidate = candidates.find(c => c.id === id);
                if (candidate) validatedCodes.push(candidate.codigo);
                successCount++;
            } catch (err) {
                console.error(`Error validating ${id}:`, err);
            }
        }
        // E3-1.2: Log batch validation
        try {
            await logDiscoveryNavigation({
                project,
                positivos: validatedCodes,
                negativos: [],
                target_text: null,
                fragments_count: successCount,
                codigos_sugeridos: [],
                action_taken: "e3_validate",
            });
        } catch { /* non-blocking */ }
        await loadCandidates();
        await loadStats();
    };

    const handleBatchReject = async () => {
        if (selected.size === 0) return;
        // E3-4.1: Confirmación antes de batch reject
        if (!confirm(`¿Rechazar ${selected.size} candidato(s) seleccionado(s)?\n\nEsta acción es reversible desde el historial.`)) {
            return;
        }
        const memo = prompt("Razón del rechazo (opcional):");
        let successCount = 0;
        const rejectedCodes: string[] = [];
        for (const id of selected) {
            try {
                await rejectCandidate(id, project, memo || undefined);
                const candidate = candidates.find(c => c.id === id);
                if (candidate) rejectedCodes.push(candidate.codigo);
                successCount++;
            } catch (err) {
                console.error(`Error rejecting ${id}:`, err);
            }
        }
        // E3-1.2: Log batch rejection
        try {
            await logDiscoveryNavigation({
                project,
                positivos: [],
                negativos: rejectedCodes,
                target_text: null,
                fragments_count: successCount,
                codigos_sugeridos: [],
                action_taken: "e3_reject",
            });
        } catch { /* non-blocking */ }
        await loadCandidates();
        await loadStats();
    };

    const handleMerge = async () => {
        if (selected.size < 2 || !mergeTarget.trim()) {
            alert("Selecciona al menos 2 candidatos y un código destino.");
            return;
        }
        const memo = prompt(
            "Justificación de la fusión (requerida).\n\n" +
            "Esta acción es gobernanza del codebook: no borra evidencia, consolida variantes hacia un código canónico."
        );
        if (memo === null || !memo.trim()) {
            alert("Se requiere una justificación (memo) para ejecutar la fusión.");
            return;
        }
        try {
            await mergeCandidates(project, Array.from(selected), mergeTarget.trim(), { memo: memo.trim() });
            setShowMerge(false);
            setMergeTarget("");
            await loadCandidates();
            await loadStats();
        } catch (err) {
            alert("Error: " + (err instanceof Error ? err.message : String(err)));
        }
    };

    const handlePromote = async () => {
        if (!stats) {
            alert("Cargando estadísticas... intenta de nuevo en un momento.");
            return;
        }
        const totalPorPromover =
            typeof stats.validated_unpromoted_total === "number"
                ? stats.validated_unpromoted_total
                : (stats.totals?.validado ?? 0);
        if (totalPorPromover <= 0) {
            alert("No hay códigos validados pendientes por promover.");
            return;
        }

        const notaEvidencia =
            "\n\nNota: solo se promueven candidatos validados con evidencia (fragmento_id válido).";
        if (!confirm(`¿Promover ${totalPorPromover} candidato(s) validados a la Lista Definitiva?${notaEvidencia}`)) return;
        try {
            const result = await promoteCandidates(project, { promoteAllValidated: true });

            const promoted = result.promoted_count ?? 0;
            const eligible = (result.eligible_total ?? null);
            const skipped = (result.skipped_total ?? null);

            // E3-1.2: Log promotion action
            try {
                await logDiscoveryNavigation({
                    project,
                    positivos: [],
                    negativos: [],
                    target_text: null,
                    fragments_count: promoted,
                    codigos_sugeridos: [],
                    ai_synthesis: `promoted=${promoted}, skipped=${skipped ?? 0}`,
                    action_taken: "e3_promote",
                });
            } catch { /* non-blocking */ }

            const details: string[] = [];
            if (typeof eligible === "number") details.push(`elegibles: ${eligible}`);
            if (typeof skipped === "number" && skipped > 0) details.push(`omitidos (sin evidencia): ${skipped}`);
            
            // Neo4j sync metrics
            const neo4jMerged = result.neo4j_merged ?? 0;
            const neo4jMissing = result.neo4j_missing_fragments ?? 0;
            const neo4jInfo = neo4jMerged > 0 
                ? `\n🔗 Neo4j: ${neo4jMerged} relación(es) sincronizada(s)${neo4jMissing > 0 ? `, ${neo4jMissing} fragmento(s) pendiente(s)` : ''}`
                : '';

            alert(
                `✅ ${promoted} fila(s) promovida(s) a la lista definitiva.` +
                (details.length ? `\n(${details.join(" · ")})` : "") +
                neo4jInfo
            );
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
            console.info("🔎 Detectando duplicados", {
                project,
                threshold: duplicateThreshold,
            });
            const result = await detectDuplicates(project, duplicateThreshold);
            console.info("📌 Duplicados detectados", {
                project,
                count: result.count ?? result.duplicates?.length ?? 0,
                method: (result as any).method,
            });
            setDuplicates(result.duplicates);
        } catch (err) {
            console.error("Error detecting duplicates:", err);
            alert("Error al detectar duplicados: " + (err instanceof Error ? err.message : String(err)));
        } finally {
            setLoadingDuplicates(false);
        }
    };

    // Detect duplicates Pre-hoc (batch check)
    const handleDetectDuplicatesPrehoc = async () => {
        if (!project) {
            alert("Selecciona un proyecto primero.");
            return;
        }
        if (prehocLoading) return;

        if (selected.size === 0) {
            alert("Selecciona al menos 1 candidato para analizar con Prehoc.");
            return;
        }

        const selectedCandidates = Array.from(selected)
            .map(id => candidates.find(c => c.id === id))
            .filter(Boolean) as CandidateCode[];

        const rawCodes = selectedCandidates
            .map(c => (c.codigo || "").trim())
            .filter(Boolean);

        const uniqueCodes = Array.from(new Set(rawCodes.map(c => c.toLowerCase())))
            .map(lower => rawCodes.find(c => c.toLowerCase() === lower) as string)
            .filter(Boolean);

        if (uniqueCodes.length === 0) {
            alert("No hay códigos válidos en la selección actual.");
            return;
        }

        setShowPrehoc(true);
        setPrehocLoading(true);
        setPrehocResponse(null);

        try {
            const result = await checkBatchCodes(project, uniqueCodes, prehocThreshold);
            setPrehocResponse(result);
            // Default selection behavior: in "all" mode select all items; in manual keep only valid keys.
            const keys = new Set((result.results || []).map(r => (r.codigo || "").trim()).filter(Boolean));
            if (prehocSelectMode === "all") {
                setPrehocSelectedKeys(keys);
            } else {
                setPrehocSelectedKeys(prev => {
                    const next = new Set<string>();
                    for (const k of prev) {
                        if (keys.has(k)) next.add(k);
                    }
                    return next;
                });
            }
        } catch (err) {
            alert("Error al detectar duplicados (Prehoc): " + (err instanceof Error ? err.message : String(err)));
        } finally {
            setPrehocLoading(false);
        }
    };

    // Runner IA (modo seguro): genera un plan de propuestas auditables (run_id).
    // No ejecuta merges en bloque; el investigador aplica uno a uno.
    const handleRunnerHighConfidenceAutoMerge = async () => {
        if (!project) {
            alert("Selecciona un proyecto primero.");
            return;
        }
        if (runnerLoading) return;

        // Determinar alcance: seleccionados o todos los candidatos cargados.
        let scopeCandidates: CandidateCode[] = [];
        if (selected.size > 0) {
            scopeCandidates = Array.from(selected)
                .map(id => candidates.find(c => c.id === id))
                .filter(Boolean) as CandidateCode[];
        } else {
            const ok = confirm(
                "No hay candidatos seleccionados.\n\n" +
                `¿Ejecutar Runner IA sobre TODOS los candidatos cargados (${candidates.length})?\n` +
                "Tip: selecciona algunos (checkbox) para un primer ensayo controlado."
            );
            if (!ok) return;
            scopeCandidates = candidates.slice();
        }

        const rawCodes = scopeCandidates
            .map(c => (c.codigo || "").trim())
            .filter(Boolean);

        const uniqueCodes = Array.from(new Set(rawCodes.map(c => c.toLowerCase())))
            .map(lower => rawCodes.find(c => c.toLowerCase() === lower) as string)
            .filter(Boolean);

        if (uniqueCodes.length === 0) {
            alert("No hay códigos válidos para analizar.");
            return;
        }

        // Seguridad: siempre confirmar umbral y volumen.
        const threshold = Math.max(0.5, Math.min(0.99, runnerMinSimilarity));
        const ok1 = confirm(
            "🤖 Runner IA (solo propuestas, con auditoría)\n\n" +
            `Códigos a analizar: ${uniqueCodes.length}\n` +
            `Confianza mínima (similitud): ${(threshold * 100).toFixed(0)}%\n\n` +
            "Generará un plan (run_id) con pares sugeridos.\n" +
            "Luego podrás aplicar cada fusión de forma manual (uno a uno)."
        );
        if (!ok1) return;

        setRunnerLoading(true);
        setRunnerLastReport("");
        try {
            const plan = await aiPlanMerges(project, uniqueCodes, threshold, 200, "ui");

            const finalPairs = (plan.pairs || []).slice();
            if (finalPairs.length === 0) {
                const report =
                    "Runner IA no encontró pares con alta confianza.\n\n" +
                    `Analizados: ${uniqueCodes.length}\n` +
                    `Umbral: ${(threshold * 100).toFixed(0)}%\n` +
                    "Sugerencia: baja el umbral (p.ej. 90%) o usa el modal Prehoc para revisar manualmente.";
                setRunnerLastReport(report);
                alert(report);
                return;
            }

            setAiPlanRunId(plan.run_id);
            setAiPlanPairs(finalPairs);
            setAiPlanThreshold(plan.threshold);
            setShowAiPlan(true);

            const preview = finalPairs
                .slice(0, 8)
                .map(p => `• ${p.source_codigo} → ${p.target_codigo} (${Math.round((p.similarity ?? 0) * 100)}%)`)
                .join("\n");

            const report =
                "✅ Plan IA generado (sin ejecutar merges).\n\n" +
                `• run_id: ${plan.run_id}\n` +
                `• Analizados: ${uniqueCodes.length}\n` +
                `• Pares propuestos: ${finalPairs.length}\n` +
                `• Umbral: ${(plan.threshold * 100).toFixed(0)}%\n\n` +
                (finalPairs.length <= 8 ? preview : (preview + "\n…"));
            setRunnerLastReport(report);
        } catch (err) {
            alert("Error en Runner IA: " + (err instanceof Error ? err.message : String(err)));
        } finally {
            setRunnerLoading(false);
        }
    };

    const handleApplyAiPlanPair = async (pair: AiPlanMergePair) => {
        if (!project) return;
        const source = (pair.source_codigo || "").trim();
        const target = (pair.target_codigo || "").trim();
        const key = `${source}→${target}`;
        if (!source || !target) return;
        if (aiPlanApplyingKey) return;

        const ok = confirm(
            "Aplicar fusión (uno a uno)\n\n" +
            `run_id: ${aiPlanRunId || "(sin run_id)"}\n` +
            `• ${source} → ${target}\n` +
            `• similitud: ${Math.round((pair.similarity ?? 0) * 100)}%\n\n` +
            "¿Confirmas ejecutar este merge ahora?"
        );
        if (!ok) return;

        setAiPlanApplyingKey(key);
        try {
            const result = await autoMergeCandidates(
                project,
                [{ source_codigo: source, target_codigo: target }],
                {
                    memo: `ai_plan_merge run_id=${aiPlanRunId || ""} similarity=${String(pair.similarity ?? "")} source=${source} target=${target}`,
                }
            );
            if (result.total_merged > 0) {
                setAiPlanPairs(prev => prev.filter(p => {
                    const s = (p.source_codigo || "").trim();
                    const t = (p.target_codigo || "").trim();
                    return `${s}→${t}` !== key;
                }));
            }
            await loadCandidates();
            await loadStats();
            await loadHealth();
        } catch (err) {
            alert("Error aplicando merge: " + (err instanceof Error ? err.message : String(err)));
        } finally {
            setAiPlanApplyingKey("");
        }
    };

    const handlePrehocMergeSelected = async (items: BatchCheckResult[]) => {
        if (!project) {
            alert("Selecciona un proyecto primero.");
            return;
        }
        if (prehocMerging) return;

        const cleanTarget = (prehocMergeTarget || "").trim();
        const selectedItems = items.filter(r => prehocSelectedKeys.has((r.codigo || "").trim()));

        if (selectedItems.length === 0) {
            alert("No hay elementos seleccionados para fusionar.");
            return;
        }

        // If user didn't provide a target, use best suggested existing code per item.
        // IMPORTANT: "Seleccionados" != "pares válidos" (se omiten items sin destino sugerido o self-merge).
        const pairs: Array<{ source_codigo: string; target_codigo: string }> = [];
        let skippedNoTarget = 0;
        let skippedSelfMerge = 0;

        for (const r of selectedItems) {
            const source = (r.codigo || "").trim();
            if (!source) continue;
            const suggested = (r.similar || [])
                .slice()
                .sort((a, b) => (b.similarity ?? 0) - (a.similarity ?? 0))[0]?.existing;
            const target = cleanTarget || (suggested ? String(suggested).trim() : "");

            if (!target) {
                skippedNoTarget += 1;
                continue;
            }
            if (source.toLowerCase() === target.toLowerCase()) {
                skippedSelfMerge += 1;
                continue;
            }
            pairs.push({ source_codigo: source, target_codigo: target });
        }

        if (pairs.length === 0) {
            const hint = cleanTarget
                ? "Tip: cambia el 'Código destino' si coincide con los sources."
                : "Tip: escribe un 'Código destino' para forzar el merge incluso si no hay sugerencias.";
            alert(
                "No hay pares válidos para fusionar.\n\n" +
                `Seleccionados: ${selectedItems.length}\n` +
                `Omitidos sin destino: ${skippedNoTarget}\n` +
                `Omitidos por self-merge: ${skippedSelfMerge}\n\n` +
                hint
            );
            return;
        }

        const ok = confirm(
            `¿Fusionar ahora?\n\n` +
            `Seleccionados: ${selectedItems.length}\n` +
            `Pares válidos a enviar: ${pairs.length}\n` +
            (skippedNoTarget > 0 ? `Omitidos sin destino: ${skippedNoTarget}\n` : "") +
            (skippedSelfMerge > 0 ? `Omitidos por self-merge: ${skippedSelfMerge}\n` : "") +
            "\n" +
            (cleanTarget
                ? `Destino único: '${cleanTarget}'\n`
                : "Destino: sugerido por similitud para cada código (si existe)\n") +
            (skippedNoTarget > 0 && !cleanTarget
                ? "\nNota: Para incluir los omitidos, escribe un 'Código destino' único."
                : "")
        );
        if (!ok) return;

        setPrehocMerging(true);
        try {
            const result = await autoMergeCandidates(project, pairs, {
                memo: `prehoc_merge_ui threshold=${prehocThreshold} selected=${selectedItems.length} pairs=${pairs.length}`,
            });
            alert(
                `✅ Prehoc merge completado.\n\n` +
                `• Pares procesados: ${result.pairs_processed}\n` +
                `• Candidatos fusionados: ${result.total_merged}`
            );
            await loadCandidates();
            await loadStats();
            await loadHealth();
        } catch (err) {
            alert("Error al fusionar (Prehoc): " + (err instanceof Error ? err.message : String(err)));
        } finally {
            setPrehocMerging(false);
        }
    };

    // Optimized auto-merge using backend endpoint (more robust than client-side ID matching)
    const handleAutoMerge = async (similarPairs: any[], options?: { closeModal?: boolean }) => {
        const closeModal = options?.closeModal !== false;
        // Prevent multiple clicks using ref (avoids stale closure issues)
        // Set ref BEFORE confirm to block any clicks during the dialog
        if (autoMergingRef.current || autoMergeInFlight) {
            console.log("⚠️ Auto-merge already in progress, ignoring click");
            return;
        }
        
        // Lock immediately BEFORE showing confirm dialog
        autoMergingRef.current = true;
        autoMergeInFlight = true;
        
        console.info("🔧 Auto-merge solicitado", {
            project,
            pairCount: similarPairs.length,
        });

        if (!confirm(`¿Fusionar automáticamente ${similarPairs.length} par(es) de códigos similares?\n\nAcciones:\n1. Fusionar códigos similares al más corto\n2. Opción de promover a lista definitiva`)) {
            // User cancelled - unlock
            autoMergingRef.current = false;
            autoMergeInFlight = false;
            return;
        }

        // User confirmed - update UI state
        setAutoMerging(true);
        setMergeProgress("🔄 Iniciando proceso de auto-fusión...");

        try {
            // Build pairs for the backend - the shorter code becomes the target
            const mergePairs = similarPairs.map(pair => {
                const target = pair.code1.length <= pair.code2.length ? pair.code1 : pair.code2;
                const source = pair.code1.length <= pair.code2.length ? pair.code2 : pair.code1;
                return {
                    source_codigo: source,
                    target_codigo: target,
                };
            });

            const selfPairs = mergePairs.filter(p =>
                p.source_codigo?.trim().toLowerCase() === p.target_codigo?.trim().toLowerCase()
            );
            if (selfPairs.length > 0) {
                console.warn("⚠️ Pares con source == target (no-op esperado)", {
                    count: selfPairs.length,
                    examples: selfPairs.slice(0, 5),
                });
            }

            const filteredPairs = mergePairs.filter(p =>
                p.source_codigo?.trim().toLowerCase() !== p.target_codigo?.trim().toLowerCase()
            );

            if (filteredPairs.length === 0) {
                console.warn("⚠️ Auto-merge cancelado: todos los pares son self-merge");
                setMergeProgress("⚠️ Sin pares válidos para fusionar (self-merge)." );
                return;
            }

            console.log("🔄 Enviando pares al backend para auto-merge:", filteredPairs);
            setMergeProgress(`🔗 Fusionando ${filteredPairs.length} pares...`);

            // Call the new backend endpoint that handles everything
            const result = await autoMergeCandidates(project, filteredPairs, {
                memo: `posthoc_auto_merge_ui threshold=${duplicateThreshold} pairs=${filteredPairs.length} strategy=prefer_shorter`,
            });

            console.log("✅ Resultado del auto-merge:", result);
            if (!result?.success || result?.total_merged === 0) {
                console.warn("⚠️ Auto-merge sin cambios aplicados", {
                    success: result?.success,
                    total_merged: result?.total_merged,
                    pairs_processed: result?.pairs_processed,
                });
            }

            // Reload data
            setMergeProgress("🔄 Actualizando datos...");
            await loadCandidates();
            await loadStats();

            // Collect target codes for promotion
            const targetCodes = new Set(filteredPairs.map(p => p.target_codigo.trim().toLowerCase()));

            // Show results and ask about promotion
            const successDetails = result.details.filter(d => d.merged_count > 0);
            const shouldPromote = confirm(
                `✅ Auto-fusión completada:\n\n` +
                `• ${result.total_merged} candidatos fusionados\n` +
                `• ${successDetails.length} de ${result.pairs_processed} pares procesados exitosamente\n` +
                `\n¿Deseas promover los códigos destino validados a la Lista Definitiva ahora?`
            );

            if (shouldPromote) {
                setMergeProgress("⬆️ Promoviendo a lista definitiva...");
                // Get validated candidates that match target codes
                const validados = (await listCandidates(project, { estado: 'validado', limit: 500 })).candidates;
                const toPromote = validados.filter(c => 
                    targetCodes.has(c.codigo.trim().toLowerCase())
                );
                
                if (toPromote.length > 0) {
                    try {
                        const promoteResult = await promoteCandidates(project, { candidateIds: toPromote.map(c => c.id) });
                        const neo4jInfo = (promoteResult.neo4j_merged ?? 0) > 0
                            ? `\n🔗 Neo4j: ${promoteResult.neo4j_merged} relación(es) sincronizada(s)`
                            : '';
                        alert(`✅ ${promoteResult.promoted_count} códigos promovidos a la Lista Definitiva.${neo4jInfo}`);
                        await loadCandidates();
                        await loadStats();
                    } catch (err) {
                        alert(`Error al promover: ${err instanceof Error ? err.message : String(err)}`);
                    }
                } else {
                    alert(`No hay códigos validados entre los ${targetCodes.size} códigos destino para promover.\n\nNota: Los códigos destino deben estar validados antes de poder promoverlos.`);
                }
            }

        } catch (err) {
            console.error("❌ Error en auto-fusión:", err);
            alert("Error en auto-fusión: " + (err instanceof Error ? err.message : String(err)));
        } finally {
            // Reset both ref and state
            autoMergingRef.current = false;
            autoMergeInFlight = false;
            setAutoMerging(false);
            setMergeProgress("");
            if (closeModal) {
                setShowDuplicates(false);
                setDuplicates([]);
                setSelectedDuplicateKeys(new Set());
                setDuplicateSelectMode("all");
            } else {
                // Keep modal open and refresh duplicates list
                try {
                    setLoadingDuplicates(true);
                    const refreshed = await detectDuplicates(project, duplicateThreshold);
                    setDuplicates(refreshed.duplicates);
                    // Keep selection consistent
                    setSelectedDuplicateKeys(prev => {
                        const next = new Set<string>();
                        const keys = new Set(
                            (refreshed.duplicates || [])
                                .filter(p => p.code1 !== p.code2)
                                .map(p => `${p.code1}|||${p.code2}`)
                        );
                        for (const k of prev) {
                            if (keys.has(k)) next.add(k);
                        }
                        return next;
                    });
                } catch (e) {
                    console.warn("No se pudo refrescar duplicados tras auto-merge", e);
                } finally {
                    setLoadingDuplicates(false);
                }
            }
        }
    };

    // Keep selection in sync when switching modes or when duplicates list changes
    useEffect(() => {
        if (!showDuplicates) return;
        const similarPairs = (duplicates || []).filter(p => p.code1 !== p.code2);
        const allKeys = new Set(similarPairs.map(p => `${p.code1}|||${p.code2}`));
        if (duplicateSelectMode === "all") {
            setSelectedDuplicateKeys(allKeys);
        } else {
            setSelectedDuplicateKeys(prev => {
                const next = new Set<string>();
                for (const k of prev) {
                    if (allKeys.has(k)) next.add(k);
                }
                return next;
            });
        }
    }, [duplicateSelectMode, duplicates, showDuplicates]);

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
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <button
                        onClick={handleRevertValidatedToPending}
                        disabled={loading || revertingValidated || !project}
                        title="Revierte todos los 'validado' a 'pendiente'"
                        style={{
                            background: revertingValidated ? "#9ca3af" : "#ef4444",
                            color: "white",
                            border: "none",
                            padding: "8px 12px",
                            borderRadius: 8,
                            cursor: (loading || revertingValidated || !project) ? "not-allowed" : "pointer",
                        }}
                    >
                        {revertingValidated ? "⏳ Revirtiendo..." : "↩️ Revertir validados"}
                    </button>
                    <button onClick={loadCandidates} disabled={loading}>
                        {loading ? "Cargando..." : "🔄 Refrescar"}
                    </button>
                </div>
            </header>

            {/* Stats Summary */}
            {stats && (
                <div className="validation-panel__stats">
                    <div className="stat stat--pending">
                        <span>Pendientes</span>
                        <strong>{stats.totals.pendiente || 0}</strong>
                        {typeof stats.unique_totals?.pendiente === "number" && (
                            <small style={{ opacity: 0.8 }}>
                                {stats.unique_totals.pendiente} códigos únicos
                            </small>
                        )}
                    </div>
                    <div className="stat stat--pending">
                        <span>Hipótesis</span>
                        <strong>{stats.totals.hipotesis || 0}</strong>
                        {typeof stats.unique_totals?.hipotesis === "number" && (
                            <small style={{ opacity: 0.8 }}>
                                {stats.unique_totals.hipotesis} códigos únicos
                            </small>
                        )}
                    </div>
                    <div className="stat stat--validated">
                        <span>Validados</span>
                        <strong>{stats.totals.validado || 0}</strong>
                        {typeof stats.unique_totals?.validado === "number" && (
                            <small style={{ opacity: 0.8 }}>
                                {stats.unique_totals.validado} códigos únicos
                            </small>
                        )}
                        {typeof stats.validated_unpromoted_total === "number" && (
                            <small style={{ opacity: 0.8 }}>
                                Por promover: {stats.validated_unpromoted_total}
                                {typeof stats.validated_unpromoted_unique === "number" ? ` (${stats.validated_unpromoted_unique} únicos)` : ""}
                            </small>
                        )}
                    </div>
                    <div className="stat stat--rejected">
                        <span>Rechazados</span>
                        <strong>{stats.totals.rechazado || 0}</strong>
                        {typeof stats.unique_totals?.rechazado === "number" && (
                            <small style={{ opacity: 0.8 }}>
                                {stats.unique_totals.rechazado} códigos únicos
                            </small>
                        )}
                    </div>
                    <div className="stat stat--merged">
                        <span>Fusionados</span>
                        <strong>{stats.totals.fusionado || 0}</strong>
                        {typeof stats.unique_totals?.fusionado === "number" && (
                            <small style={{ opacity: 0.8 }}>
                                {stats.unique_totals.fusionado} códigos únicos
                            </small>
                        )}
                    </div>
                    <div className="stat stat--total">
                        <span>Total</span>
                        <strong>{stats.total_candidatos}</strong>
                        {typeof stats.unique_total_codigos === "number" && (
                            <small style={{ opacity: 0.8 }}>
                                {stats.unique_total_codigos} códigos únicos
                            </small>
                        )}
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
                        <option value="hipotesis">🔬 Hipótesis</option>
                        <option value="validado">✅ Validado</option>
                        <option value="rechazado">❌ Rechazado</option>
                        <option value="fusionado">🔗 Fusionado</option>
                    </select>
                </label>
                <label style={{ opacity: filterEstado === "validado" ? 1 : 0.55 }}>
                    Promoción:
                    <select
                        value={filterPromovido}
                        onChange={e => setFilterPromovido(e.target.value as FilterPromovido)}
                        disabled={filterEstado !== "validado"}
                        title={filterEstado !== "validado" ? "Disponible solo cuando Estado=Validado" : "Filtra validados por estado de promoción"}
                    >
                        <option value="">Todos</option>
                        <option value="no">🟡 Por promover</option>
                        <option value="si">⬆️ Ya promovidos</option>
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
                        <option value="link_prediction">🔮 Link Prediction</option>
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

                <button
                    onClick={handleDetectDuplicatesPrehoc}
                    className="btn btn--duplicates"
                    disabled={prehocLoading || selected.size === 0}
                    title={
                        selected.size === 0
                            ? "Selecciona candidatos (checkbox) para habilitar Prehoc"
                            : "Prehoc: compara contra códigos existentes y detecta duplicados dentro del batch (solo seleccionados)"
                    }
                >
                    {prehocLoading ? "🔄 Prehoc..." : "🔍 Detectar Duplicados Prehoc"}
                </button>

                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <button
                        onClick={handleRunnerHighConfidenceAutoMerge}
                        className="btn"
                        disabled={runnerLoading || candidates.length === 0}
                        title="Runner IA: genera propuestas auditables (run_id). No ejecuta merges; se aplican uno a uno."
                        style={{
                            background: runnerLoading ? "#9ca3af" : "linear-gradient(135deg, #111827, #334155)",
                            color: "white",
                            fontWeight: 700,
                        }}
                    >
                        {runnerLoading
                            ? "🤖 Runner IA..."
                            : `🤖 Runner IA (≥${Math.round(runnerMinSimilarity * 100)}%)`}
                    </button>
                    <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: "0.8rem", color: "#374151" }}>
                        Confianza:
                        <input
                            type="range"
                            min="85"
                            max="98"
                            value={Math.round(runnerMinSimilarity * 100)}
                            onChange={e => setRunnerMinSimilarity(parseInt(e.target.value) / 100)}
                            title="Umbral de similitud para proponer pares"
                        />
                        {Math.round(runnerMinSimilarity * 100)}%
                    </label>
                </div>
            </div>

            {/* Promote Button - Visible */}
            {stats && ((stats.validated_unpromoted_total ?? 0) > 0) && (
                <button
                    onClick={handlePromote}
                    disabled={loading}
                    style={{
                        background: loading ? "#9ca3af" : "linear-gradient(135deg, #059669, #10b981)",
                        color: "white",
                        border: "none",
                        padding: "10px 20px",
                        borderRadius: "8px",
                        cursor: loading ? "not-allowed" : "pointer",
                        fontWeight: 600,
                        fontSize: "0.95rem",
                        marginBottom: "1rem",
                        display: "flex",
                        alignItems: "center",
                        gap: "8px",
                    }}
                    title="Promueve todos los códigos validados (no promovidos aún) a la lista definitiva y sincroniza con Neo4j"
                >
                    ⬆️ Promover {stats.validated_unpromoted_total} códigos validados a Lista Definitiva
                </button>
            )}

            {/* Botón Sync Neo4j */}
            <button
                onClick={async () => {
                    if (!project) return;
                    const confirmSync = confirm('🔄 ¿Sincronizar códigos abiertos con Neo4j?\n\nEsta operación creará nodos :Codigo y relaciones :TIENE_CODIGO en el grafo.');
                    if (!confirmSync) return;
                    try {
                        const result = await syncNeo4j(project);
                        if (result.success) {
                            alert(`✅ Sincronización completada:\n\n📊 Códigos en PostgreSQL: ${result.pg_codes_total}\n🔵 Códigos previos en Neo4j: ${result.neo4j_codes_before}\n➕ Códigos sincronizados: ${result.synced_codes}\n🔗 Relaciones creadas: ${result.synced_relations}\n⚠️ Fragmentos faltantes: ${result.missing_fragments}`);
                        } else {
                            alert(`❌ Error: ${result.error || 'Error desconocido'}`);
                        }
                    } catch (err) {
                        alert(`❌ Error de sincronización: ${err instanceof Error ? err.message : String(err)}`);
                    }
                }}
                disabled={loading}
                style={{
                    background: loading ? '#9ca3af' : 'linear-gradient(135deg, #0284c7, #38bdf8)',
                    color: 'white',
                    border: 'none',
                    padding: '10px 20px',
                    borderRadius: '8px',
                    cursor: loading ? 'not-allowed' : 'pointer',
                    fontWeight: 600,
                    fontSize: '0.95rem',
                    marginBottom: '1rem',
                    marginLeft: '0.5rem',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '8px',
                }}
                title="Sincroniza códigos abiertos desde PostgreSQL a Neo4j (crea nodos y relaciones)"
            >
                🔄 Sincronizar con Neo4j
            </button>

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

                            const pairKey = (p: any) => `${p.code1}|||${p.code2}`;
                            const selectedPairs = duplicateSelectMode === "all"
                                ? similarPairs
                                : similarPairs.filter(p => selectedDuplicateKeys.has(pairKey(p)));

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
                                        {similarPairs.length > 0 && (
                                            <span style={{ marginLeft: '0.5rem', color: '#065f46' }}>
                                                • seleccionados: <strong>{selectedPairs.length}</strong>
                                            </span>
                                        )}
                                    </div>

                                    {similarPairs.length === 0 ? (
                                        <p className="no-examples">
                                            ✅ Todos los duplicados son el mismo código repetido (sin variaciones a fusionar)
                                        </p>
                                    ) : (
                                        <>
                                            {/* Selection controls */}
                                            <div style={{
                                                display: 'flex',
                                                justifyContent: 'space-between',
                                                alignItems: 'center',
                                                flexWrap: 'wrap',
                                                gap: '0.5rem',
                                                marginBottom: '0.75rem'
                                            }}>
                                                <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                                                    <span style={{ fontSize: '0.85rem', color: '#374151', fontWeight: 600 }}>
                                                        Selección:
                                                    </span>
                                                    <label style={{ display: 'flex', gap: '0.35rem', alignItems: 'center', fontSize: '0.85rem' }}>
                                                        <input
                                                            type="radio"
                                                            name="dup-mode"
                                                            checked={duplicateSelectMode === "all"}
                                                            onChange={() => setDuplicateSelectMode("all")}
                                                        />
                                                        Todos
                                                    </label>
                                                    <label style={{ display: 'flex', gap: '0.35rem', alignItems: 'center', fontSize: '0.85rem' }}>
                                                        <input
                                                            type="radio"
                                                            name="dup-mode"
                                                            checked={duplicateSelectMode === "manual"}
                                                            onChange={() => setDuplicateSelectMode("manual")}
                                                        />
                                                        Uno a uno
                                                    </label>
                                                </div>
                                                {duplicateSelectMode === "manual" && (
                                                    <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                                                        <button
                                                            onClick={() => setSelectedDuplicateKeys(new Set(similarPairs.map(pairKey)))}
                                                            className="btn"
                                                            type="button"
                                                        >
                                                            Seleccionar todos
                                                        </button>
                                                        <button
                                                            onClick={() => setSelectedDuplicateKeys(new Set())}
                                                            className="btn"
                                                            type="button"
                                                        >
                                                            Limpiar
                                                        </button>
                                                    </div>
                                                )}
                                            </div>

                                            <table>
                                                <thead>
                                                    <tr>
                                                        <th style={{ width: '3.25rem' }}>Sel.</th>
                                                        <th>Código 1</th>
                                                        <th>Código 2</th>
                                                        <th>Similitud</th>
                                                        <th>Sugerencia</th>
                                                        <th style={{ width: '8.5rem' }}>Acción</th>
                                                    </tr>
                                                </thead>
                                                <tbody>
                                                    {similarPairs.map((pair, i) => {
                                                        // Suggest keeping the shorter code (usually cleaner)
                                                        const suggested = pair.code1.length <= pair.code2.length ? pair.code1 : pair.code2;
                                                        const k = pairKey(pair);
                                                        const checked = duplicateSelectMode === "all" ? true : selectedDuplicateKeys.has(k);
                                                        return (
                                                            <tr key={i}>
                                                                <td>
                                                                    <input
                                                                        type="checkbox"
                                                                        checked={checked}
                                                                        disabled={duplicateSelectMode === "all"}
                                                                        onChange={(e) => {
                                                                            const next = new Set(selectedDuplicateKeys);
                                                                            if (e.target.checked) next.add(k);
                                                                            else next.delete(k);
                                                                            setSelectedDuplicateKeys(next);
                                                                        }}
                                                                    />
                                                                </td>
                                                                <td>{pair.code1}</td>
                                                                <td>{pair.code2}</td>
                                                                <td>{(pair.similarity * 100).toFixed(0)}%</td>
                                                                <td style={{ color: '#059669', fontWeight: 500 }}>
                                                                    → {suggested}
                                                                </td>
                                                                <td>
                                                                    <button
                                                                        onClick={() => handleAutoMerge([pair], { closeModal: false })}
                                                                        disabled={autoMerging}
                                                                        className="btn"
                                                                        type="button"
                                                                        style={{
                                                                            padding: '0.35rem 0.6rem',
                                                                            fontSize: '0.85rem'
                                                                        }}
                                                                    >
                                                                        Fusionar
                                                                    </button>
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
                                                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                                                    <button
                                                        onClick={() => handleAutoMerge(similarPairs)}
                                                        disabled={autoMerging}
                                                        style={{
                                                            padding: '0.5rem 0.9rem',
                                                            background: autoMerging ? '#9ca3af' : 'linear-gradient(135deg, #059669, #10b981)',
                                                            color: 'white',
                                                            border: 'none',
                                                            borderRadius: '0.375rem',
                                                            cursor: autoMerging ? 'not-allowed' : 'pointer',
                                                            fontWeight: 600,
                                                            fontSize: '0.9rem'
                                                        }}
                                                    >
                                                        {autoMerging ? mergeProgress : `🔄 Auto-fusionar todos (${similarPairs.length})`}
                                                    </button>
                                                    <button
                                                        onClick={() => handleAutoMerge(selectedPairs)}
                                                        disabled={autoMerging || selectedPairs.length === 0}
                                                        style={{
                                                            padding: '0.5rem 0.9rem',
                                                            background: (autoMerging || selectedPairs.length === 0)
                                                                ? '#9ca3af'
                                                                : 'linear-gradient(135deg, #2563eb, #3b82f6)',
                                                            color: 'white',
                                                            border: 'none',
                                                            borderRadius: '0.375rem',
                                                            cursor: (autoMerging || selectedPairs.length === 0) ? 'not-allowed' : 'pointer',
                                                            fontWeight: 600,
                                                            fontSize: '0.9rem'
                                                        }}
                                                    >
                                                        {autoMerging
                                                            ? mergeProgress
                                                            : `🔄 Auto-fusionar seleccionados (${selectedPairs.length})`}
                                                    </button>
                                                </div>
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

            {/* AI Runner Plan Modal (auditables por run_id) */}
            {showAiPlan && (
                <div className="validation-panel__modal">
                    <div className="modal-content modal-content--wide">
                        <h4>🤖 Plan IA (solo propuestas)</h4>
                        <p style={{ color: "#374151" }}>
                            Este plan fue persistido para auditoría.
                            {aiPlanRunId ? (
                                <>
                                    {" "}run_id: <strong>{aiPlanRunId}</strong>
                                </>
                            ) : null}
                            {aiPlanThreshold ? (
                                <>
                                    {" "}• umbral: <strong>{Math.round(aiPlanThreshold * 100)}%</strong>
                                </>
                            ) : null}
                            {aiPlanPairs.length ? (
                                <>
                                    {" "}• pares pendientes: <strong>{aiPlanPairs.length}</strong>
                                </>
                            ) : null}
                        </p>

                        {aiPlanPairs.length === 0 ? (
                            <p className="no-examples">No hay pares pendientes en este plan.</p>
                        ) : (
                            <div style={{ maxHeight: 420, overflow: "auto", paddingRight: 6 }}>
                                {aiPlanPairs.map((p, idx) => {
                                    const source = (p.source_codigo || "").trim();
                                    const target = (p.target_codigo || "").trim();
                                    const key = `${source}→${target}`;
                                    const simPct = Math.round((p.similarity ?? 0) * 100);
                                    const disabled = Boolean(aiPlanApplyingKey) && aiPlanApplyingKey !== key;
                                    const applying = aiPlanApplyingKey === key;
                                    return (
                                        <div
                                            key={`${key}-${idx}`}
                                            style={{
                                                display: "flex",
                                                justifyContent: "space-between",
                                                gap: 12,
                                                alignItems: "center",
                                                padding: "0.6rem 0.75rem",
                                                marginBottom: "0.5rem",
                                                background: "#f8fafc",
                                                border: "1px solid #e5e7eb",
                                                borderRadius: "0.5rem",
                                            }}
                                        >
                                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                                                <div style={{ fontWeight: 700, color: "#111827" }}>
                                                    {source} <span style={{ color: "#64748b" }}>→</span> {target}
                                                </div>
                                                <div style={{ fontSize: "0.85rem", color: "#475569" }}>
                                                    similitud: <strong>{simPct}%</strong>
                                                    {p.reason ? <span style={{ color: "#94a3b8" }}> • {p.reason}</span> : null}
                                                </div>
                                            </div>
                                            <button
                                                className="btn btn--merge"
                                                onClick={() => handleApplyAiPlanPair(p)}
                                                disabled={disabled || applying}
                                                title="Aplicar este merge (uno a uno)"
                                            >
                                                {applying ? "Aplicando..." : "Aplicar"}
                                            </button>
                                        </div>
                                    );
                                })}
                            </div>
                        )}

                        <div className="modal-actions">
                            <button
                                onClick={() => {
                                    setShowAiPlan(false);
                                }}
                            >
                                Cerrar
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Prehoc Batch Check Modal */}
            {showPrehoc && (
                <div className="validation-panel__modal">
                    <div className="modal-content modal-content--wide">
                        <h4>🔍 Duplicados Prehoc (Batch Check)</h4>
                        <p>
                            Revisa similitudes contra códigos existentes y duplicados dentro del mismo lote (bandeja actual).
                            Umbral ≥{Math.round(prehocThreshold * 100)}%.
                        </p>

                        {prehocLoading && <p className="loading-text">Analizando (Prehoc)...</p>}

                        {!prehocLoading && prehocResponse && (() => {
                            const results: BatchCheckResult[] = prehocResponse.results || [];
                            const flagged = results.filter(r => Boolean(r.has_similar || r.duplicate_in_batch));
                            const list = prehocShowAll ? results : flagged;
                            const hasFlags = flagged.length > 0;

                            const keyOf = (r: BatchCheckResult) => (r.codigo || "").trim();
                            const allKeys = new Set(list.map(keyOf).filter(Boolean));
                            const selectedCount = Array.from(prehocSelectedKeys).filter(k => allKeys.has(k)).length;

                            const mergeTargetClean = (prehocMergeTarget || "").trim();
                            const selectedItemsForMerge = (prehocSelectMode === "all")
                                ? list
                                : list.filter(r => prehocSelectedKeys.has(keyOf(r)));
                            let estimatedPairs = 0;
                            let estimatedSkippedNoTarget = 0;
                            let estimatedSkippedSelf = 0;
                            for (const r of selectedItemsForMerge) {
                                const source = keyOf(r);
                                if (!source) continue;
                                const suggested = (r.similar || [])
                                    .slice()
                                    .sort((a, b) => (b.similarity ?? 0) - (a.similarity ?? 0))[0]?.existing;
                                const target = mergeTargetClean || (suggested ? String(suggested).trim() : "");
                                if (!target) {
                                    estimatedSkippedNoTarget += 1;
                                    continue;
                                }
                                if (source.toLowerCase() === target.toLowerCase()) {
                                    estimatedSkippedSelf += 1;
                                    continue;
                                }
                                estimatedPairs += 1;
                            }

                            return (
                                <div className="duplicates-list">
                                    <div style={{
                                        background: '#f0f9ff',
                                        padding: '0.5rem 0.75rem',
                                        borderRadius: '0.375rem',
                                        marginBottom: '0.75rem',
                                        fontSize: '0.85rem'
                                    }}>
                                        <strong>📊 Resumen:</strong>{' '}
                                        <span style={{ color: '#0369a1', fontWeight: 600 }}>
                                            {prehocResponse.checked_count} analizados
                                        </span>
                                        {typeof prehocResponse.existing_count === 'number' && (
                                            <span style={{ color: '#6b7280' }}>
                                                {' '}• {prehocResponse.existing_count} existentes
                                            </span>
                                        )}
                                        {typeof prehocResponse.batch_unique_count === 'number' && (
                                            <span style={{ color: '#6b7280' }}>
                                                {' '}• {prehocResponse.batch_unique_count} únicos en batch
                                            </span>
                                        )}
                                        {typeof prehocResponse.batch_duplicate_groups === 'number' && (
                                            <span style={{ color: '#6b7280' }}>
                                                {' '}• {prehocResponse.batch_duplicate_groups} grupo(s) duplicados
                                            </span>
                                        )}
                                        {typeof prehocResponse.batch_duplicates_total === 'number' && (
                                            <span style={{ color: '#6b7280' }}>
                                                {' '}• {prehocResponse.batch_duplicates_total} duplicados totales
                                            </span>
                                        )}
                                        <div style={{ marginTop: '0.4rem', color: '#065f46' }}>
                                            Marcados: <strong>{flagged.length}</strong>
                                            {!prehocShowAll && (
                                                <span style={{ color: '#6b7280' }}>
                                                    {' '}(mostrando solo marcados)
                                                </span>
                                            )}
                                            <span style={{ marginLeft: '0.5rem', color: '#065f46' }}>
                                                • seleccionados: <strong>{prehocSelectMode === "all" ? list.length : selectedCount}</strong>
                                            </span>
                                        </div>
                                    </div>

                                    {!hasFlags && (
                                        <p className="no-examples">
                                            ✅ No se encontraron similitudes ni duplicados en batch con el umbral {Math.round(prehocThreshold * 100)}%.
                                        </p>
                                    )}

                                    {list.length > 0 && (
                                        <div style={{
                                            marginBottom: '0.75rem',
                                            display: 'flex',
                                            gap: '0.75rem',
                                            alignItems: 'center',
                                            flexWrap: 'wrap',
                                            justifyContent: 'space-between'
                                        }}>
                                            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
                                                <button
                                                    type="button"
                                                    className="btn"
                                                    onClick={() => {
                                                        setPrehocShowAll(v => {
                                                            const next = !v;
                                                            const nextList = next ? results : flagged;
                                                            if (prehocSelectMode === "all") {
                                                                setPrehocSelectedKeys(new Set(nextList.map(keyOf).filter(Boolean)));
                                                            }
                                                            return next;
                                                        });
                                                    }}
                                                >
                                                    {prehocShowAll ? `Mostrar solo marcados (${flagged.length})` : `Mostrar todos (${results.length})`}
                                                </button>

                                                <span style={{ fontSize: '0.85rem', color: '#374151', fontWeight: 600 }}>
                                                    Selección:
                                                </span>
                                                <label style={{ display: 'flex', gap: '0.35rem', alignItems: 'center', fontSize: '0.85rem' }}>
                                                    <input
                                                        type="radio"
                                                        name="prehoc-mode"
                                                        checked={prehocSelectMode === "all"}
                                                        onChange={() => {
                                                            setPrehocSelectMode("all");
                                                            setPrehocSelectedKeys(new Set(list.map(keyOf).filter(Boolean)));
                                                        }}
                                                    />
                                                    Todos
                                                </label>
                                                <label style={{ display: 'flex', gap: '0.35rem', alignItems: 'center', fontSize: '0.85rem' }}>
                                                    <input
                                                        type="radio"
                                                        name="prehoc-mode"
                                                        checked={prehocSelectMode === "manual"}
                                                        onChange={() => {
                                                            setPrehocSelectMode("manual");
                                                            // Keep current selection if any; otherwise default to all.
                                                            setPrehocSelectedKeys(prev => (prev.size > 0 ? prev : new Set(list.map(keyOf).filter(Boolean))));
                                                        }}
                                                    />
                                                    Uno a uno
                                                </label>
                                            </div>

                                            {prehocSelectMode === "manual" && (
                                                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                                                    <button
                                                        type="button"
                                                        className="btn"
                                                        onClick={() => setPrehocSelectedKeys(new Set(list.map(keyOf).filter(Boolean)))}
                                                    >
                                                        Seleccionar todos
                                                    </button>
                                                    <button
                                                        type="button"
                                                        className="btn"
                                                        onClick={() => setPrehocSelectedKeys(new Set())}
                                                    >
                                                        Limpiar
                                                    </button>
                                                </div>
                                            )}
                                        </div>
                                    )}

                                    {list.map((r, idx) => (
                                        <div key={idx} style={{
                                            padding: '0.75rem',
                                            marginBottom: '0.5rem',
                                            background: (r.has_similar || r.duplicate_in_batch) ? '#fef3c7' : '#d1fae5',
                                            borderRadius: '0.5rem',
                                            borderLeft: `4px solid ${(r.has_similar || r.duplicate_in_batch) ? '#f59e0b' : '#10b981'}`,
                                        }}>
                                            <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', marginBottom: '0.35rem' }}>
                                                <input
                                                    type="checkbox"
                                                    checked={prehocSelectMode === "all" ? true : prehocSelectedKeys.has(keyOf(r))}
                                                    disabled={prehocSelectMode === "all"}
                                                    onChange={(e) => {
                                                        const k = keyOf(r);
                                                        setPrehocSelectedKeys(prev => {
                                                            const next = new Set(prev);
                                                            if (e.target.checked) next.add(k);
                                                            else next.delete(k);
                                                            return next;
                                                        });
                                                    }}
                                                />
                                                <span style={{ fontSize: '0.85rem', color: '#374151' }}>
                                                    Seleccionar
                                                </span>
                                            </div>
                                            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem', flexWrap: 'wrap' }}>
                                                <strong>{r.codigo}</strong>
                                                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                                                    {r.duplicate_in_batch && (
                                                        <span style={{
                                                            background: '#fff7ed',
                                                            border: '1px solid #fdba74',
                                                            color: '#9a3412',
                                                            padding: '0.1rem 0.45rem',
                                                            borderRadius: '999px',
                                                            fontSize: '0.75rem',
                                                            fontWeight: 700,
                                                        }}>
                                                            Duplicado en batch{typeof r.batch_group_size === 'number' ? ` (x${r.batch_group_size})` : ''}
                                                        </span>
                                                    )}
                                                    {r.has_similar && (
                                                        <span style={{
                                                            background: '#f0f9ff',
                                                            border: '1px solid #93c5fd',
                                                            color: '#1d4ed8',
                                                            padding: '0.1rem 0.45rem',
                                                            borderRadius: '999px',
                                                            fontSize: '0.75rem',
                                                            fontWeight: 700,
                                                        }}>
                                                            Similar existente
                                                        </span>
                                                    )}
                                                </div>
                                            </div>

                                            {r.has_similar && r.similar?.length > 0 && (
                                                <div style={{ fontSize: '0.85rem', marginTop: '0.35rem' }}>
                                                    Similar a:{' '}
                                                    {r.similar.map((s, i) => (
                                                        <span key={i}>
                                                            <code>{s.existing}</code> ({Math.round(s.similarity * 100)}%)
                                                            {i < r.similar.length - 1 && ', '}
                                                        </span>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    ))}

                                    {list.length > 0 && (
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
                                            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
                                                <span style={{ fontSize: '0.85rem', color: '#065f46', fontWeight: 600 }}>
                                                    🔗 Fusión (Prehoc)
                                                </span>
                                                <span style={{ fontSize: '0.8rem', color: '#065f46' }}>
                                                    Pares listos: <strong>{estimatedPairs}</strong>
                                                    {(estimatedSkippedNoTarget + estimatedSkippedSelf) > 0 && (
                                                        <>
                                                            {' '}• omitidos: <strong>{estimatedSkippedNoTarget + estimatedSkippedSelf}</strong>
                                                            {estimatedSkippedNoTarget > 0 && (
                                                                <span style={{ color: '#6b7280' }}> (sin destino: {estimatedSkippedNoTarget})</span>
                                                            )}
                                                            {estimatedSkippedSelf > 0 && (
                                                                <span style={{ color: '#6b7280' }}> (self: {estimatedSkippedSelf})</span>
                                                            )}
                                                        </>
                                                    )}
                                                </span>
                                                <input
                                                    type="text"
                                                    placeholder="Código destino (opcional)"
                                                    value={prehocMergeTarget}
                                                    onChange={(e) => setPrehocMergeTarget(e.target.value)}
                                                    style={{
                                                        width: 'min(420px, 90vw)',
                                                        padding: '0.45rem 0.6rem',
                                                        border: '1px solid #d1d5db',
                                                        borderRadius: '0.375rem'
                                                    }}
                                                    title="Si se deja vacío, se usa el código existente más similar sugerido para cada item (si existe)."
                                                />
                                            </div>

                                            <button
                                                type="button"
                                                className="btn"
                                                disabled={prehocMerging || (prehocSelectMode === "manual" && prehocSelectedKeys.size === 0)}
                                                onClick={() => handlePrehocMergeSelected(list)}
                                                style={{
                                                    padding: '0.5rem 0.9rem',
                                                    background: (prehocMerging ? '#9ca3af' : 'linear-gradient(135deg, #059669, #10b981)'),
                                                    color: 'white',
                                                    border: 'none',
                                                    borderRadius: '0.375rem',
                                                    cursor: prehocMerging ? 'not-allowed' : 'pointer',
                                                    fontWeight: 600,
                                                    fontSize: '0.9rem'
                                                }}
                                                title="Fusiona por nombre de código (backend auto-merge)."
                                            >
                                                {prehocMerging
                                                    ? '⏳ Fusionando...'
                                                    : `🔗 Fusionar seleccionados (${prehocSelectMode === "all" ? list.length : selectedCount})`}
                                            </button>
                                        </div>
                                    )}
                                </div>
                            );
                        })()}

                        <div className="modal-actions">
                            <label>
                                Umbral:
                                <input
                                    type="range"
                                    min="60"
                                    max="95"
                                    value={Math.round(prehocThreshold * 100)}
                                    onChange={e => setPrehocThreshold(parseInt(e.target.value) / 100)}
                                />
                                {Math.round(prehocThreshold * 100)}%
                            </label>
                            <button onClick={handleDetectDuplicatesPrehoc} disabled={prehocLoading}>
                                🔄 Re-analizar
                            </button>
                            <button onClick={() => { setShowPrehoc(false); setPrehocResponse(null); setPrehocShowAll(false); }}>
                                Cerrar
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Botón de promover movido arriba (después de filtros, línea ~1245) */}

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
                                                onClick={() => {
                                                    setFilterEstado("validado");
                                                    setFilterPromovido("no");
                                                }}
                                            >
                                                ✅ Ver validados (por promover)
                                            </button>
                                            <button
                                                type="button"
                                                className="btn"
                                                onClick={() => {
                                                    setFilterEstado("validado");
                                                    setFilterPromovido("si");
                                                }}
                                            >
                                                ⬆️ Ver promovidos
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
                                    {c.estado === "validado" && c.promovido_en && (
                                        <span style={{ marginLeft: 8, opacity: 0.75 }} title={`Promovido: ${c.promovido_en}`}>
                                            ↑ promovido
                                        </span>
                                    )}
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
                    max-height: 85vh;
                    display: flex;
                    flex-direction: column;
                    overflow: hidden;
        }
        .modal-content--wide {
                    max-width: 95vw;
                    width: min(1000px, 95vw);
        }
        .modal-content h4 { margin: 0 0 0.5rem 0; }
        .modal-content h5 { margin: 0.5rem 0; font-size: 0.85rem; color: #6366f1; }
        .modal-content p { margin: 0 0 1rem 0; color: #64748b; font-size: 0.9rem; }
        .modal-content input { width: 100%; padding: 0.5rem; border: 1px solid #d1d5db; border-radius: 0.375rem; margin-bottom: 1rem; }
                .modal-actions {
                    display: flex;
                    gap: 0.5rem;
                    justify-content: flex-end;
                    margin-top: 1rem;
                    position: sticky;
                    bottom: 0;
                    background: white;
                    padding-top: 0.75rem;
                    border-top: 1px solid #e5e7eb;
                    flex-wrap: wrap;
                }

                /* Duplicates list modal content */
                .duplicates-list {
                    overflow: auto;
                    max-height: 50vh;
                    padding-right: 0.25rem;
                }
                .duplicates-list table {
                    width: 100%;
                    border-collapse: collapse;
                }
                .duplicates-list th,
                .duplicates-list td {
                    padding: 0.5rem;
                    border-bottom: 1px solid #e5e7eb;
                    vertical-align: top;
                }
                .duplicates-list th {
                    position: sticky;
                    top: 0;
                    background: #f8fafc;
                    z-index: 1;
                }
                .duplicates-list td {
                    word-break: break-word;
                }
        
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
