/**
 * @fileoverview Panel operativo (admin) para la transición controlada a code_id (Fase 1.5).
 *
 * IMPORTANTE:
 * - Infra/mantenimiento, NO análisis.
 * - Read-only por defecto.
 * - Acciones con efectos requieren dry-run + confirm explícito.
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  codeIdBackfill,
  codeIdInconsistencies,
  codeIdRepair,
  codeIdStatus,
  ontologyFreezeBreak,
  ontologyFreezeSet,
  ontologyFreezeStatus,
} from "../services/api";

const PROJECT_STORAGE_KEY = "qualy-dashboard-project";

type CodeIdStatusResponse = {
  project: string;
  supported: boolean;
  has_table?: boolean;
  reason?: string;
  columns?: {
    code_id: boolean;
    canonical_code_id: boolean;
    canonical_codigo: boolean;
  };
  counts?: Record<string, any>;
  axial_ready?: boolean;
  blocking_reasons?: string[];
  ontology_freeze?: {
    is_frozen: boolean;
    frozen_at?: string | null;
    frozen_by?: string | null;
    broken_at?: string | null;
    broken_by?: string | null;
    note?: string | null;
    updated_at?: string | null;
  } | null;
  notes?: string[];
};

type FreezeStatusResponse = {
  project: string;
  is_frozen: boolean;
  frozen_at?: string | null;
  frozen_by?: string | null;
  broken_at?: string | null;
  broken_by?: string | null;
  note?: string | null;
  updated_at?: string | null;
};

type CodeIdInconsistenciesResponse = {
  project: string;
  supported: boolean;
  reason?: string;
  columns?: Record<string, boolean>;
  samples?: {
    missing_code_id?: Array<any>;
    missing_canonical_code_id?: Array<any>;
    divergences?: Array<any>;
    self_pointing?: Array<any>;
    cycles?: Array<any>;
  };
  notes?: string[];
};

export function CodeIdTransitionSection() {
  const enabled = useMemo(
    () => String(import.meta.env.VITE_ENABLE_CODE_ID_TRANSITION_PANEL || "").toLowerCase() === "true",
    []
  );

  const project = useMemo(() => localStorage.getItem(PROJECT_STORAGE_KEY) || "default", []);

  const [status, setStatus] = useState<CodeIdStatusResponse | null>(null);
  const [incons, setIncons] = useState<CodeIdInconsistenciesResponse | null>(null);
  const [freeze, setFreeze] = useState<FreezeStatusResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<any>(null);

  const [batchSize, setBatchSize] = useState<number>(500);

  const reload = useCallback(async () => {
    if (!enabled) return;
    setLoading(true);
    setError(null);
    setMessage(null);
    try {
      const [s, i, f] = await Promise.all([
        codeIdStatus(project),
        codeIdInconsistencies(project, 50),
        ontologyFreezeStatus(project),
      ]);
      setStatus(s as any);
      setIncons(i as any);
      setFreeze(f as any);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [enabled, project]);

  useEffect(() => {
    void reload();
  }, [reload]);

  if (!enabled) {
    return null;
  }

  const confirmImpact = (title: string): boolean => {
    return confirm(
      "⚠️ Herramienta de mantenimiento de identidad conceptual (Fase 1.5)\n\n" +
        title +
        "\n\nEsta acción modifica ontología interna. No es parte del flujo normal de investigación." +
        "\n\n¿Continuar?"
    );
  };

  const setFreezeOn = async () => {
    setLoading(true);
    setError(null);
    setMessage(null);
    try {
      const ok = confirmImpact(
        "Activar FREEZE ontológico (bloquea operaciones con efectos: backfill/repair)."
      );
      if (!ok) return;
      await ontologyFreezeSet(project, { note: "freeze activado desde panel Fase 1.5" });
      setMessage("✅ Freeze activado");
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const breakFreeze = async () => {
    setLoading(true);
    setError(null);
    setMessage(null);
    try {
      const phrase = prompt(
        "Para romper el freeze ontológico, escribe exactamente: BREAK_FREEZE"
      );
      if (!phrase) return;
      await ontologyFreezeBreak(project, {
        confirm: true,
        phrase,
        note: "freeze roto desde panel Fase 1.5",
      });
      setMessage("✅ Freeze roto");
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const runBackfill = async (mode: "code_id" | "canonical_code_id" | "all", dryRun: boolean) => {
    setLoading(true);
    setError(null);
    setMessage(null);
    try {
      if (!dryRun) {
        if (freeze?.is_frozen) {
          throw new Error("Proyecto está en freeze ontológico. Rompe freeze para ejecutar operaciones con efectos.");
        }
        const ok = confirmImpact(`Ejecutar backfill (${mode}) en batches de ${batchSize}`);
        if (!ok) return;
      }
      const res = await codeIdBackfill(project, {
        mode,
        dry_run: dryRun,
        confirm: !dryRun,
        batch_size: batchSize,
      });
      setMessage(`✅ Backfill ${mode}: ${dryRun ? "dry-run" : "ejecutado"}`);
      setLastResult({ kind: "backfill", mode, dry_run: dryRun, response: res });
      // Refresh after any operation
      await reload();
      // Keep last response accessible via console
      console.log("[code_id] backfill result", res);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const runRepair = async (
    action: "derive_text_from_id" | "derive_id_from_text" | "fix_self_pointing_mapped",
    dryRun: boolean
  ) => {
    setLoading(true);
    setError(null);
    setMessage(null);
    try {
      if (!dryRun) {
        if (freeze?.is_frozen) {
          throw new Error("Proyecto está en freeze ontológico. Rompe freeze para ejecutar operaciones con efectos.");
        }
        const ok = confirmImpact(`Ejecutar repair (${action}) en batches de ${batchSize}`);
        if (!ok) return;
      }
      const res = await codeIdRepair(project, {
        action,
        dry_run: dryRun,
        confirm: !dryRun,
        batch_size: batchSize,
      });
      setMessage(`✅ Repair ${action}: ${dryRun ? "dry-run" : "ejecutado"}`);
      setLastResult({ kind: "repair", action, dry_run: dryRun, response: res });
      await reload();
      console.log("[code_id] repair result", res);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const counts = status?.counts || {};
  const axialReady = Boolean(status?.axial_ready);
  const blockingReasons = Array.isArray(status?.blocking_reasons) ? status?.blocking_reasons : [];
  const frozen = Boolean(freeze?.is_frozen);
  const samples = (incons?.samples || {}) as any;

  const renderSample = (title: string, rows: any[] | undefined) => {
    const safeRows = Array.isArray(rows) ? rows : [];
    return (
      <details style={{ marginTop: "0.5rem" }}>
        <summary style={{ cursor: "pointer" }}>
          {title} <span style={{ opacity: 0.8 }}>({safeRows.length})</span>
        </summary>
        <div style={{ marginTop: "0.35rem" }}>
          {safeRows.length === 0 ? (
            <div className="sync-note">Sin muestras.</div>
          ) : (
            <pre style={{ whiteSpace: "pre-wrap" }}>{JSON.stringify(safeRows, null, 2)}</pre>
          )}
        </div>
      </details>
    );
  };

  return (
    <section className="admin-panel__neo4j-sync">
      <h3>🧰 Mantenimiento de identidad conceptual (Fase 1.5)</h3>
      <p className="sync-note">
        Este panel es <strong>infraestructural</strong>. No habilita análisis, ni rankings, ni
        inferencias. Read-only por defecto.
      </p>

      <div style={{ marginTop: "0.5rem" }}>
        <div className={`sync-indicator ${frozen ? "disconnected" : "connected"}`}>
          {frozen ? "🧊 Freeze ontológico ACTIVO" : "✅ Freeze ontológico inactivo"}
        </div>
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginTop: "0.5rem" }}>
          <button className="sync-button" onClick={setFreezeOn} disabled={loading || frozen}>
            Activar freeze
          </button>
          <button
            className="sync-button sync-button--warn"
            onClick={breakFreeze}
            disabled={loading || !frozen}
            title="Romper freeze requiere frase BREAK_FREEZE"
          >
            Romper freeze
          </button>
        </div>
      </div>

      <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "center" }}>
        <button className="sync-button" onClick={reload} disabled={loading}>
          {loading ? "Actualizando..." : "🔄 Refrescar"}
        </button>

        <label style={{ display: "inline-flex", gap: "0.5rem", alignItems: "center" }}>
          <span style={{ fontSize: "0.9rem" }}>Batch</span>
          <input
            type="number"
            min={10}
            max={5000}
            value={batchSize}
            onChange={(e) => setBatchSize(Number(e.target.value || 500))}
            style={{ width: 110 }}
          />
        </label>
      </div>

      {status && (
        <div style={{ marginTop: "0.75rem" }}>
          <div className={`sync-indicator ${status.supported ? "connected" : "disconnected"}`}>
            {status.supported ? "✅ Fase 1.5 soportada" : "⚠️ Fase 1.5 no habilitada"}
          </div>
          {status.reason && <div className="sync-message">{status.reason}</div>}
          <div className="sync-note" style={{ marginTop: "0.5rem" }}>
            ℹ️ Este panel es <strong>infraestructural</strong>: valida consistencia de identidad/canonicidad.
            No evalúa teoría, categorías, centralidad ni decisiones semánticas.
          </div>
          <div className="sync-status-grid" style={{ marginTop: "0.5rem" }}>
            <div className="sync-stat">
              <span className="sync-value">{counts.total_rows ?? "-"}</span>
              <span className="sync-label">Filas catálogo</span>
            </div>
            <div className="sync-stat">
              <span className="sync-value">{counts.missing_code_id ?? "-"}</span>
              <span className="sync-label">Sin code_id</span>
            </div>
            <div className="sync-stat">
              <span className="sync-value">{counts.missing_canonical_code_id_for_noncanonical ?? "-"}</span>
              <span className="sync-label">No-canónicos sin canonical_code_id</span>
            </div>
            <div className="sync-stat">
              <span className="sync-value">{counts.divergences_text_vs_id ?? "-"}</span>
              <span className="sync-label">Divergencias texto↔ID</span>
            </div>
            <div className="sync-stat">
              <span className="sync-value">{counts.pending_merges ?? "-"}</span>
              <span className="sync-label">Merges pendientes (info)</span>
            </div>
            <div className="sync-stat">
              <span className="sync-value">{counts.self_canonical_nodes ?? counts.self_pointing_canonical_code_id ?? "-"}</span>
              <span className="sync-label">Self-canonical (normal)</span>
            </div>
            <div className="sync-stat">
              <span className="sync-value">{counts.cycles_non_trivial_nodes ?? counts.cycle_nodes ?? "-"}</span>
              <span className="sync-label">Ciclos no triviales</span>
            </div>
          </div>

          <div style={{ marginTop: "0.5rem" }}>
            <div className={`sync-indicator ${axialReady ? "connected" : "disconnected"}`}>
              {axialReady
                ? "✅ Infraestructura lista para codificación axial"
                : "⛔ Bloqueado para codificación axial (infraestructura)"}
            </div>
            {blockingReasons.length > 0 && (
              <div className="sync-message">
                Bloqueos (hard): <code>{blockingReasons.join(", ")}</code>
              </div>
            )}

            <div className="sync-note" style={{ marginTop: "0.35rem" }}>
              Regla de lectura: <strong>self-canonical</strong> (<code>canonical_code_id = code_id</code>) es estado esperado.
              Solo bloquea si hay identidad incompleta, divergencias, o ciclos <strong>no triviales</strong>.
              El <strong>freeze</strong> bloquea mutaciones (backfill/repair), no define <code>axial_ready</code>.
            </div>
          </div>
        </div>
      )}

      {incons && (
        <details style={{ marginTop: "0.75rem" }}>
          <summary style={{ cursor: "pointer" }}>📋 Muestras operativas (inconsistencias)</summary>
          <div style={{ marginTop: "0.5rem" }}>
            <div className="sync-note">
              Vista técnica, solo lectura: worklist literal para operación Fase 1.5. No representa categorías ni importancia.
            </div>
            {renderSample("missing_code_id", samples.missing_code_id)}
            {renderSample("missing_canonical_code_id", samples.missing_canonical_code_id)}
            {renderSample("divergences (texto↔ID)", samples.divergences)}
            {renderSample("self-canonical (canonical_code_id = code_id) — estado esperado", samples.self_pointing)}
            {renderSample("cycles no triviales (best-effort)", samples.cycles)}
          </div>
        </details>
      )}

      <div style={{ marginTop: "0.75rem", display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
        <button className="sync-button" onClick={() => runBackfill("code_id", true)} disabled={loading}>
          Dry-run backfill code_id
        </button>
        <button
          className="sync-button sync-button--warn"
          onClick={() => runBackfill("code_id", false)}
          disabled={loading || frozen}
          title="Asigna code_id en batch (requiere confirmación)"
        >
          Ejecutar backfill code_id
        </button>

        <button className="sync-button" onClick={() => runBackfill("canonical_code_id", true)} disabled={loading}>
          Dry-run backfill canonical_code_id
        </button>
        <button
          className="sync-button sync-button--warn"
          onClick={() => runBackfill("canonical_code_id", false)}
          disabled={loading || frozen}
          title="Deriva canonical_code_id desde canonical_codigo (requiere confirmación)"
        >
          Ejecutar backfill canonical_code_id
        </button>
      </div>

      <div style={{ marginTop: "0.5rem", display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
        <button className="sync-button" onClick={() => runRepair("derive_text_from_id", true)} disabled={loading}>
          Dry-run repair: texto ← ID
        </button>
        <button
          className="sync-button sync-button--warn"
          onClick={() => runRepair("derive_text_from_id", false)}
          disabled={loading || frozen}
          title="Regla: ID manda. Re-deriva canonical_codigo desde canonical_code_id"
        >
          Ejecutar repair: texto ← ID
        </button>

        <button className="sync-button" onClick={() => runRepair("derive_id_from_text", true)} disabled={loading}>
          Dry-run repair: ID ← texto
        </button>
        <button
          className="sync-button sync-button--warn"
          onClick={() => runRepair("derive_id_from_text", false)}
          disabled={loading || frozen}
          title="Best-effort. Deriva canonical_code_id desde canonical_codigo"
        >
          Ejecutar repair: ID ← texto
        </button>
      </div>

      {lastResult && (
        <details style={{ marginTop: "0.75rem" }}>
          <summary style={{ cursor: "pointer" }}>🧾 Último resultado (raw)</summary>
          <div style={{ marginTop: "0.5rem" }}>
            <pre style={{ whiteSpace: "pre-wrap" }}>{JSON.stringify(lastResult, null, 2)}</pre>
          </div>
        </details>
      )}

      {message && <div className="sync-message">{message}</div>}
      {error && <div className="sync-message">❌ {error}</div>}

      <p className="sync-note" style={{ marginTop: "0.75rem" }}>
        Nota: este panel debe vivir solo en <strong>Administración</strong> y con feature-flag.
        No forma parte del flujo normal del investigador.
      </p>
    </section>
  );
}
