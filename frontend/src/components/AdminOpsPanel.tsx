/**
 * Panel de Operaciones Admin (ergonomía cognitiva y operativa).
 *
 * Objetivo: reducir fricción post-ejecución sin abrir carpetas/grepear logs.
 * Fuente: endpoints /api/admin/ops/* (parsean logs JSONL por sesión/proyecto).
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  adminOpsLog,
  adminOpsRecent,
  adminPostJson,
  codeIdStatus,
  ontologyFreezeStatus,
  type AdminOpsFilters,
  type AdminOpsOutcome,
  type AdminOpsRun,
} from "../services/api";
import "./AdminOpsPanel.css";

const PROJECT_STORAGE_KEY = "qualy-dashboard-project";

function fmtTs(ts?: string): string {
  if (!ts) return "—";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleString();
}

function shortId(value?: string, n = 8): string {
  if (!value) return "—";
  return value.length <= n ? value : `${value.slice(0, n)}…`;
}

function opLabel(run: AdminOpsRun): string {
  const ev = run.event || "";
  if (ev.includes("code_id.backfill")) return "code-id backfill";
  if (ev.includes("code_id.repair")) return "code-id repair";
  if (run.path) return run.path;
  return ev || "(sin evento)";
}

function opParams(run: AdminOpsRun): string {
  const parts: string[] = [];
  if (typeof run.dry_run === "boolean") parts.push(`dry_run=${run.dry_run}`);
  if (typeof run.confirm === "boolean") parts.push(`confirm=${run.confirm}`);
  if (typeof run.batch_size === "number") parts.push(`batch=${run.batch_size}`);
  if (run.mode) parts.push(`mode=${run.mode}`);
  if (run.action) parts.push(`action=${run.action}`);
  return parts.length ? parts.join(" · ") : "—";
}

function statusBadge(run: AdminOpsRun): { text: string; cls: string } {
  const code = run.status_code;
  if (run.is_error) return { text: "Error", cls: "admin-ops__badge admin-ops__badge--error" };
  if (typeof code === "number") {
    if (code >= 200 && code < 300) return { text: String(code), cls: "admin-ops__badge admin-ops__badge--ok" };
    if (code >= 400) return { text: String(code), cls: "admin-ops__badge admin-ops__badge--error" };
  }
  return { text: "—", cls: "admin-ops__badge" };
}

function getUpdatedCount(run: AdminOpsRun): number | null {
  const u: any = (run as any).updated;
  if (typeof u === "number" && Number.isFinite(u)) return u;
  if (u && typeof u === "object") {
    const candidates = ["updated", "rows_updated", "rows", "affected", "count"];
    for (const k of candidates) {
      const v = (u as any)[k];
      if (typeof v === "number" && Number.isFinite(v)) return v;
    }
  }
  return null;
}

function outcomeEnum(run: AdminOpsRun): AdminOpsOutcome {
  const code = run.status_code;
  const method = String((run as any).http_method || "").toUpperCase();
  const updatedCount = getUpdatedCount(run);

  if (run.is_error || (typeof code === "number" && code >= 400)) return "ERROR";
  if (typeof code === "number" && code >= 200 && code < 300) {
    if (method === "POST" && updatedCount === 0) return "NOOP";
    return "OK";
  }
  return "UNKNOWN";
}

function outcomeLabel(run: AdminOpsRun): string {
  const out = outcomeEnum(run);
  const code = run.status_code;
  return typeof code === "number" ? `${out} (${code})` : out;
}

function safeJson(value: any): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function AdminOpsPanel(): JSX.Element {
  const [project, setProject] = useState(() => localStorage.getItem(PROJECT_STORAGE_KEY) || "default");

  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === PROJECT_STORAGE_KEY) {
        setProject(localStorage.getItem(PROJECT_STORAGE_KEY) || "default");
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const [runs, setRuns] = useState<AdminOpsRun[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filters (log-only)
  const [kind, setKind] = useState<AdminOpsFilters["kind"]>("all");
  const [op, setOp] = useState<AdminOpsFilters["op"]>("all");
  const [intent, setIntent] = useState<AdminOpsFilters["intent"]>("all");
  const [range, setRange] = useState<"24h" | "7d" | "custom">("24h");
  const [sinceIso, setSinceIso] = useState<string>("");
  const [untilIso, setUntilIso] = useState<string>("");

  const [selected, setSelected] = useState<AdminOpsRun | null>(null);
  const [logRecords, setLogRecords] = useState<any[] | null>(null);
  const [logLoading, setLogLoading] = useState(false);
  const [logError, setLogError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const now = new Date();
      let since: string | undefined;
      let until: string | undefined;

      if (range === "24h") {
        const d = new Date(now.getTime() - 24 * 60 * 60 * 1000);
        since = d.toISOString();
        until = now.toISOString();
      } else if (range === "7d") {
        const d = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
        since = d.toISOString();
        until = now.toISOString();
      } else {
        since = sinceIso.trim() ? sinceIso.trim() : undefined;
        until = untilIso.trim() ? untilIso.trim() : undefined;
      }

      const res = await adminOpsRecent(project, 80, {
        kind,
        op,
        intent,
        since,
        until,
      });
      setRuns(Array.isArray((res as any).runs) ? (res as any).runs : []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error cargando ejecuciones");
    } finally {
      setLoading(false);
    }
  }, [project, kind, op, intent, range, sinceIso, untilIso]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Re-run modal
  const [rerunOpen, setRerunOpen] = useState(false);
  const [rerunRun, setRerunRun] = useState<AdminOpsRun | null>(null);
  const [rerunPayload, setRerunPayload] = useState<any>(null);
  const [rerunEndpoint, setRerunEndpoint] = useState<string>("");
  const [rerunDangerAck, setRerunDangerAck] = useState(false);
  const [rerunTyped, setRerunTyped] = useState("");
  const [rerunExecLoading, setRerunExecLoading] = useState(false);
  const [rerunExecError, setRerunExecError] = useState<string | null>(null);
  const [rerunPrecheck, setRerunPrecheck] = useState<{
    freeze?: boolean;
    axial_ready?: boolean;
    blocking_reasons?: string[];
    supported?: boolean;
  } | null>(null);

  const openRerun = useCallback(async (run: AdminOpsRun) => {
    setRerunExecError(null);
    setRerunDangerAck(false);
    setRerunTyped("");
    setRerunPrecheck(null);

    // Rebuild payload from historical run (log-derived, not live state)
    const path = run.path || "";

    if (path.endsWith("/api/admin/code-id/backfill") || (run.event || "").includes("code_id.backfill")) {
      setRerunEndpoint(`/api/admin/code-id/backfill?project=${encodeURIComponent(project)}`);
      setRerunPayload({
        mode: run.mode || "all",
        dry_run: run.dry_run ?? true,
        confirm: run.confirm ?? false,
        batch_size: run.batch_size ?? 500,
      });
    } else if (path.endsWith("/api/admin/code-id/repair") || (run.event || "").includes("code_id.repair")) {
      setRerunEndpoint(`/api/admin/code-id/repair?project=${encodeURIComponent(project)}`);
      setRerunPayload({
        action: run.action || "derive_id_from_text",
        dry_run: run.dry_run ?? true,
        confirm: run.confirm ?? false,
        batch_size: run.batch_size ?? 1000,
      });
    } else {
      setRerunEndpoint("");
      setRerunPayload(null);
      setRerunExecError("Esta ejecución no es re-ejecutable desde el panel (solo code-id backfill/repair). ");
    }

    setRerunRun(run);
    setRerunOpen(true);

    // Prechecks are live reads (still safe) used only for warnings.
    try {
      const [freeze, status] = await Promise.all([ontologyFreezeStatus(project), codeIdStatus(project)]);
      setRerunPrecheck({
        freeze: Boolean((freeze as any)?.is_frozen),
        axial_ready: Boolean((status as any)?.axial_ready),
        blocking_reasons: Array.isArray((status as any)?.blocking_reasons) ? (status as any).blocking_reasons : [],
        supported: Boolean((status as any)?.supported),
      });
    } catch {
      // best-effort
      setRerunPrecheck(null);
    }
  }, [project]);

  const executeRerun = useCallback(async () => {
    if (!rerunEndpoint || !rerunPayload) return;
    setRerunExecLoading(true);
    setRerunExecError(null);
    try {
      // New session per execution for auditability
      const newSessionId = `rerun-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
      await adminPostJson<any>(rerunEndpoint, rerunPayload, { "X-Session-ID": newSessionId }, 120000);
      setRerunOpen(false);
      setRerunRun(null);
      setRerunPayload(null);
      void refresh();
    } catch (e) {
      setRerunExecError(e instanceof Error ? e.message : "Error re-ejecutando");
    } finally {
      setRerunExecLoading(false);
    }
  }, [rerunEndpoint, rerunPayload, refresh]);

  const openLog = useCallback(async (run: AdminOpsRun) => {
    setSelected(run);
    setLogRecords(null);
    setLogError(null);

    if (!run.session_id) {
      setLogError("No hay session_id para esta ejecución.");
      return;
    }

    setLogLoading(true);
    try {
      const res = await adminOpsLog(project, run.session_id, run.request_id, 400);
      setLogRecords(Array.isArray((res as any).records) ? (res as any).records : []);
    } catch (e) {
      setLogError(e instanceof Error ? e.message : "Error cargando log");
    } finally {
      setLogLoading(false);
    }
  }, [project]);

  const copySummary = useCallback(async (run: AdminOpsRun) => {
    const text = [
      `project=${project}`,
      `timestamp=${run.timestamp || ""}`,
      `op=${opLabel(run)}`,
      `http=${(run as any).http_method || ""}`,
      `outcome=${outcomeLabel(run)}`,
      `params=${opParams(run)}`,
      `status=${run.status_code ?? ""}`,
      `duration_ms=${run.duration_ms ?? ""}`,
      `session_id=${run.session_id || ""}`,
      `request_id=${run.request_id || ""}`,
    ].join("\n");
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // ignore
    }
  }, [project]);

  return (
    <section className="admin-ops">
      <header className="admin-ops__header">
        <div>
          <h3>🧭 Operaciones (Post-ejecución)</h3>
          <div className="admin-ops__subtitle">
            Fuente: logs estructurados por <code>session_id</code>. Proyecto: <strong>{project}</strong>
          </div>
        </div>
        <div className="admin-ops__actions">
          <button className="admin-ops__btn" onClick={refresh} disabled={loading}>
            {loading ? "Actualizando…" : "Actualizar"}
          </button>
        </div>
      </header>

      <div className="admin-ops__filters">
        <div className="admin-ops__filterRow">
          <label>
            Tipo
            <select value={kind} onChange={(e) => setKind(e.target.value as any)}>
              <option value="all">Todo</option>
              <option value="errors">Solo errores</option>
              <option value="mutations">Solo mutaciones (updated &gt; 0)</option>
            </select>
          </label>
          <label>
            Operación
            <select value={op} onChange={(e) => setOp(e.target.value as any)}>
              <option value="all">Todas</option>
              <option value="backfill">Backfill</option>
              <option value="repair">Repair</option>
              <option value="sync">Sync Neo4j</option>
              <option value="ontology">Ontology</option>
              <option value="maintenance">Maintenance</option>
            </select>
          </label>
          <div className="admin-ops__filterToggle">
            <div>Incidentes</div>
            <label className="admin-ops__checkbox">
              <input
                type="checkbox"
                checked={intent === "write_intent_post"}
                onChange={(e) => setIntent(e.target.checked ? "write_intent_post" : "all")}
              />
              Solo operaciones con intento de mutación (POST)
            </label>
            <div className="admin-ops__filterHint">Filtra eventos que intentaron ejecutar cambios (incluye dry-run)</div>
          </div>
          <label>
            Rango
            <select value={range} onChange={(e) => setRange(e.target.value as any)}>
              <option value="24h">Últimas 24h</option>
              <option value="7d">Últimos 7 días</option>
              <option value="custom">From–to (ISO)</option>
            </select>
          </label>
        </div>
        <div className="admin-ops__filterHint">
          Resultado (técnico): <span className="admin-ops__mono">OK</span>/<span className="admin-ops__mono">NOOP</span>/<span className="admin-ops__mono">ERROR</span> derivado de <span className="admin-ops__mono">status_code</span> (y para POST, <span className="admin-ops__mono">rows=0 =&gt; NOOP</span>).
        </div>
        {range === "custom" && (
          <div className="admin-ops__filterRow">
            <label className="admin-ops__filterGrow">
              Since (ISO)
              <input
                type="text"
                value={sinceIso}
                onChange={(e) => setSinceIso(e.target.value)}
                placeholder="2026-01-22T00:00:00Z"
              />
            </label>
            <label className="admin-ops__filterGrow">
              Until (ISO)
              <input
                type="text"
                value={untilIso}
                onChange={(e) => setUntilIso(e.target.value)}
                placeholder="2026-01-22T23:59:59Z"
              />
            </label>
          </div>
        )}
      </div>

      {error && <div className="admin-ops__error">⚠️ {error}</div>}

      <div className="admin-ops__tableWrap">
        <table className="admin-ops__table">
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Operación</th>
              <th>HTTP</th>
              <th>Resultado</th>
              <th>Parámetros</th>
              <th>Rows</th>
              <th>Duración</th>
              <th>Sesión</th>
              <th>Req</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {runs.length === 0 ? (
              <tr>
                <td colSpan={10} className="admin-ops__empty">
                  No hay ejecuciones admin recientes para este proyecto.
                </td>
              </tr>
            ) : (
              runs.map((run) => {
                const httpMethod = String((run as any).http_method || "—").toUpperCase();
                const outcome = outcomeLabel(run);
                const updatedCount = getUpdatedCount(run);
                const updatedText = typeof updatedCount === "number" ? String(updatedCount) : "—";
                const duration = typeof run.duration_ms === "number" ? `${Math.round(run.duration_ms)} ms` : "—";
                return (
                  <tr key={`${run.request_id}-${run.timestamp || ""}`}>
                    <td>{fmtTs(run.timestamp)}</td>
                    <td>{opLabel(run)}</td>
                    <td className="admin-ops__mono">{httpMethod}</td>
                    <td className="admin-ops__mono">{outcome}</td>
                    <td className="admin-ops__mono">{opParams(run)}</td>
                    <td className="admin-ops__mono">{updatedText}</td>
                    <td className="admin-ops__mono">{duration}</td>
                    <td className="admin-ops__mono" title={run.session_id || ""}>{shortId(run.session_id, 10)}</td>
                    <td className="admin-ops__mono" title={run.request_id}>{shortId(run.request_id, 10)}</td>
                    <td className="admin-ops__rowActions">
                      <button className="admin-ops__btn" onClick={() => void openLog(run)}>
                        Ver log
                      </button>
                      <button className="admin-ops__btn" onClick={() => void openRerun(run)}>
                        Re-ejecutar
                      </button>
                      <button className="admin-ops__btn admin-ops__btn--ghost" onClick={() => void copySummary(run)}>
                        Copiar
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {selected && (
        <div className="admin-ops__modalBackdrop" role="dialog" aria-modal="true">
          <div className="admin-ops__modal">
            <header className="admin-ops__modalHeader">
              <div>
                <div className="admin-ops__modalTitle">Log de ejecución</div>
                <div className="admin-ops__modalMeta">
                  <span className="admin-ops__mono">session={selected.session_id}</span>
                  <span className="admin-ops__mono">request={selected.request_id}</span>
                </div>
              </div>
              <button className="admin-ops__btn" onClick={() => setSelected(null)}>
                Cerrar
              </button>
            </header>

            {logError && <div className="admin-ops__error">⚠️ {logError}</div>}
            {logLoading && <div className="admin-ops__loading">Cargando log…</div>}

            {!logLoading && logRecords && (
              <pre className="admin-ops__log">{safeJson(logRecords)}</pre>
            )}
          </div>
        </div>
      )}

      {rerunOpen && rerunRun && (
        <div className="admin-ops__modalBackdrop" role="dialog" aria-modal="true">
          <div className="admin-ops__modal">
            <header className="admin-ops__modalHeader">
              <div>
                <div className="admin-ops__modalTitle">Re-ejecutar con confirmación explícita</div>
                <div className="admin-ops__modalMeta">
                  <span className="admin-ops__mono">project={project}</span>
                  <span className="admin-ops__mono">op={opLabel(rerunRun)}</span>
                </div>
              </div>
              <button
                className="admin-ops__btn"
                onClick={() => {
                  setRerunOpen(false);
                  setRerunRun(null);
                }}
              >
                Cerrar
              </button>
            </header>

            <div className="admin-ops__modalBody">
              <div className="admin-ops__warn">
                ⚠️ Esta operación puede mutar datos. Esto NO es un retry silencioso: se muestra el payload y se requiere confirmación.
              </div>

              {rerunPrecheck && (
                <div className="admin-ops__precheck">
                  <div>
                    <strong>Prechecks (lectura)</strong>
                  </div>
                  <div className="admin-ops__precheckGrid">
                    <div>Freeze: {rerunPrecheck.freeze ? "ACTIVO" : "no"}</div>
                    <div>supported: {String(rerunPrecheck.supported ?? "—")}</div>
                    <div>axial_ready: {String(rerunPrecheck.axial_ready ?? "—")}</div>
                    <div>
                      blocking_reasons: {Array.isArray(rerunPrecheck.blocking_reasons) ? rerunPrecheck.blocking_reasons.join(", ") : "—"}
                    </div>
                  </div>
                  {rerunPrecheck.freeze && (
                    <div className="admin-ops__warn">
                      Freeze activo: el backend bloqueará mutaciones (dry_run=false) salvo que se rompa el freeze explícitamente.
                    </div>
                  )}
                </div>
              )}

              {rerunExecError && <div className="admin-ops__error">⚠️ {rerunExecError}</div>}

              <div className="admin-ops__payload">
                <div className="admin-ops__payloadRow">
                  <div>
                    <div className="admin-ops__mono">Endpoint</div>
                    <div className="admin-ops__mono">{rerunEndpoint || "—"}</div>
                  </div>
                </div>
                <div className="admin-ops__payloadRow">
                  <div className="admin-ops__mono">Payload (read-only)</div>
                  <pre className="admin-ops__payloadPre">{safeJson(rerunPayload)}</pre>
                </div>
              </div>

              {rerunPayload?.dry_run === false && (
                <div className="admin-ops__danger">
                  <label className="admin-ops__dangerAck">
                    <input
                      type="checkbox"
                      checked={rerunDangerAck}
                      onChange={(e) => setRerunDangerAck(e.target.checked)}
                    />
                    Entiendo que esto puede modificar datos.
                  </label>
                  <label className="admin-ops__dangerAck">
                    Escribe <code>EJECUTAR</code> para habilitar
                    <input
                      type="text"
                      value={rerunTyped}
                      onChange={(e) => setRerunTyped(e.target.value)}
                      placeholder="EJECUTAR"
                    />
                  </label>
                </div>
              )}

              <div className="admin-ops__modalFooter">
                <button
                  className="admin-ops__btn"
                  onClick={() => void executeRerun()}
                  disabled={
                    rerunExecLoading ||
                    !rerunEndpoint ||
                    !rerunPayload ||
                    (rerunPayload?.dry_run === false && (!rerunDangerAck || rerunTyped.trim() !== "EJECUTAR")) ||
                    Boolean(rerunPrecheck?.freeze && rerunPayload?.dry_run === false)
                  }
                >
                  {rerunExecLoading ? "Ejecutando…" : "Ejecutar"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="admin-ops__hint">
        Tip: el <code>X-Session-ID</code> del navegador debe coincidir con la carpeta en <code>logs/&lt;project&gt;/&lt;session&gt;/app.jsonl</code>.
      </div>
    </section>
  );
}
