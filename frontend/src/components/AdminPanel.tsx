/**
 * @fileoverview Panel de Administración para gestión de usuarios.
 * Solo visible para usuarios con rol 'admin'.
 */

import React, { useCallback, useEffect, useState } from "react";
import { apiFetchJson, apiFetch } from "../services/api";
import { CodeIdTransitionSection } from "./CodeIdTransitionSection";
import { AdminOpsPanel } from "./AdminOpsPanel";
import "./AdminPanel.css";

// Constante de localStorage consistente con App.tsx
const PROJECT_STORAGE_KEY = "qualy-dashboard-project";

interface OrgUser {
    id: string;
    email: string;
    full_name: string | null;
    role: string;
    organization_id: string;
    is_active: boolean;
    created_at: string;
    last_login: string | null;
}

interface OrgStats {
    organization_id: string;
    users_by_role: Record<string, number>;
    total_users: number;
    total_fragments: number;
    active_sessions: number;
}

interface SyncStatus {
    pending: number;
    synced: number;
    total: number;
    neo4j_available: boolean;
    project: string;
}

interface MemberSyncResult {
    project: string;
    org_id: string;
    users_total: number;
    members_assigned: number;
    use_user_role: boolean;
    default_role: string;
    include_inactive: boolean;
}

// Neo4j Sync Section Component
function Neo4jSyncSection() {
    const [status, setStatus] = useState<SyncStatus | null>(null);
    const [syncing, setSyncing] = useState(false);
    const [axialSyncing, setAxialSyncing] = useState(false);
    const [resetting, setResetting] = useState(false);
    const [message, setMessage] = useState<string | null>(null);
    const [axialMessage, setAxialMessage] = useState<string | null>(null);
    const project = localStorage.getItem(PROJECT_STORAGE_KEY) || "default";

    const fetchStatus = useCallback(async () => {
        try {
            const res = await apiFetchJson<SyncStatus>(
                `/api/admin/sync-neo4j/status?project=${encodeURIComponent(project)}`
            );
            setStatus(res);
        } catch (err) {
            console.error("Error fetching sync status:", err);
        }
    }, [project]);

    useEffect(() => {
        void fetchStatus();
    }, [fetchStatus]);

    const handleSync = async () => {
        setSyncing(true);
        setMessage(null);
        setAxialMessage(null);
        try {
            const res = await apiFetchJson<{
                synced: number;
                failed: number;
                remaining: number;
            }>(`/api/admin/sync-neo4j?project=${encodeURIComponent(project)}`, {
                method: "POST",
            });
            setMessage(`✅ Sincronizados ${res.synced} fragmentos. Pendientes: ${res.remaining}`);
            await fetchStatus();
        } catch (err) {
            setMessage(`❌ Error: ${err instanceof Error ? err.message : "Error desconocido"}`);
        } finally {
            setSyncing(false);
        }
    };

    const handleAxialSync = async () => {
        setAxialSyncing(true);
        setAxialMessage(null);
        try {
            const res = await apiFetchJson<{
                synced: number;
                skipped: number;
                remaining: number;
            }>(`/api/admin/sync-neo4j/axial?project=${encodeURIComponent(project)}`, {
                method: "POST",
            });
            const remainingNote = res.remaining > 0 ? ` Pendientes: ${res.remaining}` : "";
            setAxialMessage(
                `✅ Axial: ${res.synced} relaciones. Omitidas: ${res.skipped}.${remainingNote}`
            );
        } catch (err) {
            setAxialMessage(`❌ Error axial: ${err instanceof Error ? err.message : "Error desconocido"}`);
        } finally {
            setAxialSyncing(false);
        }
    };

    const handleResetSyncFlags = async () => {
        setResetting(true);
        setMessage(null);
        setAxialMessage(null);
        try {
            const res = await apiFetchJson<{
                status: string;
                message?: string;
                pending?: number;
                synced?: number;
                total?: number;
            }>(`/api/admin/sync-neo4j/reset?project=${encodeURIComponent(project)}`, {
                method: "POST",
            });
            if (res.message) {
                setMessage(`✅ ${res.message}`);
            }
            await fetchStatus();
        } catch (err) {
            setMessage(`❌ Error: ${err instanceof Error ? err.message : "Error desconocido"}`);
        } finally {
            setResetting(false);
        }
    };

    if (!status) return null;

    return (
        <section className="admin-panel__neo4j-sync">
            <h3>🔄 Sincronización Neo4j</h3>
            <div className="sync-status-grid">
                <div className={`sync-indicator ${status.neo4j_available ? "connected" : "disconnected"}`}>
                    {status.neo4j_available ? "✅ Neo4j Conectado" : "❌ Neo4j Desconectado"}
                </div>
                <div className="sync-stat">
                    <span className="sync-value">{status.pending}</span>
                    <span className="sync-label">Pendientes</span>
                </div>
                <div className="sync-stat">
                    <span className="sync-value">{status.synced}</span>
                    <span className="sync-label">Sincronizados</span>
                </div>
                <div className="sync-stat">
                    <span className="sync-value">{status.total}</span>
                    <span className="sync-label">Total</span>
                </div>
            </div>
            <p className="sync-note">Nota: estos contadores se basan en PostgreSQL (flags neo4j_synced).</p>
            {status.pending > 0 && (
                <button
                    className="sync-button"
                    onClick={handleSync}
                    disabled={syncing || !status.neo4j_available}
                >
                    {syncing ? "Sincronizando..." : `Sincronizar ${status.pending} fragmentos`}
                </button>
            )}
            <button
                className="sync-button"
                onClick={handleAxialSync}
                disabled={axialSyncing || !status.neo4j_available}
            >
                {axialSyncing ? "Sincronizando axial..." : "Sincronizar relaciones axiales"}
            </button>
            <button
                className="sync-button sync-button--warn"
                onClick={handleResetSyncFlags}
                disabled={resetting}
                title="Resetea los flags neo4j_synced para forzar re-sincronización"
            >
                {resetting ? "Reseteando..." : "Resetear flags de sincronización"}
            </button>
            {message && <div className="sync-message">{message}</div>}
            {axialMessage && <div className="sync-message">{axialMessage}</div>}
        </section>
    );
}

interface AdminPanelProps {
    currentUserId: string;
}

interface CleanupResult {
    status: string;
    message: string;
    project?: string;
    counts?: Record<string, number>;
    cleaned_projects?: Array<{ project_id: string; rows_deleted: number }>;
}

interface AnalysisResult {
    status: string;
    project: string;
    [key: string]: any;
}

// Cleanup Section Component
function CleanupSection() {
    const [project, setProject] = useState(() => localStorage.getItem(PROJECT_STORAGE_KEY) || "default");
    const [cleaningAll, setCleaningAll] = useState(false);
    const [cleaningProjects, setCleaningProjects] = useState(false);
    const [cleaningOrphans, setCleaningOrphans] = useState(false);
    const [cleaningNeo4jOrphans, setCleaningNeo4jOrphans] = useState(false);
    const [cleaningNeo4jUnscoped, setCleaningNeo4jUnscoped] = useState(false);
    const [cleaningNeo4jUnscopedRels, setCleaningNeo4jUnscopedRels] = useState(false);
    const [cleanupMessage, setCleanupMessage] = useState<string | null>(null);
    const [showCollapsed, setShowCollapsed] = useState(true);

    const handleCleanupAll = async () => {
        if (!confirm("⚠️ ADVERTENCIA: Esta acción eliminará TODOS los datos del proyecto.\n¿Continuar?")) {
            return;
        }
        
        setCleaningAll(true);
        setCleanupMessage(null);
        try {
            const res = await apiFetchJson<CleanupResult>(
                `/api/admin/cleanup/all-data?project=${encodeURIComponent(project)}`,
                {
                    method: "POST",
                    body: JSON.stringify({ confirm: true, reason: "Manual cleanup from AdminPanel" }),
                }
            );
            setCleanupMessage(`✅ ${res.message}`);
        } catch (err) {
            setCleanupMessage(`❌ Error: ${err instanceof Error ? err.message : "Error desconocido"}`);
        } finally {
            setCleaningAll(false);
        }
    };

    const handleCleanupProjects = async () => {
        if (!confirm("⚠️ ADVERTENCIA: Eliminará datos de proyectos marcados como deleted.\n¿Continuar?")) {
            return;
        }
        
        setCleaningProjects(true);
        setCleanupMessage(null);
        try {
            const res = await apiFetchJson<CleanupResult>(
                "/api/admin/cleanup/projects",
                {
                    method: "POST",
                    body: JSON.stringify({ confirm: true, reason: "Manual cleanup from AdminPanel" }),
                }
            );
            setCleanupMessage(`✅ ${res.message}`);
        } catch (err) {
            setCleanupMessage(`❌ Error: ${err instanceof Error ? err.message : "Error desconocido"}`);
        } finally {
            setCleaningProjects(false);
        }
    };

    const handleCleanupOrphans = async () => {
        if (!confirm("⚠️ ADVERTENCIA: Eliminará archivos huérfanos (DB + Neo4j).\n¿Continuar?")) {
            return;
        }

        setCleaningOrphans(true);
        setCleanupMessage(null);
        try {
            const res = await apiFetchJson<CleanupResult>(
                `/api/admin/cleanup/orphans?project=${encodeURIComponent(project)}`,
                {
                    method: "POST",
                    body: JSON.stringify({ confirm: true, reason: "Manual orphan cleanup from AdminPanel" }),
                }
            );
            setCleanupMessage(`✅ ${res.message}`);
        } catch (err) {
            setCleanupMessage(`❌ Error: ${err instanceof Error ? err.message : "Error desconocido"}`);
        } finally {
            setCleaningOrphans(false);
        }
    };

    const handleCleanupNeo4jOrphans = async () => {
        if (!confirm("⚠️ ADVERTENCIA: Eliminará nodos huérfanos en Neo4j.\n¿Continuar?")) {
            return;
        }

        setCleaningNeo4jOrphans(true);
        setCleanupMessage(null);
        try {
            const res = await apiFetchJson<CleanupResult>(
                `/api/admin/cleanup/neo4j-orphans?project=${encodeURIComponent(project)}`,
                {
                    method: "POST",
                    body: JSON.stringify({ confirm: true, reason: "Manual Neo4j orphan cleanup from AdminPanel" }),
                }
            );
            setCleanupMessage(`✅ ${res.message}`);
        } catch (err) {
            setCleanupMessage(`❌ Error: ${err instanceof Error ? err.message : "Error desconocido"}`);
        } finally {
            setCleaningNeo4jOrphans(false);
        }
    };

    const handleCleanupNeo4jUnscoped = async () => {
        if (!confirm("⚠️ ADVERTENCIA: Eliminará nodos Neo4j sin project_id (datos antiguos).\n¿Continuar?")) {
            return;
        }

        setCleaningNeo4jUnscoped(true);
        setCleanupMessage(null);
        try {
            const res = await apiFetchJson<CleanupResult>(
                "/api/admin/cleanup/neo4j-unscoped",
                {
                    method: "POST",
                    body: JSON.stringify({ confirm: true, reason: "Manual Neo4j unscoped cleanup from AdminPanel" }),
                }
            );
            setCleanupMessage(`✅ ${res.message}`);
        } catch (err) {
            setCleanupMessage(`❌ Error: ${err instanceof Error ? err.message : "Error desconocido"}`);
        } finally {
            setCleaningNeo4jUnscoped(false);
        }
    };

    const handleCleanupNeo4jUnscopedRels = async () => {
        if (!confirm("⚠️ ADVERTENCIA: Eliminará relaciones Neo4j sin project_id (origen/destino sin project_id).\n¿Continuar?")) {
            return;
        }

        setCleaningNeo4jUnscopedRels(true);
        setCleanupMessage(null);
        try {
            const res = await apiFetchJson<CleanupResult>(
                "/api/admin/cleanup/neo4j-unscoped-relationships",
                {
                    method: "POST",
                    body: JSON.stringify({ confirm: true, reason: "Manual Neo4j unscoped relationship cleanup from AdminPanel" }),
                }
            );
            setCleanupMessage(`✅ ${res.message}`);
        } catch (err) {
            setCleanupMessage(`❌ Error: ${err instanceof Error ? err.message : "Error desconocido"}`);
        } finally {
            setCleaningNeo4jUnscopedRels(false);
        }
    };

    return (
        <section className="admin-panel__cleanup">
            <div className="cleanup__header" onClick={() => setShowCollapsed(!showCollapsed)}>
                <h3>🧹 Limpieza de Datos {showCollapsed ? "▼" : "▶"}</h3>
            </div>
            
            {!showCollapsed && (
                <>
                    <div className="cleanup__warning">
                        ⚠️ Las operaciones de limpieza son destructivas e irreversibles.
                    </div>
                    
                    <div className="cleanup__field">
                        <label htmlFor="cleanup-project">Proyecto</label>
                        <input
                            id="cleanup-project"
                            type="text"
                            value={project}
                            onChange={(e) => setProject(e.target.value)}
                            placeholder="default"
                        />
                    </div>
                    
                    <div className="cleanup__actions">
                        <button
                            className="cleanup-button cleanup-button--danger"
                            onClick={handleCleanupAll}
                            disabled={cleaningAll || cleaningProjects || cleaningOrphans}
                        >
                            {cleaningAll ? "Limpiando..." : "🔥 Eliminar Todo"}
                        </button>
                        <button
                            className="cleanup-button cleanup-button--warning"
                            onClick={handleCleanupProjects}
                            disabled={cleaningAll || cleaningProjects || cleaningOrphans}
                        >
                            {cleaningProjects ? "Limpiando..." : "🗑️ Limpiar Proyectos Deleted"}
                        </button>
                        <button
                            className="cleanup-button cleanup-button--warning"
                            onClick={handleCleanupOrphans}
                            disabled={cleaningAll || cleaningProjects || cleaningOrphans || cleaningNeo4jOrphans}
                        >
                            {cleaningOrphans ? "Limpiando..." : "🧹 Limpiar Huérfanos"}
                        </button>
                        <button
                            className="cleanup-button cleanup-button--warning"
                            onClick={handleCleanupNeo4jOrphans}
                            disabled={cleaningAll || cleaningProjects || cleaningOrphans || cleaningNeo4jOrphans || cleaningNeo4jUnscoped || cleaningNeo4jUnscopedRels}
                        >
                            {cleaningNeo4jOrphans ? "Limpiando..." : "🧽 Limpiar Huérfanos Neo4j"}
                        </button>
                        <button
                            className="cleanup-button cleanup-button--danger"
                            onClick={handleCleanupNeo4jUnscoped}
                            disabled={cleaningAll || cleaningProjects || cleaningOrphans || cleaningNeo4jOrphans || cleaningNeo4jUnscoped || cleaningNeo4jUnscopedRels}
                        >
                            {cleaningNeo4jUnscoped ? "Limpiando..." : "🧨 Limpiar Neo4j sin project_id"}
                        </button>
                        <button
                            className="cleanup-button cleanup-button--danger"
                            onClick={handleCleanupNeo4jUnscopedRels}
                            disabled={cleaningAll || cleaningProjects || cleaningOrphans || cleaningNeo4jOrphans || cleaningNeo4jUnscoped || cleaningNeo4jUnscopedRels}
                        >
                            {cleaningNeo4jUnscopedRels ? "Limpiando..." : "🧨 Limpiar relaciones sin project_id"}
                        </button>
                    </div>
                    
                    {cleanupMessage && <div className="cleanup__message">{cleanupMessage}</div>}
                </>
            )}
        </section>
    );
}

// Analysis Section Component
function AnalysisSection() {
    const [project, setProject] = useState(() => localStorage.getItem(PROJECT_STORAGE_KEY) || "default");
    const [threshold, setThreshold] = useState(0.85);
    const [analyzeLoading, setAnalyzeLoading] = useState<string | null>(null);
    const [analysisResults, setAnalysisResults] = useState<Record<string, AnalysisResult | null>>({
        duplicates: null,
        orphans: null,
        integrity: null,
        neo4j_audit: null,
    });
    const [showCollapsed, setShowCollapsed] = useState(true);

    const handleFindDuplicates = async () => {
        setAnalyzeLoading("duplicates");
        setAnalysisResults((prev) => ({ ...prev, duplicates: null }));
        try {
            const res = await apiFetchJson<AnalysisResult>(
                `/api/admin/cleanup/duplicate-codes?project=${encodeURIComponent(project)}&threshold=${threshold}`,
                { method: "POST" }
            );
            setAnalysisResults((prev) => ({ ...prev, duplicates: res }));
        } catch (err) {
            setAnalysisResults((prev) => ({
                ...prev,
                duplicates: {
                    status: "error",
                    project,
                    message: err instanceof Error ? err.message : "Error desconocido",
                },
            }));
        } finally {
            setAnalyzeLoading(null);
        }
    };

    const handleFindOrphans = async () => {
        setAnalyzeLoading("orphans");
        setAnalysisResults((prev) => ({ ...prev, orphans: null }));
        try {
            const res = await apiFetchJson<AnalysisResult>(
                `/api/admin/analysis/orphan-files?project=${encodeURIComponent(project)}`,
                { method: "GET" }
            );
            setAnalysisResults((prev) => ({ ...prev, orphans: res }));
        } catch (err) {
            setAnalysisResults((prev) => ({
                ...prev,
                orphans: {
                    status: "error",
                    project,
                    message: err instanceof Error ? err.message : "Error desconocido",
                },
            }));
        } finally {
            setAnalyzeLoading(null);
        }
    };

    const handleIntegrityCheck = async () => {
        setAnalyzeLoading("integrity");
        setAnalysisResults((prev) => ({ ...prev, integrity: null }));
        try {
            const res = await apiFetchJson<AnalysisResult>(
                `/api/admin/analysis/integrity?project=${encodeURIComponent(project)}`,
                { method: "GET" }
            );
            setAnalysisResults((prev) => ({ ...prev, integrity: res }));
        } catch (err) {
            setAnalysisResults((prev) => ({
                ...prev,
                integrity: {
                    status: "error",
                    project,
                    message: err instanceof Error ? err.message : "Error desconocido",
                },
            }));
        } finally {
            setAnalyzeLoading(null);
        }
    };

    const handleNeo4jAudit = async () => {
        setAnalyzeLoading("neo4j_audit");
        setAnalysisResults((prev) => ({ ...prev, neo4j_audit: null }));
        try {
            const res = await apiFetchJson<AnalysisResult>(
                `/api/admin/neo4j-audit?project=${encodeURIComponent(project)}`,
                { method: "GET" }
            );
            setAnalysisResults((prev) => ({ ...prev, neo4j_audit: res }));
        } catch (err) {
            setAnalysisResults((prev) => ({
                ...prev,
                neo4j_audit: {
                    status: "error",
                    project,
                    message: err instanceof Error ? err.message : "Error desconocido",
                },
            }));
        } finally {
            setAnalyzeLoading(null);
        }
    };

    return (
        <section className="admin-panel__analysis">
            <div className="analysis__header" onClick={() => setShowCollapsed(!showCollapsed)}>
                <h3>🔍 Análisis de Integridad {showCollapsed ? "▼" : "▶"}</h3>
            </div>
            
            {!showCollapsed && (
                <>
                    <div className="analysis__controls">
                        <div className="analysis__field">
                            <label htmlFor="analysis-project">Proyecto</label>
                            <input
                                id="analysis-project"
                                type="text"
                                value={project}
                                onChange={(e) => setProject(e.target.value)}
                                placeholder="default"
                            />
                        </div>
                        <div className="analysis__field">
                            <label htmlFor="analysis-threshold">Umbral duplicados (0-1)</label>
                            <input
                                id="analysis-threshold"
                                type="number"
                                min="0"
                                max="1"
                                step="0.05"
                                value={threshold}
                                onChange={(e) => setThreshold(parseFloat(e.target.value))}
                            />
                        </div>
                    </div>
                    
                    <div className="analysis__buttons">
                        <button
                            className="analysis-button"
                            onClick={handleFindDuplicates}
                            disabled={analyzeLoading === "duplicates"}
                        >
                            {analyzeLoading === "duplicates" ? "Analizando..." : "🔎 Detectar Duplicados"}
                        </button>
                        <button
                            className="analysis-button"
                            onClick={handleFindOrphans}
                            disabled={analyzeLoading === "orphans"}
                        >
                            {analyzeLoading === "orphans" ? "Analizando..." : "📁 Encontrar Huérfanos"}
                        </button>
                        <button
                            className="analysis-button"
                            onClick={handleIntegrityCheck}
                            disabled={analyzeLoading === "integrity"}
                        >
                            {analyzeLoading === "integrity" ? "Verificando..." : "✓ Integridad"}
                        </button>
                        <button
                            className="analysis-button"
                            onClick={handleNeo4jAudit}
                            disabled={analyzeLoading === "neo4j_audit"}
                        >
                            {analyzeLoading === "neo4j_audit" ? "Analizando..." : "🧭 Audit Neo4j vs PG"}
                        </button>
                    </div>
                    
                    {/* Results Grid */}
                    {(analysisResults.duplicates || analysisResults.orphans || analysisResults.integrity || analysisResults.neo4j_audit) && (
                        <div className="analysis__results">
                            {analysisResults.duplicates && (
                                <div className="result-card">
                                    <h4>Duplicados</h4>
                                    {analysisResults.duplicates.status === "error" ? (
                                        <p className="error">{analysisResults.duplicates.message}</p>
                                    ) : (
                                        <>
                                            <p>
                                                Total de códigos: <strong>{analysisResults.duplicates.total_codes}</strong>
                                            </p>
                                            <p>
                                                Grupos duplicados: <strong>{analysisResults.duplicates.groups_count}</strong>
                                            </p>
                                            {analysisResults.duplicates.duplicate_groups?.length > 0 && (
                                                <details>
                                                    <summary>Ver detalles</summary>
                                                    <ul>
                                                        {analysisResults.duplicates.duplicate_groups.map((group: string[], idx: number) => (
                                                            <li key={idx}>{group.join(", ")}</li>
                                                        ))}
                                                    </ul>
                                                </details>
                                            )}
                                        </>
                                    )}
                                </div>
                            )}
                            
                            {analysisResults.orphans && (
                                <div className="result-card">
                                    <h4>Archivos Huérfanos</h4>
                                    {analysisResults.orphans.status === "error" ? (
                                        <p className="error">{analysisResults.orphans.message}</p>
                                    ) : (
                                        <>
                                            <p>
                                                Total de archivos: <strong>{analysisResults.orphans.total_files}</strong>
                                            </p>
                                            <p>
                                                Huérfanos: <strong>{analysisResults.orphans.orphans_count}</strong>
                                            </p>
                                            {analysisResults.orphans.orphans?.length > 0 && (
                                                <details>
                                                    <summary>Ver lista</summary>
                                                    <ul>
                                                        {analysisResults.orphans.orphans.map((orphan: any, idx: number) => (
                                                            <li key={idx}>{orphan.filename}</li>
                                                        ))}
                                                    </ul>
                                                </details>
                                            )}
                                        </>
                                    )}
                                </div>
                            )}
                            
                            {analysisResults.integrity && (
                                <div className="result-card">
                                    <h4>Integridad</h4>
                                    {analysisResults.integrity.status === "error" ? (
                                        <p className="error">{analysisResults.integrity.message}</p>
                                    ) : (
                                        <>
                                            <p>
                                                Fragmentos: <strong>{analysisResults.integrity.checks?.total_fragments || 0}</strong>
                                            </p>
                                            <p>
                                                Sin códigos:{" "}
                                                <strong style={{ color: "#ff6b6b" }}>
                                                    {analysisResults.integrity.checks?.fragments_without_codes || 0}
                                                </strong>
                                            </p>
                                            <p>
                                                Códigos únicos: <strong>{analysisResults.integrity.checks?.unique_codes || 0}</strong>
                                            </p>
                                            <p>
                                                Asignaciones: <strong>{analysisResults.integrity.checks?.total_code_assignments || 0}</strong>
                                            </p>
                                        </>
                                    )}
                                </div>
                            )}

                            {analysisResults.neo4j_audit && (
                                <div className="result-card">
                                    <h4>Neo4j vs PostgreSQL</h4>
                                    {analysisResults.neo4j_audit.status === "error" ? (
                                        <p className="error">{analysisResults.neo4j_audit.message}</p>
                                    ) : (
                                        <>
                                            <p><strong>PostgreSQL</strong></p>
                                            <p>Fragmentos: <strong>{analysisResults.neo4j_audit.postgres?.fragmentos ?? 0}</strong></p>
                                            <p>Archivos: <strong>{analysisResults.neo4j_audit.postgres?.archivos ?? 0}</strong></p>
                                            <p>Códigos abiertos: <strong>{analysisResults.neo4j_audit.postgres?.codigos_abiertos ?? 0}</strong></p>
                                            <p>Relaciones axiales: <strong>{analysisResults.neo4j_audit.postgres?.relaciones_axiales ?? 0}</strong></p>
                                            <p style={{ marginTop: "0.5rem" }}><strong>Neo4j</strong></p>
                                            <p>Entrevistas: <strong>{analysisResults.neo4j_audit.neo4j?.entrevistas ?? 0}</strong></p>
                                            <p>Fragmentos: <strong>{analysisResults.neo4j_audit.neo4j?.fragmentos ?? 0}</strong></p>
                                            <p>Códigos: <strong>{analysisResults.neo4j_audit.neo4j?.codigos ?? 0}</strong></p>
                                            <p>Categorías: <strong>{analysisResults.neo4j_audit.neo4j?.categorias ?? 0}</strong></p>
                                            <p>Rel TIENE_FRAGMENTO: <strong>{analysisResults.neo4j_audit.neo4j?.rel_tiene_fragmento ?? 0}</strong></p>
                                            <p>Rel TIENE_CODIGO: <strong>{analysisResults.neo4j_audit.neo4j?.rel_tiene_codigo ?? 0}</strong></p>
                                            <p>Rel Axiales: <strong>{analysisResults.neo4j_audit.neo4j?.rel_axial ?? 0}</strong></p>
                                            <p>Nodos sin project_id: <strong>{analysisResults.neo4j_audit.neo4j?.nodes_sin_project_id ?? 0}</strong></p>
                                            <p>Relaciones sin project_id: <strong>{analysisResults.neo4j_audit.neo4j?.rels_sin_project_id ?? 0}</strong></p>
                                        </>
                                    )}
                                </div>
                            )}
                        </div>
                    )}
                </>
            )}
        </section>
    );
}

export function AdminPanel({ currentUserId }: AdminPanelProps) {
    const [users, setUsers] = useState<OrgUser[]>([]);
    const [stats, setStats] = useState<OrgStats | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [actionLoading, setActionLoading] = useState<string | null>(null);
    const [panelResetKey, setPanelResetKey] = useState(0);
    const [syncProjectId, setSyncProjectId] = useState(() => localStorage.getItem(PROJECT_STORAGE_KEY) || "default");
    const [syncOrgId, setSyncOrgId] = useState("default_org");
    const [syncUseUserRole, setSyncUseUserRole] = useState(true);
    const [syncDefaultRole, setSyncDefaultRole] = useState("codificador");
    const [syncIncludeInactive, setSyncIncludeInactive] = useState(false);
    const [syncingMembers, setSyncingMembers] = useState(false);
    const [syncMessage, setSyncMessage] = useState<string | null>(null);

    const loadData = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const [usersRes, statsRes] = await Promise.all([
                apiFetchJson<{ users: OrgUser[] }>("/api/admin/users"),
                apiFetchJson<OrgStats>("/api/admin/stats"),
            ]);
            setUsers(usersRes.users || []);
            setStats(statsRes);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Error cargando datos");
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        void loadData();
    }, [loadData]);

    useEffect(() => {
        if (stats?.organization_id) {
            setSyncOrgId(stats.organization_id);
        }
    }, [stats]);

    const handleResetPanel = () => {
        const projectDefault = localStorage.getItem(PROJECT_STORAGE_KEY) || "default";
        setError(null);
        setSyncMessage(null);
        setActionLoading(null);
        setSyncProjectId(projectDefault);
        setSyncOrgId(stats?.organization_id || "default_org");
        setSyncUseUserRole(true);
        setSyncDefaultRole("codificador");
        setSyncIncludeInactive(false);
        setPanelResetKey((prev) => prev + 1);
        void loadData();
    };

    const handleRoleChange = async (userId: string, newRole: string) => {
        setActionLoading(userId);
        try {
            await apiFetch(`/api/admin/users/${userId}`, {
                method: "PATCH",
                body: JSON.stringify({ role: newRole }),
            });
            await loadData();
        } catch (err) {
            setError(err instanceof Error ? err.message : "Error actualizando rol");
        } finally {
            setActionLoading(null);
        }
    };

    const handleToggleActive = async (userId: string, isActive: boolean) => {
        setActionLoading(userId);
        try {
            await apiFetch(`/api/admin/users/${userId}`, {
                method: "PATCH",
                body: JSON.stringify({ is_active: !isActive }),
            });
            await loadData();
        } catch (err) {
            setError(err instanceof Error ? err.message : "Error actualizando estado");
        } finally {
            setActionLoading(null);
        }
    };

    const handleDeleteUser = async (userId: string, email: string) => {
        if (!confirm(`¿Eliminar usuario ${email}? Esta acción no se puede deshacer.`)) {
            return;
        }
        setActionLoading(userId);
        try {
            await apiFetch(`/api/admin/users/${userId}`, { method: "DELETE" });
            await loadData();
        } catch (err) {
            setError(err instanceof Error ? err.message : "Error eliminando usuario");
        } finally {
            setActionLoading(null);
        }
    };

    const handleSyncMembers = async () => {
        if (!syncProjectId.trim()) {
            setError("Debes indicar el proyecto a sincronizar.");
            return;
        }
        setSyncingMembers(true);
        setSyncMessage(null);
        setError(null);
        try {
            const res = await apiFetchJson<{ result: MemberSyncResult }>(
                `/api/projects/${encodeURIComponent(syncProjectId.trim())}/members/sync-org`,
                {
                    method: "POST",
                    body: JSON.stringify({
                        org_id: syncOrgId.trim() || undefined,
                        default_role: syncDefaultRole,
                        use_user_role: syncUseUserRole,
                        include_inactive: syncIncludeInactive,
                    }),
                }
            );
            const result = res.result;
            setSyncMessage(
                `✅ Miembros sincronizados: ${result.members_assigned} / ${result.users_total} en ${result.project}`
            );
        } catch (err) {
            setError(err instanceof Error ? err.message : "Error sincronizando miembros");
        } finally {
            setSyncingMembers(false);
        }
    };

    if (loading) {
        return <div className="admin-panel admin-panel--loading">Cargando...</div>;
    }

    return (
        <div className="admin-panel">
            <header className="admin-panel__header">
                <h2>🛠️ Panel de Administración</h2>
                <div className="admin-panel__header-actions">
                    <button onClick={loadData} className="admin-panel__refresh">
                        🔄 Actualizar
                    </button>
                    <button onClick={handleResetPanel} className="admin-panel__refresh">
                        ♻️ Resetear
                    </button>
                </div>
            </header>

            {error && (
                <div className="admin-panel__error">
                    ⚠️ {error}
                    <button onClick={() => setError(null)}>✕</button>
                </div>
            )}

            {/* Stats Section */}
            {stats && (
                <section className="admin-panel__stats">
                    <div className="stat-card">
                        <span className="stat-value">{stats.total_users}</span>
                        <span className="stat-label">Usuarios</span>
                    </div>
                    <div className="stat-card">
                        <span className="stat-value">{stats.active_sessions}</span>
                        <span className="stat-label">Sesiones Activas</span>
                    </div>
                    <div className="stat-card">
                        <span className="stat-value">{stats.total_fragments}</span>
                        <span className="stat-label">Fragmentos</span>
                    </div>
                    <div className="stat-card">
                        <span className="stat-value">{stats.users_by_role.admin || 0}</span>
                        <span className="stat-label">Admins</span>
                    </div>
                </section>
            )}

            <section className="admin-panel__member-sync">
                <div className="member-sync__header">
                    <h3>👥 Sincronizar miembros por organización</h3>
                    <button
                        className="member-sync__action"
                        onClick={handleSyncMembers}
                        disabled={syncingMembers}
                    >
                        {syncingMembers ? "Sincronizando..." : "Sincronizar miembros"}
                    </button>
                </div>
                <div className="member-sync__grid">
                    <div className="member-sync__field">
                        <label htmlFor="member-sync-project">Proyecto</label>
                        <input
                            id="member-sync-project"
                            type="text"
                            value={syncProjectId}
                            onChange={(event) => setSyncProjectId(event.target.value)}
                            placeholder="default"
                        />
                    </div>
                    <div className="member-sync__field">
                        <label htmlFor="member-sync-org">Organización</label>
                        <input
                            id="member-sync-org"
                            type="text"
                            value={syncOrgId}
                            onChange={(event) => setSyncOrgId(event.target.value)}
                            placeholder="default_org"
                        />
                    </div>
                    <div className="member-sync__field">
                        <label htmlFor="member-sync-role">Rol por defecto</label>
                        <select
                            id="member-sync-role"
                            value={syncDefaultRole}
                            onChange={(event) => setSyncDefaultRole(event.target.value)}
                            disabled={syncUseUserRole}
                        >
                            <option value="admin">admin</option>
                            <option value="codificador">codificador</option>
                            <option value="lector">lector</option>
                        </select>
                    </div>
                </div>
                <div className="member-sync__options">
                    <label>
                        <input
                            type="checkbox"
                            checked={syncUseUserRole}
                            onChange={(event) => setSyncUseUserRole(event.target.checked)}
                        />
                        Usar rol del usuario (admin/analyst/viewer)
                    </label>
                    <label>
                        <input
                            type="checkbox"
                            checked={syncIncludeInactive}
                            onChange={(event) => setSyncIncludeInactive(event.target.checked)}
                        />
                        Incluir usuarios inactivos
                    </label>
                </div>
                {syncMessage && <div className="member-sync__message">{syncMessage}</div>}
            </section>

            {/* Neo4j Sync Section */}
            <Neo4jSyncSection key={`neo4j-${panelResetKey}`} />

            {/* Ergonomía operativa: historial de ejecuciones admin (logs JSONL) */}
            <AdminOpsPanel />

            {/* Fase 1.5: Mantenimiento identidad (code_id) */}
            <CodeIdTransitionSection />

            {/* Cleanup Section */}
            <CleanupSection key={`cleanup-${panelResetKey}`} />

            {/* Analysis Section */}
            <AnalysisSection key={`analysis-${panelResetKey}`} />

            {/* Users Table */}
            <section className="admin-panel__users">
                <h3>👥 Usuarios ({users.length})</h3>
                <table className="admin-table">
                    <thead>
                        <tr>
                            <th>Email</th>
                            <th>Nombre</th>
                            <th>Rol</th>
                            <th>Estado</th>
                            <th>Último Login</th>
                            <th>Acciones</th>
                        </tr>
                    </thead>
                    <tbody>
                        {users.map((user) => (
                            <tr key={user.id} className={!user.is_active ? "inactive" : ""}>
                                <td>{user.email}</td>
                                <td>{user.full_name || "—"}</td>
                                <td>
                                    <select
                                        value={user.role}
                                        onChange={(e) => handleRoleChange(user.id, e.target.value)}
                                        disabled={actionLoading === user.id || user.id === currentUserId}
                                    >
                                        <option value="admin">Admin</option>
                                        <option value="analyst">Analyst</option>
                                        <option value="viewer">Viewer</option>
                                    </select>
                                </td>
                                <td>
                                    <button
                                        className={`status-badge ${user.is_active ? "active" : "inactive"}`}
                                        onClick={() => handleToggleActive(user.id, user.is_active)}
                                        disabled={actionLoading === user.id || user.id === currentUserId}
                                    >
                                        {user.is_active ? "✅ Activo" : "⛔ Inactivo"}
                                    </button>
                                </td>
                                <td>
                                    {user.last_login
                                        ? new Date(user.last_login).toLocaleDateString()
                                        : "Nunca"}
                                </td>
                                <td>
                                    {user.id !== currentUserId && (
                                        <button
                                            className="delete-btn"
                                            onClick={() => handleDeleteUser(user.id, user.email)}
                                            disabled={actionLoading === user.id}
                                        >
                                            🗑️
                                        </button>
                                    )}
                                    {user.id === currentUserId && <span className="you-badge">Tú</span>}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </section>
        </div>
    );
}
