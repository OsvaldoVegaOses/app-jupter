import { useEffect, useMemo, useState } from "react";
import type { StageEntry } from "../types";
import { IngestionPanel } from "./IngestionPanel";
import { TranscriptionPanel } from "./TranscriptionPanel";
import { FamiliarizationPanel } from "./FamiliarizationPanel";
import { Stage0PreparationPanel } from "./Stage0PreparationPanel";

type WorkflowStageKey =
  | "preparacion"
  | "ingesta"
  | "familiarizacion"
  | "codificacion"
  | "axial"
  | "nucleo"
  | "transversal"
  | "validacion"
  | "informe";

type WorkflowStatus = "completed" | "pending" | "blocked" | "available";

type ObservedCounts = {
  ingesta?: {
    archivos?: number;
    fragmentos_totales?: number;
    fragmentos_analizables?: number;
  };
  familiarizacion?: {
    entrevistas_revisadas?: number;
    entrevistas_totales?: number;
    porcentaje?: number;
  };
  codificacion?: {
    porcentaje_cobertura?: number;
    fragmentos_codificados?: number;
    fragmentos_sin_codigo?: number;
    codigos_unicos?: number;
    citas?: number;
  };
  axial?: {
    relaciones?: number;
    categorias?: number;
  };
  candidatos?: {
    pendientes?: number;
    validados?: number;
    rechazados?: number;
    total?: number;
  };
};

type DiscoverySummary = {
  recent_runs?: number;
  avg_landing_rate?: number;
};

const WORKFLOW_STAGES: Array<{
  index: number;
  key: WorkflowStageKey;
  icon: string;
  title: string;
}> = [
  { index: 0, key: "preparacion", icon: "📋", title: "Preparación" },
  { index: 1, key: "ingesta", icon: "📥", title: "Ingesta" },
  { index: 2, key: "familiarizacion", icon: "👁️", title: "Familiarización" },
  { index: 3, key: "codificacion", icon: "🏷️", title: "Cod. Abierta" },
  { index: 4, key: "axial", icon: "🔗", title: "Cod. Axial" },
  { index: 5, key: "nucleo", icon: "⭐", title: "Cod. Selectiva" },
  { index: 6, key: "transversal", icon: "📊", title: "Transversal" },
  { index: 7, key: "validacion", icon: "✅", title: "Validación" },
  { index: 8, key: "informe", icon: "📑", title: "Informe Final" },
];

function stageCompleted(entry: StageEntry | undefined): boolean {
  return Boolean(entry?.completed);
}

function computeStatus(args: {
  stageKey: WorkflowStageKey;
  stages: Record<string, StageEntry> | undefined;
  observed?: ObservedCounts | null;
}): WorkflowStatus {
  const { stageKey, stages, observed } = args;

  if (stageKey === "familiarizacion") {
    const ingestaDone = stageCompleted(stages?.ingesta);
    if (!ingestaDone) return "blocked";
    const pct = observed?.familiarizacion?.porcentaje;
    if (typeof pct === "number" && pct >= 100) return "completed";
    // No hay checklist estándar para Familiarización; la tratamos como disponible tras ingesta.
    return "available";
  }

  const completed = stageCompleted(stages?.[stageKey]);
  if (completed) return "completed";

  // Dependencias secuenciales (UI): si el anterior no está completo, mostramos bloqueada.
  const order = WORKFLOW_STAGES.map((s) => s.key);
  const idx = order.indexOf(stageKey);
  if (idx > 0) {
    const prevKey = order[idx - 1];
    if (prevKey === "familiarizacion") {
      // Gate suave: Familiarización no bloquea la codificación.
      // Solo se requiere que Ingesta esté lista.
      if (!stageCompleted(stages?.ingesta)) return "blocked";
    } else {
      if (!stageCompleted(stages?.[prevKey])) return "blocked";
    }
  }

  return "pending";
}

function statusLabel(status: WorkflowStatus): string {
  switch (status) {
    case "completed":
      return "✅ Completada";
    case "blocked":
      return "🔴 Bloqueada";
    case "available":
      return "Disponible";
    case "pending":
    default:
      return "Pendiente";
  }
}

export function WorkflowPanel(props: {
  project: string;
  stages: Record<string, StageEntry> | undefined;
  observed: ObservedCounts | null | undefined;
  discovery?: DiscoverySummary | null;
  disabled?: boolean;
  onTranscriptionCompleted: () => void;
  onIngestionCompleted: () => void;
  onFamiliarizationUpdated?: () => void;
  onNavigateToInvestigation: (tab: "abierta" | "axial" | "selectiva") => void;
  onNavigateToReports: () => void;
}) {
  const {
    project,
    stages,
    observed,
    discovery,
    disabled,
    onTranscriptionCompleted,
    onIngestionCompleted,
    onFamiliarizationUpdated,
    onNavigateToInvestigation,
    onNavigateToReports
  } = props;

  const sidebarMeta = useMemo(() => {
    const meta: Partial<Record<WorkflowStageKey, string>> = {};
    const archivos = observed?.ingesta?.archivos;
    const fragmentos = observed?.ingesta?.fragmentos_totales;
    const analizables = observed?.ingesta?.fragmentos_analizables;
    if (typeof archivos === "number" || typeof fragmentos === "number") {
      meta.ingesta = `${archivos ?? "-"} archivos · ${fragmentos ?? "-"} frags`;
      const rev = observed?.familiarizacion?.entrevistas_revisadas;
      const tot = observed?.familiarizacion?.entrevistas_totales ?? archivos;
      const revText = (typeof rev === "number" && typeof tot === "number") ? `${rev}/${tot} revisadas` : null;
      meta.familiarizacion = [`${archivos ?? "-"} entrevistas`, `${analizables ?? "-"} frags analizables`, revText]
        .filter(Boolean)
        .join(" · ");
    }

    const cobertura = observed?.codificacion?.porcentaje_cobertura;
    const codigos = observed?.codificacion?.codigos_unicos;
    const pendientes = observed?.candidatos?.pendientes;
    if (typeof cobertura === "number" || typeof codigos === "number") {
      const parts = [
        typeof cobertura === "number" ? `Cobertura ${cobertura.toFixed(1)}%` : null,
        typeof codigos === "number" ? `${codigos} códigos` : null,
        typeof pendientes === "number" ? `${pendientes} candidatos pendientes` : null,
      ].filter(Boolean);
      if (parts.length) meta.codificacion = parts.join(" · ");
    }

    const relaciones = observed?.axial?.relaciones;
    const categorias = observed?.axial?.categorias;
    if (typeof relaciones === "number" || typeof categorias === "number") {
      meta.axial = `${relaciones ?? "-"} relaciones · ${categorias ?? "-"} categorías`;
    }

    if (typeof discovery?.avg_landing_rate === "number") {
      meta.codificacion = [meta.codificacion, `Landing ${discovery.avg_landing_rate.toFixed(2)}`].filter(Boolean).join(" · ");
    }

    return meta;
  }, [observed, discovery]);

  const familiarizationBadgeText = useMemo(() => {
    const pct = observed?.familiarizacion?.porcentaje;
    if (typeof pct === "number" && pct > 0 && pct < 100) return `En progreso ${pct.toFixed(1)}%`;
    if (typeof pct === "number" && pct >= 100) return "✅ Completada";
    return null;
  }, [observed]);

  const defaultStage = useMemo<WorkflowStageKey>(() => {
    if (!stages) return "ingesta";
    if (!stageCompleted(stages.ingesta)) return "ingesta";
    if (!stageCompleted(stages.codificacion)) return "familiarizacion";
    if (!stageCompleted(stages.axial)) return "codificacion";
    if (!stageCompleted(stages.nucleo)) return "axial";
    return "informe";
  }, [stages]);

  const [activeStage, setActiveStage] = useState<WorkflowStageKey>(defaultStage);

  useEffect(() => {
    setActiveStage(defaultStage);
  }, [defaultStage, project]);

  const rows = useMemo(() => {
    return WORKFLOW_STAGES.map((stage) => {
      const status = computeStatus({ stageKey: stage.key, stages, observed });
      return {
        ...stage,
        status,
        statusText:
          stage.key === "familiarizacion" && familiarizationBadgeText
            ? familiarizationBadgeText
            : statusLabel(status),
        isActive: stage.key === activeStage,
      };
    });
  }, [stages, activeStage, observed, familiarizationBadgeText]);

  const coverage = observed?.codificacion?.porcentaje_cobertura;

  return (
    <section className="workflow">
      <aside className="workflow__sidebar" aria-label="Flujo de trabajo">
        <h2 className="workflow__title">VISTA 2: Flujo de trabajo</h2>
        <div className="workflow__list" role="list">
          {rows.map((row) => (
            <button
              key={row.key}
              type="button"
              className={row.isActive ? "workflow__item workflow__item--active" : "workflow__item"}
              onClick={() => setActiveStage(row.key)}
              disabled={disabled}
            >
              <span className="workflow__item-index">{row.index}</span>
              <span className="workflow__item-title">
                <span className="workflow__item-title-main">{row.icon} {row.title}</span>
                {sidebarMeta[row.key] && <span className="workflow__item-meta">{sidebarMeta[row.key]}</span>}
              </span>
              <span
                className={
                  row.status === "completed"
                    ? "workflow__badge workflow__badge--ok"
                    : row.status === "blocked"
                      ? "workflow__badge workflow__badge--blocked"
                      : row.isActive
                        ? "workflow__badge workflow__badge--active"
                        : "workflow__badge"
                }
              >
                {row.isActive ? "ACTUAL" : row.statusText}
              </span>
            </button>
          ))}
        </div>

        <div className="workflow__hint">
          La navegación es secuencial y validada. Si una etapa está bloqueada, completa los prerequisitos.
        </div>
      </aside>

      <div className="workflow__content" aria-label="Contenido de etapa">
        {activeStage === "preparacion" && (
          <section className="workflow__stage">
            <header className="workflow__stage-header">
              <h3>ETAPA 0: PREPARACIÓN</h3>
              <p>Estado: <strong>{stageCompleted(stages?.preparacion) ? "✅ Completada" : "Pendiente"}</strong></p>
            </header>

            <Stage0PreparationPanel project={project} />

            <div className="workflow__card">
              <h4>Verificación</h4>
              <p className="workflow__mono">python scripts/healthcheck.py</p>
            </div>
          </section>
        )}

        {activeStage === "ingesta" && (
          <section className="workflow__stage">
            <header className="workflow__stage-header">
              <h3>📥 ETAPA 1: INGESTA</h3>
              <p>
                Estado: <strong>{stageCompleted(stages?.ingesta) ? "✅ Completada" : "Pendiente"}</strong>
              </p>
              {observed?.ingesta && (
                <p className="workflow__metrics">
                  Archivos: <strong>{observed.ingesta.archivos ?? "-"}</strong> · Fragmentos: <strong>{observed.ingesta.fragmentos_totales ?? "-"}</strong>
                </p>
              )}
            </header>

            <TranscriptionPanel
              project={project}
              disabled={Boolean(disabled)}
              onCompleted={onTranscriptionCompleted}
            />

            <IngestionPanel
              project={project}
              disabled={Boolean(disabled)}
              onCompleted={onIngestionCompleted}
            />
          </section>
        )}

        {activeStage === "familiarizacion" && (
          <section className="workflow__stage">
            <header className="workflow__stage-header">
              <h3>👁️ ETAPA 2: FAMILIARIZACIÓN</h3>
              <p>
                Estado: <strong>{stageCompleted(stages?.codificacion) ? "✅ Cerrada (implícita)" : "En progreso"}</strong>
              </p>
              <p className="workflow__hint-inline">
                Revisa fragmentos antes de codificar: navegación por entrevistas, QA del segmentado y memos.
              </p>
            </header>
              <FamiliarizationPanel project={project} onProgressChanged={onFamiliarizationUpdated} />
          </section>
        )}

        {activeStage === "codificacion" && (
          <section className="workflow__stage">
            <header className="workflow__stage-header">
              <h3>🏷️ ETAPA 3: CODIFICACIÓN ABIERTA</h3>
              <p>
                Estado: <strong>{stageCompleted(stages?.codificacion) ? "✅ Completada" : "Pendiente"}</strong>
              </p>
              {typeof coverage === "number" && (
                <p className="workflow__metrics">
                  Cobertura: <strong>{coverage.toFixed(1)}%</strong> · Códigos: <strong>{observed?.codificacion?.codigos_unicos ?? "-"}</strong>
                </p>
              )}
            </header>

            <div className="workflow__card">
              <p>Acción del investigador: asignar códigos a cada fragmento y validar candidatos.</p>
              <button
                type="button"
                className="workflow__cta"
                onClick={() => onNavigateToInvestigation("abierta")}
              >
                Ir a Codificación Abierta
              </button>
            </div>
          </section>
        )}

        {activeStage === "axial" && (
          <section className="workflow__stage">
            <header className="workflow__stage-header">
              <h3>🔗 ETAPA 4: CODIFICACIÓN AXIAL</h3>
              <p>
                Estado: <strong>{stageCompleted(stages?.axial) ? "✅ Completada" : "Pendiente"}</strong>
              </p>
              {observed?.axial && (
                <p className="workflow__metrics">
                  Relaciones: <strong>{observed.axial.relaciones ?? "-"}</strong> · Categorías: <strong>{observed.axial.categorias ?? "-"}</strong>
                </p>
              )}
            </header>

            <div className="workflow__card">
              <p>Estructura relaciones explicables con evidencia y análisis de grafo.</p>
              <button type="button" className="workflow__cta" onClick={() => onNavigateToInvestigation("axial")}>
                Ir a Codificación Axial
              </button>
            </div>
          </section>
        )}

        {activeStage === "nucleo" && (
          <section className="workflow__stage">
            <header className="workflow__stage-header">
              <h3>⭐ ETAPA 5: CODIFICACIÓN SELECTIVA</h3>
              <p>
                Estado: <strong>{stageCompleted(stages?.nucleo) ? "✅ Completada" : "Pendiente"}</strong>
              </p>
            </header>

            <div className="workflow__card">
              <p>Síntesis, núcleo, muestreo teórico y narrativa integrada.</p>
              <button type="button" className="workflow__cta" onClick={() => onNavigateToInvestigation("selectiva")}>
                Ir a Selectiva
              </button>
            </div>
          </section>
        )}

        {(activeStage === "transversal" || activeStage === "validacion" || activeStage === "informe") && (
          <section className="workflow__stage">
            <header className="workflow__stage-header">
              <h3>
                {activeStage === "transversal"
                  ? "📊 ETAPA 6: ANÁLISIS TRANSVERSAL"
                  : activeStage === "validacion"
                    ? "✅ ETAPA 7: VALIDACIÓN"
                    : "📑 ETAPA 8: INFORME FINAL"}
              </h3>
              <p>
                Estado: <strong>{stageCompleted(stages?.[activeStage as string]) ? "✅ Completada" : "Pendiente"}</strong>
              </p>
            </header>
            <div className="workflow__card">
              <p>
                Esta etapa se revisa desde el panel de <strong>Reportes</strong> (comparativos, métricas y exportaciones).
              </p>
              <button type="button" className="workflow__cta" onClick={onNavigateToReports}>
                Ir a Reportes
              </button>
            </div>
          </section>
        )}
      </div>
    </section>
  );
}
