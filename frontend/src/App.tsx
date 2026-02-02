/**
 * @fileoverview Componente principal del dashboard de análisis cualitativo.
 * 
 * App.tsx es el orquestador que integra todos los componentes y gestiona:
 * - Selección y creación de proyectos
 * - Flujo de trabajo por etapas (9 stages de Grounded Theory)
 * - Navegación entre paneles (Ingesta, Codificación, Análisis, Neo4j)
 * - Sistema de notificaciones (toasts)
 * 
 * Etapas del workflow:
 * 1. preparacion - Preparación y reflexividad
 * 2. ingesta - Ingesta y normalización
 * 3. codificacion - Codificación abierta
 * 4. axial - Codificación axial
 * 5. nucleo - Selección del núcleo
 * 6. transversal - Análisis transversal
 * 7. validacion - Validación y saturación
 * 8. informe - Informe integrado
 * 9. analisis - Análisis asistido por LLM
 * 
 * Estado persistido en localStorage:
 * - qualy-dashboard-project: Proyecto seleccionado
 * 
 * @module App
 */

import { Suspense, lazy, useCallback, useEffect, useMemo, useState, useRef } from "react";
import { ManifestSummary } from "./components/ManifestSummary";
import { WorkflowPanel } from "./components/WorkflowPanel";
import { CodingPanel } from "./components/CodingPanel";
import { CodesList } from "./components/CodesList";
import { AnalysisPanel } from "./components/AnalysisPanel";
import { GraphRAGPanel } from "./components/GraphRAGPanel";
import { DiscoveryPanel } from "./components/DiscoveryPanel";
import { LinkPredictionPanel } from "./components/LinkPredictionPanel";
import { ReportsPanel } from "./components/ReportsPanel";
import { InsightsPanel } from "./components/InsightsPanel";
import { SelectiveCodingPanel } from "./components/SelectiveCodingPanel";
import { CodeValidationPanel } from "./components/CodeValidationPanel";
import { HiddenRelationshipsPanel } from "./components/HiddenRelationshipsPanel";
import { Toast, type ToastMessage } from "./components/Toast";
import { BackendStatus } from "./components/BackendStatus";
import { PanelErrorBoundary } from "./components/PanelErrorBoundary";
import { ApiErrorToast } from "./components/ApiErrorToast";
import { SystemHealthDashboard } from "./components/SystemHealthDashboard";
import { LoginPage } from "./components/LoginPage";
import { RegisterPage } from "./components/RegisterPage";
import { ConfirmModal } from "./components/ConfirmModal";
import { AdminPanel } from "./components/AdminPanel";
import { AgentPanel } from "./components/AgentPanel";  // Autonomous Agent
import { EpistemicModeBadge } from "./components/common/EpistemicModeBadge";
import { EpistemicModeSelector } from "./components/common/EpistemicModeSelector";
import { useAuth } from "./context/AuthContext";
import { useProjects } from "./hooks/useProjects";
import { useStatus } from "./hooks/useStatus";
import { useResearchOverview } from "./hooks/useResearchOverview";
import type { StageEntry, EpistemicMode } from "./types";
import "./App.css";
import { apiFetch } from "./services/api";

const Neo4jExplorer = lazy(async () => {
  const module = await import("./components/Neo4jExplorer");
  const comp = (module as any)?.Neo4jExplorer ?? (module as any)?.default;
  if (!comp) {
    return {
      default: () => <div className="app__loader">Error cargando Neo4j Explorer</div>
    } as any;
  }
  return { default: comp } as any;
});

const stageTitles: Array<[string, string]> = [
  ["preparacion", "Preparacion y reflexividad"],
  ["ingesta", "Ingesta y normalizacion"],
  ["codificacion", "Codificacion abierta"],
  ["axial", "Codificacion axial"],
  ["nucleo", "Seleccion del nucleo"],
  ["transversal", "Analisis transversal"],
  ["validacion", "Validacion y saturacion"],
  ["informe", "Informe integrado"]
];

function normaliseStage(entry: StageEntry | undefined, label: string): StageEntry {
  if (!entry) {
    return { label, completed: false };
  }
  return { label, ...entry };
}

const DEFAULT_PROJECT = "default";
const PROJECT_STORAGE_KEY = "qualy-dashboard-project";
const VIEW_STORAGE_KEY = "qualy-dashboard-view";
const INVESTIGATION_VIEW_STORAGE_KEY = "qualy-dashboard-investigation-view";

type AppView = "inicio" | "proceso" | "investigacion" | "reportes" | "admin";
type InvestigationView = "abierta" | "axial" | "selectiva";

function BloomOrExplorer({ project }: { project: string }) {
  const bloomUrl = import.meta.env.VITE_NEO4J_BLOOM_URL as string | undefined;
  const [bloomAvailable, setBloomAvailable] = useState<boolean | null>(null);
  const [forceFallback, setForceFallback] = useState(false);
    const openedTabRef = useRef<Window | null>(null);

  useEffect(() => {
    if (!bloomUrl) {
      setBloomAvailable(false);
      return;
    }
    // Iniciar intento de carga: null = "cargando".
    setBloomAvailable(null);

    // Dev helper: si el iframe no confirma carga en X ms, asumimos fallo y usamos fallback.
    const FALLBACK_TIMEOUT_MS = 5000; // 5s
    const t = window.setTimeout(() => {
      // Sólo forzamos fallback si el estado sigue en 'cargando'
      setBloomAvailable((prev) => {
        if (prev === null) {
          // Intentar abrir Bloom en nueva pestaña como fallback primario.
          try {
            const tab = window.open(bloomUrl, "_blank");
            if (tab) {
              try { tab.opener = null; } catch {}
              openedTabRef.current = tab;
            }
          } catch (e) {
            // ignore
          }
          return false;
        }
        return prev;
      });
    }, FALLBACK_TIMEOUT_MS);

    return () => {
      window.clearTimeout(t);
    };
  }, [bloomUrl]);

  if (!bloomUrl || forceFallback || bloomAvailable === false) {
    return (
      <div className="app__bloom">
        <div className="app__bloom-header">
          <h3 style={{ margin: 0 }}>Neo4j Explorer (fallback)</h3>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            {bloomUrl && (
              <a href={bloomUrl} target="_blank" rel="noreferrer" className="app__bloom-link">
                Abrir Bloom en nueva pestaña
              </a>
            )}
            <button
              type="button"
              className="app__bloom-fallback"
              onClick={() => {
                // If already in fallback, try toggling back to bloom if available
                setForceFallback(true);
              }}
            >
              Usar Neo4j Explorer
            </button>
          </div>
        </div>
        <div className="app__bloom-frame">
          <Suspense fallback={<div className="app__bloom-loading">Cargando Neo4j Explorer…</div>}>
            <Neo4jExplorer project={project} />
          </Suspense>
        </div>
      </div>
    );
  }

  return (
    <div className="app__bloom">
      <div className="app__bloom-header">
        <h3 style={{ margin: 0 }}>Neo4j Bloom</h3>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <a
            href={bloomUrl}
            target="_blank"
            rel="noreferrer"
            className="app__bloom-link"
          >
            Abrir en nueva pestaña
          </a>
          <button
            type="button"
            className="app__bloom-fallback"
            onClick={() => setForceFallback(true)}
          >
            Usar fallback React
          </button>
        </div>
      </div>
      <div className="app__bloom-frame">
        <iframe
          src={bloomUrl}
          title="Neo4j Bloom"
          onLoad={() => setBloomAvailable(true)}
          onError={() => {
            setBloomAvailable(false);
            // También abrir en nueva pestaña si el iframe falla
            try {
              const tab = window.open(bloomUrl, "_blank");
              if (tab) { try { tab.opener = null; } catch {} openedTabRef.current = tab; }
            } catch (e) {
              // ignore
            }
          }}
        />
        {bloomAvailable === null && (
          <div className="app__bloom-loading">Cargando Bloom…</div>
        )}
      </div>
    </div>
  );
}

export default function App() {
  // Auth state
  const { isAuthenticated, isLoading: authLoading, user, logout } = useAuth();
  const [authView, setAuthView] = useState<"login" | "register">("login");

  // If not authenticated, show login/register
  if (authLoading) {
    return (
      <div className="app app--loading">
        <div className="app__loader">Cargando...</div>
      </div>
    );
  }

  if (!isAuthenticated) {
    if (authView === "register") {
      return <RegisterPage onSwitchToLogin={() => setAuthView("login")} />;
    }
    return <LoginPage onSwitchToRegister={() => setAuthView("register")} />;
  }

  // Authenticated - render dashboard
  return <AuthenticatedApp user={user} onLogout={logout} />;
}

function AuthenticatedApp({ user, onLogout }: { user: any; onLogout: () => void }) {
  const { state: projectsState, create: createProject, update: updateProject, deleteProject, exportProject } = useProjects();
  const userRoles = Array.isArray(user?.roles) ? user.roles : (user?.role ? [user.role] : []);
  const hasRole = (role: string) => userRoles.some((r: string) => String(r).toLowerCase() === role);
  const isAdmin = hasRole("admin") || hasRole("superadmin");
  const canCreateProjects = isAdmin || hasRole("analyst");
  const canEditProjects = isAdmin || hasRole("analyst");
  const [view, setView] = useState<AppView>(() => {
    if (typeof window !== "undefined") {
      const stored = window.localStorage.getItem(VIEW_STORAGE_KEY) as AppView | null;
      if (stored) {
        return stored;
      }
    }
    return "inicio";
  });

  const [investigationView, setInvestigationView] = useState<InvestigationView>(() => {
    if (typeof window !== "undefined") {
      const stored = window.localStorage.getItem(INVESTIGATION_VIEW_STORAGE_KEY) as InvestigationView | null;
      if (stored === "abierta" || stored === "axial" || stored === "selectiva") {
        return stored;
      }
    }
    return "abierta";
  });
  const [selectedProject, setSelectedProject] = useState<string>(() => {
    if (typeof window !== "undefined") {
      return window.localStorage.getItem(PROJECT_STORAGE_KEY) || DEFAULT_PROJECT;
    }
    return DEFAULT_PROJECT;
  });
  const [actionError, setActionError] = useState<string | null>(null);
  const [completingStage, setCompletingStage] = useState<string | null>(null);
  const [creatingProject, setCreatingProject] = useState(false);
  const [formName, setFormName] = useState("");
  const [formDescription, setFormDescription] = useState("");
  const [formEpistemicMode, setFormEpistemicMode] = useState<EpistemicMode>("constructivist");
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [updatingProject, setUpdatingProject] = useState(false);
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const [codingRefreshKey, setCodingRefreshKey] = useState(0);
  const [deletingProject, setDeletingProject] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [backupBeforeDelete, setBackupBeforeDelete] = useState(true);
  const [showDeleteAccountModal, setShowDeleteAccountModal] = useState(false);
  const [deletingAccount, setDeletingAccount] = useState(false);
  const [overviewRefreshKey, setOverviewRefreshKey] = useState(0);
  const [panoramaArchivo, setPanoramaArchivo] = useState<string | null>(null);

  const addToast = useCallback((type: ToastMessage["type"], message: string) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    setToasts((prev) => [...prev, { id, type, message }]);
  }, []);

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  useEffect(() => {
    if (projectsState.loading) {
      return;
    }
    if (!projectsState.items.length) {
      setSelectedProject(DEFAULT_PROJECT);
      return;
    }
    if (!projectsState.items.find((project) => project.id === selectedProject)) {
      setSelectedProject(projectsState.items[0].id);
    }
  }, [projectsState, selectedProject]);

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(PROJECT_STORAGE_KEY, selectedProject);
    }
  }, [selectedProject]);

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(VIEW_STORAGE_KEY, view);
    }
  }, [view]);

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(INVESTIGATION_VIEW_STORAGE_KEY, investigationView);
    }
  }, [investigationView]);

  useEffect(() => {
    if (!isAdmin && view === "admin") {
      setView("inicio");
    }
  }, [isAdmin, view]);

  const activeProject = useMemo(
    () => projectsState.items.find((project) => project.id === selectedProject),
    [projectsState.items, selectedProject]
  );

  const [statusState, reloadStatus] = useStatus(selectedProject);
  const researchOverviewState = useResearchOverview(selectedProject, overviewRefreshKey);

  const stageCards = useMemo(() => {
    const entries = statusState.data?.stages || {};
    return stageTitles.map(([key, shortLabel], index) => ({
      key,
      index: index + 1,
      entry: normaliseStage(entries[key], shortLabel)
    }));
  }, [statusState.data]);

  const completedStages = useMemo(
    () => stageCards.filter((item) => item.entry.completed).length,
    [stageCards]
  );

  const handleRefresh = async () => {
    setActionError(null);
    await reloadStatus();
    setOverviewRefreshKey((prev) => prev + 1);
  };

  const navigateFromPanorama = useCallback(
    (action: any | null | undefined) => {
      if (!action) return;
      const targetView = String(action.view || "").trim();
      const targetSub = (action.subview ? String(action.subview) : "") as any;
      const params = (action.params || {}) as Record<string, any>;
      const archivo = (params.archivo ? String(params.archivo) : "").trim();

      if (targetView === "investigacion") {
        setView("investigacion");
        if (targetSub === "axial" || targetSub === "selectiva" || targetSub === "abierta") {
          setInvestigationView(targetSub);
        } else {
          setInvestigationView("abierta");
        }
        setPanoramaArchivo(archivo || null);
        return;
      }

      if (targetView === "proceso") {
        setView("proceso");
        setPanoramaArchivo(null);
        return;
      }

      if (targetView === "reportes") {
        setView("reportes");
        setPanoramaArchivo(null);
        return;
      }
    },
    [setView, setInvestigationView]
  );

  const handleCreateProject = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!formName.trim()) {
      setActionError("Debes definir un nombre para el proyecto.");
      return;
    }
    setActionError(null);
    setCreatingProject(true);
    try {
      const result = await createProject({ 
        name: formName.trim(), 
        description: formDescription,
        epistemic_mode: formEpistemicMode
      });
      if (result) {
        setFormName("");
        setFormDescription("");
        setFormEpistemicMode("constructivist");
        addToast("success", `Proyecto "${result.name || result.id}" creado exitosamente`);
        // Small delay to ensure state is fully updated before switching
        await new Promise((resolve) => setTimeout(resolve, 100));
        setSelectedProject(result.id);
      } else {
        addToast("error", "No se pudo crear el proyecto");
      }
    } catch (error) {
      addToast("error", error instanceof Error ? error.message : "Error al crear proyecto");
    } finally {
      setCreatingProject(false);
    }
  };

  const handleUpdateProject = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!selectedProject) {
      setActionError("No hay proyecto seleccionado.");
      return;
    }
    if (!editName.trim()) {
      setActionError("Debes definir un nombre para el proyecto.");
      return;
    }
    setActionError(null);
    setUpdatingProject(true);
    try {
      const result = await updateProject(selectedProject, {
        name: editName.trim(),
        description: editDescription.trim() || undefined
      });
      if (result) {
        addToast("success", `Proyecto actualizado: ${result.name || result.id}`);
      } else {
        addToast("error", "No se pudo actualizar el proyecto");
      }
    } catch (error) {
      addToast("error", error instanceof Error ? error.message : "Error actualizando proyecto");
    } finally {
      setUpdatingProject(false);
    }
  };

  const handleCompleteStage = async (stageKey: string) => {
    setActionError(null);
    setCompletingStage(stageKey);
    try {
      await apiFetch(
        `/api/projects/${encodeURIComponent(selectedProject)}/stages/${encodeURIComponent(stageKey)}/complete`,
        {
          method: "POST",
          body: JSON.stringify({})
        }
      );
      await reloadStatus();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "No se pudo marcar la etapa.");
    } finally {
      setCompletingStage(null);
    }
  };

  const handleIngestionCompleted = async () => {
    await reloadStatus();
    setCodingRefreshKey((prev) => prev + 1);
    addToast("success", "Ingesta completada exitosamente");
  };

  useEffect(() => {
    if (activeProject) {
      setEditName(activeProject.name || activeProject.id || "");
      setEditDescription(activeProject.description || "");
    }
  }, [activeProject]);

  return (
    <div className="app">
      <header className="app__header">
        <div>
          <h1>Dashboard del ciclo cualitativo</h1>
          <p>
            Define proyectos, avanza etapa por etapa y revisa los artefactos consolidados del
            pipeline.
          </p>
          <div className="app__header-project">
            <span className="app__header-label">Proyecto activo</span>
            <div>
              <strong>{activeProject?.name || selectedProject || "Sin proyecto"}</strong>
              {selectedProject && <span className="app__header-meta">ID: {selectedProject}</span>}
            </div>
            {activeProject?.description && (
              <small className="app__header-description">{activeProject.description}</small>
            )}
          </div>
        </div>
        <div className="app__actions">
          <div className="app__user-info">
            <span className="app__user-email">{user?.email}</span>
            <span className="app__user-org">🏢 {user?.org_id}</span>
            <button onClick={onLogout} className="app__logout-btn" title="Cerrar sesión">
              🚪 Salir
            </button>
            <button
              onClick={() => setShowDeleteAccountModal(true)}
              className="app__delete-account-btn"
              title="Eliminar mi cuenta"
              disabled={deletingAccount}
            >
              🗑️
            </button>
          </div>
          <BackendStatus />
          <button onClick={handleRefresh} disabled={statusState.loading}>
            {statusState.loading ? "Actualizando..." : "Refrescar estado"}
          </button>
        </div>
      </header>

      <nav className="app__nav" aria-label="Navegación principal">
        <button
          type="button"
          className={view === "inicio" ? "app__nav-btn app__nav-btn--active" : "app__nav-btn"}
          onClick={() => setView("inicio")}
        >
          Inicio
        </button>
        <button
          type="button"
          className={view === "proceso" ? "app__nav-btn app__nav-btn--active" : "app__nav-btn"}
          onClick={() => setView("proceso")}
        >
          Flujo de trabajo
        </button>
        <button
          type="button"
          className={view === "investigacion" ? "app__nav-btn app__nav-btn--active" : "app__nav-btn"}
          onClick={() => setView("investigacion")}
        >
          Investigación
        </button>
        <button
          type="button"
          className={view === "reportes" ? "app__nav-btn app__nav-btn--active" : "app__nav-btn"}
          onClick={() => setView("reportes")}
        >
          Reportes
        </button>
        {isAdmin && (
          <button
            type="button"
            className={view === "admin" ? "app__nav-btn app__nav-btn--active" : "app__nav-btn"}
            onClick={() => setView("admin")}
          >
            Administración
          </button>
        )}
      </nav>

      {isAdmin && view === "admin" && (
        <SystemHealthDashboard autoRefreshSeconds={120} defaultCollapsed={true} />
      )}

      <section className="app__projects">
        <div className="app__project-card">
          <h2 style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
            {activeProject?.name || "Proyecto sin titulo"}
            <EpistemicModeBadge mode={activeProject?.epistemic_mode} size="sm" />
          </h2>
          <p>{activeProject?.description || "Describe el alcance investigativo del proyecto."}</p>
          <dl>
            <div>
              <dt>Identificador</dt>
              <dd>{selectedProject}</dd>
            </div>
            {activeProject?.created_at && (
              <div>
                <dt>Creado</dt>
                <dd>{activeProject.created_at}</dd>
              </div>
            )}
            <div>
              <dt>Etapas completadas</dt>
              <dd>
                {completedStages} / {stageCards.length}
              </dd>
            </div>
          </dl>
        </div>
        <div className="app__project-controls">
          <div className="app__selector">
            <label htmlFor="project-select">Proyecto activo</label>
            <select
              id="project-select"
              value={selectedProject}
              onChange={(event) => setSelectedProject(event.target.value)}
              disabled={projectsState.loading}
            >
              {projectsState.items.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name || project.id}
                </option>
              ))}
              {!projectsState.items.length && <option value={DEFAULT_PROJECT}>default</option>}
            </select>
            {isAdmin && view === "admin" && (
              <button
                type="button"
                className="app__delete-btn"
                disabled={projectsState.loading || deletingProject || selectedProject === DEFAULT_PROJECT}
                onClick={() => setShowDeleteModal(true)}
              >
                {deletingProject ? "Eliminando..." : "🗑️ Eliminar"}
              </button>
            )}
          </div>
            {canCreateProjects && (
            <form className="app__form" onSubmit={handleCreateProject}>
              <div>
                <label htmlFor="project-name">Nuevo proyecto</label>
                <input
                  id="project-name"
                  type="text"
                  value={formName}
                  onChange={(event) => setFormName(event.target.value)}
                  placeholder="Nombre descriptivo"
                />
              </div>
              <div>
                <label htmlFor="project-description">Descripcion</label>
                <input
                  id="project-description"
                  type="text"
                  value={formDescription}
                  onChange={(event) => setFormDescription(event.target.value)}
                  placeholder="Opcional"
                />
              </div>
              <div>
                <label>Modo epistemologico</label>
                <EpistemicModeSelector
                  value={formEpistemicMode}
                  onChange={setFormEpistemicMode}
                  compact={false}
                />
              </div>
              <button type="submit" disabled={projectsState.loading || creatingProject}>
                {creatingProject ? "Creando..." : "Crear proyecto"}
              </button>
            </form>
          )}
          {canEditProjects && activeProject && (
            <form className="app__form" onSubmit={handleUpdateProject}>
              <div>
                <label htmlFor="project-edit-name">Renombrar proyecto</label>
                <input
                  id="project-edit-name"
                  type="text"
                  value={editName}
                  onChange={(event) => setEditName(event.target.value)}
                  placeholder="Nombre del proyecto"
                />
              </div>
              <div>
                <label htmlFor="project-edit-description">Descripcion</label>
                <input
                  id="project-edit-description"
                  type="text"
                  value={editDescription}
                  onChange={(event) => setEditDescription(event.target.value)}
                  placeholder="Opcional"
                />
              </div>
              <button type="submit" disabled={projectsState.loading || updatingProject}>
                {updatingProject ? "Actualizando..." : "Actualizar proyecto"}
              </button>
            </form>
          )}
        </div>
      </section>

      {projectsState.error && (
        <div className="app__error">
          <strong>No fue posible cargar los proyectos.</strong>
          <span>{projectsState.error}</span>
        </div>
      )}

      {statusState.error && (
        <div className="app__error">
          <strong>No fue posible cargar el estado.</strong>
          <span>{statusState.error}</span>
          <span>Confirma que `python main.py status --json --no-update` funciona en la terminal.</span>
        </div>
      )}

      {actionError && (
        <div className="app__error">
          <strong>Accion fallida.</strong>
          <span>{actionError}</span>
        </div>
      )}

      <main className="app__layout">
        <section className="app__primary">
          {view === "inicio" && (
            <section className="app__overview">
              <h2>VISTA 1: Panorama del proyecto</h2>
              <p className="app__hint">
                Inicio orientado a acción: indicadores clave + recomendación concreta.
              </p>

              {researchOverviewState.loading && <div className="app__loader">Cargando resumen...</div>}

              {researchOverviewState.error && (
                <div className="app__error">
                  <strong>No fue posible cargar el resumen.</strong>
                  <span>{researchOverviewState.error}</span>
                </div>
              )}

              {researchOverviewState.data?.panorama?.primary_action ? (
                <div className="app__project-card">
                  <h3>
                    🎯 Proyecto: {researchOverviewState.data.panorama.project}
                  </h3>
                  <p className="technical-detail" style={{ marginTop: 6 }}>
                    Etapa actual: {researchOverviewState.data.panorama.current_stage?.label ?? "-"}
                  </p>

                  <dl style={{ marginTop: 12 }}>
                    <div>
                      <dt>Cobertura (Etapa 3)</dt>
                      <dd>
                        {researchOverviewState.data.panorama.signals?.coverage_percent ?? "-"}%
                      </dd>
                    </div>
                    <div>
                      <dt>Pendientes</dt>
                      <dd>
                        {researchOverviewState.data.panorama.signals?.pending_in_recommended != null
                          ? `${researchOverviewState.data.panorama.signals.pending_in_recommended} (entrevista sugerida)`
                          : "-"}
                        {researchOverviewState.data.panorama.signals?.pending_total != null
                          ? ` · ${researchOverviewState.data.panorama.signals.pending_total} (total)`
                          : ""}
                      </dd>
                    </div>
                    <div>
                      <dt>Candidatos</dt>
                      <dd>
                        {researchOverviewState.data.panorama.signals?.candidates_pending != null
                          ? `${researchOverviewState.data.panorama.signals.candidates_pending} pendientes`
                          : "-"}
                      </dd>
                    </div>
                    <div>
                      <dt>Saturación</dt>
                      <dd>
                        {researchOverviewState.data.panorama.saturation?.saturacion_alcanzada
                          ? "Plateau alcanzado"
                          : "En progreso"}
                      </dd>
                    </div>
                  </dl>

                  {researchOverviewState.data.panorama.axial_gate?.status === "locked" ? (
                    <div className="critical-info" style={{ marginTop: 14 }}>
                      <strong>Axial (Etapa 4): bloqueado</strong>
                      {researchOverviewState.data.panorama.axial_gate.reasons?.length ? (
                        <ul style={{ marginTop: 8 }}>
                          {researchOverviewState.data.panorama.axial_gate.reasons.map((r: string, idx: number) => (
                            <li key={idx}>{r}</li>
                          ))}
                        </ul>
                      ) : null}
                      {researchOverviewState.data.panorama.axial_gate.unlock_hint ? (
                        <p style={{ marginTop: 8 }}>
                          <strong>Para desbloquear:</strong> {researchOverviewState.data.panorama.axial_gate.unlock_hint}
                        </p>
                      ) : null}
                      <p className="technical-detail" style={{ marginTop: 8 }}>
                        Regla aplicada: {researchOverviewState.data.panorama.axial_gate.policy_used ?? "-"}
                      </p>
                    </div>
                  ) : (
                    <div className="app__info" style={{ marginTop: 14 }}>
                      <strong>Axial (Etapa 4): listo</strong>
                      <span className="technical-detail" style={{ marginLeft: 8 }}>
                        Regla aplicada: {researchOverviewState.data.panorama.axial_gate?.policy_used ?? "-"}
                      </span>
                    </div>
                  )}

                  <div style={{ marginTop: 14, display: "flex", gap: 10, flexWrap: "wrap" }}>
                    <button
                      type="button"
                      className="primary-action"
                      onClick={() => navigateFromPanorama(researchOverviewState.data?.panorama?.primary_action)}
                    >
                      {researchOverviewState.data.panorama.primary_action.label}
                    </button>
                    <button type="button" onClick={() => setView("proceso")}>Ver detalle</button>
                  </div>

                  {researchOverviewState.data.panorama.primary_action.reason ? (
                    <p className="technical-detail" style={{ marginTop: 8 }}>
                      {researchOverviewState.data.panorama.primary_action.reason}
                    </p>
                  ) : null}

                  {researchOverviewState.data.panorama.secondary_actions?.length ? (
                    <details style={{ marginTop: 12 }}>
                      <summary>Otras acciones sugeridas</summary>
                      <div style={{ marginTop: 10, display: "flex", gap: 10, flexWrap: "wrap" }}>
                        {researchOverviewState.data.panorama.secondary_actions.map((a: any) => (
                          <button key={a.id} type="button" onClick={() => navigateFromPanorama(a)}>
                            {a.label}
                          </button>
                        ))}
                      </div>
                    </details>
                  ) : null}
                </div>
              ) : null}

              {researchOverviewState.data?.warnings?.length ? (
                <div className="app__warning">
                  <strong>Alertas</strong>
                  <ul>
                    {researchOverviewState.data.warnings.map((w, idx) => (
                      <li key={idx}>{w}</li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {researchOverviewState.data?.discovery && (
                <div className="app__project-card">
                  <h3>Discovery (reciente)</h3>
                  <dl>
                    <div>
                      <dt>Iteraciones (30)</dt>
                      <dd>{researchOverviewState.data.discovery.recent_runs ?? "-"}</dd>
                    </div>
                    <div>
                      <dt>Landing rate promedio</dt>
                      <dd>
                        {researchOverviewState.data.discovery.avg_landing_rate ?? "-"}
                      </dd>
                    </div>
                  </dl>
                </div>
              )}
            </section>
          )}

          {view === "proceso" && (
            <>
              <WorkflowPanel
                project={selectedProject}
                stages={statusState.data?.stages}
                observed={researchOverviewState.data?.observed}
                discovery={researchOverviewState.data?.discovery}
                disabled={projectsState.loading || statusState.loading}
                onTranscriptionCompleted={() => {
                  reloadStatus();
                  addToast("success", "Transcripción completada exitosamente");
                }}
                onIngestionCompleted={handleIngestionCompleted}
                onFamiliarizationUpdated={() => setOverviewRefreshKey((prev) => prev + 1)}
                onNavigateToInvestigation={(tab) => {
                  setView("investigacion");
                  setInvestigationView(tab);
                }}
                onNavigateToReports={() => setView("reportes")}
              />
            </>
          )}

          {view === "investigacion" && (
            <>
              <nav className="app__subnav" aria-label="Investigación">
                <button
                  type="button"
                  className={
                    investigationView === "abierta" ? "app__nav-btn app__nav-btn--active" : "app__nav-btn"
                  }
                  onClick={() => setInvestigationView("abierta")}
                >
                  Codificación abierta
                </button>
                <button
                  type="button"
                  className={
                    investigationView === "axial" ? "app__nav-btn app__nav-btn--active" : "app__nav-btn"
                  }
                  onClick={() => setInvestigationView("axial")}
                >
                  Codificación axial
                </button>
                <button
                  type="button"
                  className={
                    investigationView === "selectiva" ? "app__nav-btn app__nav-btn--active" : "app__nav-btn"
                  }
                  onClick={() => setInvestigationView("selectiva")}
                >
                  Codificación selectiva
                </button>
              </nav>

              {investigationView === "abierta" && (
                <>
                  {/* Codificación abierta: producción de códigos + trazabilidad + validación */}
                  <DiscoveryPanel project={selectedProject} />

                  <div className="app__coding-wrapper">
                    <CodingPanel
                      key={selectedProject}
                      project={selectedProject}
                      refreshKey={codingRefreshKey}
                      initialArchivo={panoramaArchivo}
                    />
                    <aside className="app__coding-sidebar">
                      <ManifestSummary manifest={statusState.data?.manifest} />
                      <section className="app__state-path">
                        <h2>Archivo de estado</h2>
                        <p>{statusState.data?.state_path ?? `metadata/projects/${selectedProject}.json`}</p>
                        <p className="app__hint">
                          Ejecuta `python main.py status --project {selectedProject}` para refrescar.
                        </p>
                      </section>
                    </aside>
                  </div>

                  <CodesList project={selectedProject} refreshKey={codingRefreshKey} />
                  <CodeValidationPanel project={selectedProject} />
                </>
              )}

              {investigationView === "axial" && (
                <>
                  {/* Codificación axial: estructura relacional y validación de relaciones */}
                  <LinkPredictionPanel project={selectedProject} />
                  <HiddenRelationshipsPanel project={selectedProject} />
                  <BloomOrExplorer project={selectedProject} />
                </>
              )}

              {investigationView === "selectiva" && (
                <>
                  {/* Codificación selectiva: síntesis, núcleo, muestreo teórico y narrativa */}
                  <SelectiveCodingPanel project={selectedProject} />
                  <AnalysisPanel project={selectedProject} refreshKey={codingRefreshKey} />
                  <GraphRAGPanel project={selectedProject} />
                  <InsightsPanel project={selectedProject} />
                  <AgentPanel project={selectedProject} />
                </>
              )}
            </>
          )}

          {view === "reportes" && (
            <ReportsPanel project={selectedProject} />
          )}

          {view === "admin" && isAdmin && (
            <>
              <AdminPanel currentUserId={user?.id || ""} />
            </>
          )}
        </section>
      </main>

      <Toast messages={toasts} onDismiss={dismissToast} />
      <ApiErrorToast />

      <ConfirmModal
        isOpen={showDeleteModal}
        title={`Eliminar proyecto "${selectedProject}"`}
        message="Esta acción eliminará permanentemente todos los datos asociados al proyecto. No se puede deshacer."
        warningItems={[
          "Todas las entrevistas y fragmentos",
          "Códigos y categorías asignadas",
          "Análisis y reportes generados",
          "Notas y archivos del proyecto",
        ]}
        confirmText="Eliminar permanentemente"
        cancelText="Cancelar"
        confirmVariant="danger"
        onCancel={() => setShowDeleteModal(false)}
        onConfirm={async () => {
          setShowDeleteModal(false);
          setDeletingProject(true);
          try {
            // Download backup first if checkbox is checked
            if (backupBeforeDelete) {
              addToast("info", "Descargando backup...");
              const exported = await exportProject(selectedProject);
              if (!exported) {
                addToast("error", "Error al descargar backup, cancelando eliminación");
                return;
              }
              addToast("success", "Backup descargado");
            }
            // Then delete
            const success = await deleteProject(selectedProject);
            if (success) {
              addToast("success", `Proyecto "${selectedProject}" eliminado`);
              setSelectedProject(projectsState.items[0]?.id || DEFAULT_PROJECT);
            } else {
              addToast("error", "Error al eliminar proyecto");
            }
          } finally {
            setDeletingProject(false);
          }
        }}
      >
        <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginTop: "1rem", cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={backupBeforeDelete}
            onChange={(e) => setBackupBeforeDelete(e.target.checked)}
          />
          <span>📦 Descargar backup antes de eliminar</span>
        </label>
      </ConfirmModal>

      {/* Modal para eliminar cuenta propia */}
      <ConfirmModal
        isOpen={showDeleteAccountModal}
        title="Eliminar mi cuenta"
        message="Esta acción eliminará permanentemente tu cuenta y todos tus datos. No podrás recuperar el acceso."
        warningItems={[
          "Tu cuenta de usuario será eliminada",
          "Todas tus sesiones serán revocadas",
          "No podrás acceder nuevamente con este email",
        ]}
        confirmText="Eliminar mi cuenta"
        cancelText="Cancelar"
        confirmVariant="danger"
        onCancel={() => setShowDeleteAccountModal(false)}
        onConfirm={async () => {
          setShowDeleteAccountModal(false);
          setDeletingAccount(true);
          try {
            await apiFetch("/api/auth/me/delete", { method: "POST" });
            addToast("success", "Tu cuenta ha sido eliminada");
            // Logout after account deletion
            onLogout();
          } catch (err) {
            addToast("error", err instanceof Error ? err.message : "Error eliminando cuenta");
          } finally {
            setDeletingAccount(false);
          }
        }}
      />
    </div>
  );
}
