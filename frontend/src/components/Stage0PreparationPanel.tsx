import { useCallback, useEffect, useMemo, useState } from "react";
import {
  approveStage0Override,
  createStage0Actor,
  createStage0Consent,
  getStage0AnalysisPlanLatest,
  getStage0Overrides,
  getStage0ProtocolLatest,
  getStage0SamplingLatest,
  getStage0Status,
  listStage0Actors,
  rejectStage0Override,
  requestStage0Override,
  upsertStage0AnalysisPlan,
  upsertStage0Protocol,
  upsertStage0Sampling,
  type Stage0Actor,
  type Stage0OverrideEntry,
  type Stage0StatusResponse,
} from "../services/api";

type TabKey = "protocol" | "actors" | "sampling" | "analysis" | "overrides";

function safeJsonParse(value: string): { ok: true; data: any } | { ok: false; error: string } {
  try {
    if (!value.trim()) {
      return { ok: true, data: {} };
    }
    return { ok: true, data: JSON.parse(value) };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : "JSON inválido" };
  }
}

function getUserIsAdmin(): boolean {
  try {
    const raw = localStorage.getItem("user");
    if (!raw) return false;
    const user = JSON.parse(raw) as { roles?: string[] };
    return Boolean(user.roles?.some((r) => String(r).toLowerCase() === "admin"));
  } catch {
    return false;
  }
}

export function Stage0PreparationPanel({ project }: { project: string }) {
  const [tab, setTab] = useState<TabKey>("protocol");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<Stage0StatusResponse | null>(null);

  const [protocolVersion, setProtocolVersion] = useState(1);
  const [protocolTitle, setProtocolTitle] = useState("");
  const [protocolStatus, setProtocolStatus] = useState("draft");
  const [protocolMarkdown, setProtocolMarkdown] = useState("");

  const [samplingVersion, setSamplingVersion] = useState(1);
  const [samplingMarkdown, setSamplingMarkdown] = useState("");

  const [analysisVersion, setAnalysisVersion] = useState(1);
  const [analysisMarkdown, setAnalysisMarkdown] = useState("");

  const [actors, setActors] = useState<Stage0Actor[]>([]);
  const [actorAlias, setActorAlias] = useState("");
  const [actorDemographicsJson, setActorDemographicsJson] = useState("{}");
  const [actorNotes, setActorNotes] = useState("");

  const [consentOpenFor, setConsentOpenFor] = useState<string | null>(null);
  const [consentVersion, setConsentVersion] = useState(1);
  const [consentSignedAt, setConsentSignedAt] = useState<string>("");
  const [consentEvidenceUrl, setConsentEvidenceUrl] = useState<string>("");
  const [consentScopeJson, setConsentScopeJson] = useState<string>("{}");
  const [consentNotes, setConsentNotes] = useState<string>("");

  const [overrides, setOverrides] = useState<Stage0OverrideEntry[]>([]);
  const [overrideScope, setOverrideScope] = useState<"ingest" | "analyze" | "both">("both");
  const [overrideReasonCategory, setOverrideReasonCategory] = useState<
    "critical_incident" | "data_validation" | "service_continuity" | "protocol_exception" | "other"
  >("protocol_exception");
  const [overrideReasonDetails, setOverrideReasonDetails] = useState("");
  const [overrideRequestedExpiresHours, setOverrideRequestedExpiresHours] = useState(24);

  const isAdmin = useMemo(() => getUserIsAdmin(), []);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [statusRes, protocolRes, actorsRes, samplingRes, analysisRes, overridesRes] = await Promise.all([
        getStage0Status(project),
        getStage0ProtocolLatest(project),
        listStage0Actors(project),
        getStage0SamplingLatest(project),
        getStage0AnalysisPlanLatest(project),
        getStage0Overrides(project, 50),
      ]);

      setStatus(statusRes);

      const protocol = protocolRes.protocol;
      if (protocol) {
        setProtocolVersion(protocol.version ?? 1);
        setProtocolTitle(protocol.title ?? "");
        setProtocolStatus(protocol.status ?? "draft");
        setProtocolMarkdown(String(protocol.content?.markdown ?? ""));
      } else {
        setProtocolVersion(1);
        setProtocolTitle("");
        setProtocolStatus("draft");
        setProtocolMarkdown("");
      }

      const sampling = samplingRes.sampling;
      if (sampling) {
        setSamplingVersion(sampling.version ?? 1);
        setSamplingMarkdown(String(sampling.content?.markdown ?? ""));
      } else {
        setSamplingVersion(1);
        setSamplingMarkdown("");
      }

      const analysisPlan = analysisRes.analysis_plan;
      if (analysisPlan) {
        setAnalysisVersion(analysisPlan.version ?? 1);
        setAnalysisMarkdown(String(analysisPlan.content?.markdown ?? ""));
      } else {
        setAnalysisVersion(1);
        setAnalysisMarkdown("");
      }

      setActors(actorsRes.actors || []);
      setOverrides(overridesRes.overrides || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error cargando Etapa 0");
    } finally {
      setLoading(false);
    }
  }, [project]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const readyBadge = status?.ready ? "✅ Lista" : "🟡 Pendiente";

  const handleSaveProtocol = async () => {
    setLoading(true);
    setError(null);
    try {
      await upsertStage0Protocol(project, {
        version: protocolVersion,
        title: protocolTitle || undefined,
        status: protocolStatus || undefined,
        content: { markdown: protocolMarkdown },
      });
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo guardar el protocolo");
    } finally {
      setLoading(false);
    }
  };

  const handleSaveSampling = async () => {
    setLoading(true);
    setError(null);
    try {
      await upsertStage0Sampling(project, {
        version: samplingVersion,
        content: { markdown: samplingMarkdown },
      });
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo guardar muestreo");
    } finally {
      setLoading(false);
    }
  };

  const handleSaveAnalysisPlan = async () => {
    setLoading(true);
    setError(null);
    try {
      await upsertStage0AnalysisPlan(project, {
        version: analysisVersion,
        content: { markdown: analysisMarkdown },
      });
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo guardar plan de análisis");
    } finally {
      setLoading(false);
    }
  };

  const handleCreateActor = async () => {
    const parsed = safeJsonParse(actorDemographicsJson);
    if (!parsed.ok) {
      setError(`Demographics JSON inválido: ${parsed.error}`);
      return;
    }
    if (!actorAlias.trim()) {
      setError("Alias es obligatorio (sin PII)");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      await createStage0Actor(project, {
        alias: actorAlias.trim(),
        demographics_anon: parsed.data,
        notes: actorNotes || undefined,
      });
      setActorAlias("");
      setActorDemographicsJson("{}");
      setActorNotes("");
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo crear actor");
    } finally {
      setLoading(false);
    }
  };

  const openConsentForActor = (actorId: string) => {
    setConsentOpenFor((prev) => (prev === actorId ? null : actorId));
    setConsentVersion(1);
    setConsentSignedAt("");
    setConsentEvidenceUrl("");
    setConsentScopeJson("{}");
    setConsentNotes("");
  };

  const handleCreateConsent = async (actorId: string) => {
    const parsedScope = safeJsonParse(consentScopeJson);
    if (!parsedScope.ok) {
      setError(`Scope JSON inválido: ${parsedScope.error}`);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      await createStage0Consent(project, actorId, {
        version: consentVersion,
        signed_at: consentSignedAt ? new Date(consentSignedAt).toISOString() : undefined,
        scope: parsedScope.data,
        evidence_url: consentEvidenceUrl || undefined,
        notes: consentNotes || undefined,
      });
      setConsentOpenFor(null);
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo guardar consentimiento");
    } finally {
      setLoading(false);
    }
  };

  const handleRequestOverride = async () => {
    if (!overrideReasonDetails.trim()) {
      setError("Debes indicar el motivo (reason_details)");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      await requestStage0Override(project, {
        scope: overrideScope,
        reason_category: overrideReasonCategory,
        reason_details: overrideReasonDetails.trim(),
        requested_expires_hours: overrideRequestedExpiresHours,
      });
      setOverrideReasonDetails("");
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo solicitar override");
    } finally {
      setLoading(false);
    }
  };

  const handleApproveReject = async (overrideId: string, action: "approve" | "reject") => {
    const note = window.prompt(action === "approve" ? "Nota de aprobación" : "Nota de rechazo");
    if (!note || note.trim().length < 3) {
      return;
    }
    const expires = action === "approve" ? window.prompt("Horas de expiración (1-168)", "24") : null;
    const expiresHours = action === "approve" ? Number(expires || 24) : 24;

    setLoading(true);
    setError(null);
    try {
      if (action === "approve") {
        await approveStage0Override(project, overrideId, { decision_note: note.trim(), expires_hours: expiresHours });
      } else {
        await rejectStage0Override(project, overrideId, { decision_note: note.trim(), expires_hours: 24 });
      }
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo actualizar override");
    } finally {
      setLoading(false);
    }
  };

  const tabs: Array<{ key: TabKey; label: string }> = [
    { key: "protocol", label: "Protocolo" },
    { key: "actors", label: "Actores + Consentimientos" },
    { key: "sampling", label: "Muestreo" },
    { key: "analysis", label: "Plan de análisis" },
    { key: "overrides", label: "Overrides" },
  ];

  return (
    <div className="workflow__card" style={{ padding: 16 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <div>
          <div style={{ fontWeight: 700, marginBottom: 4 }}>Checklist Etapa 0 (backend)</div>
          <div style={{ fontSize: 13, opacity: 0.85 }}>
            Estado: <strong>{readyBadge}</strong> · Protocolo {status?.checks?.protocol ? "✅" : "❌"} · Actores {status?.checks?.actors ? "✅" : "❌"} · Consentimientos {status?.checks?.consents ? "✅" : "❌"} · Muestreo {status?.checks?.sampling ? "✅" : "❌"} · Plan {status?.checks?.analysis_plan ? "✅" : "❌"}
          </div>
          {status?.override && (
            <div style={{ fontSize: 12, marginTop: 6 }}>
              Override activo: <strong>{status.override.scope}</strong> hasta <strong>{status.override.expires_at || "(sin exp.)"}</strong>
            </div>
          )}
        </div>

        <div style={{ display: "flex", gap: 8 }}>
          <button type="button" className="workflow__cta" onClick={() => void reload()} disabled={loading}>
            {loading ? "Cargando..." : "Refrescar"}
          </button>
        </div>
      </div>

      {error && (
        <div style={{ marginTop: 12, color: "#b91c1c", fontSize: 13, whiteSpace: "pre-wrap" }}>
          {error}
        </div>
      )}

      <div style={{ marginTop: 14, display: "flex", gap: 8, flexWrap: "wrap" }}>
        {tabs.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            disabled={loading}
            style={{
              padding: "6px 10px",
              borderRadius: 999,
              border: "1px solid #d1d5db",
              background: tab === t.key ? "#111827" : "#ffffff",
              color: tab === t.key ? "#ffffff" : "#111827",
              fontSize: 13,
              cursor: "pointer",
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "protocol" && (
        <div style={{ marginTop: 14 }}>
          <p style={{ marginTop: 0, fontSize: 13, opacity: 0.85 }}>
            Guarda el protocolo como Markdown (se almacena como JSON: <code>{"{markdown: \"...\"}"}</code>). No incluyas PII.
          </p>
          <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: 10, alignItems: "center" }}>
            <label>Versión</label>
            <input type="number" min={1} value={protocolVersion} onChange={(e) => setProtocolVersion(Number(e.target.value || 1))} />
            <label>Título</label>
            <input value={protocolTitle} onChange={(e) => setProtocolTitle(e.target.value)} placeholder="Protocolo de investigación" />
            <label>Status</label>
            <select value={protocolStatus} onChange={(e) => setProtocolStatus(e.target.value)}>
              <option value="draft">draft</option>
              <option value="final">final</option>
            </select>
          </div>
          <div style={{ marginTop: 10 }}>
            <textarea
              value={protocolMarkdown}
              onChange={(e) => setProtocolMarkdown(e.target.value)}
              rows={14}
              style={{ width: "100%", fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}
              placeholder="# Protocolo\n\n- Preguntas de investigación\n- Enfoque\n- Instrumentos\n"
            />
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
            <button type="button" className="workflow__cta" onClick={() => setProtocolVersion((v) => v + 1)} disabled={loading}>
              Nueva versión
            </button>
            <button type="button" className="workflow__cta" onClick={() => void handleSaveProtocol()} disabled={loading}>
              Guardar protocolo
            </button>
          </div>
        </div>
      )}

      {tab === "actors" && (
        <div style={{ marginTop: 14 }}>
          <p style={{ marginTop: 0, fontSize: 13, opacity: 0.85 }}>
            Matriz de actores anonimizada: usa alias (P01, P02, etc.) y demografía anonimizada. Los consentimientos se vinculan al actor.
          </p>

          <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: 10, alignItems: "center" }}>
            <label>Alias</label>
            <input value={actorAlias} onChange={(e) => setActorAlias(e.target.value)} placeholder="P01 / Lider comunitario" />
            <label>Demografía (JSON)</label>
            <textarea
              value={actorDemographicsJson}
              onChange={(e) => setActorDemographicsJson(e.target.value)}
              rows={3}
              style={{ width: "100%", fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}
            />
            <label>Notas</label>
            <input value={actorNotes} onChange={(e) => setActorNotes(e.target.value)} placeholder="(opcional)" />
          </div>

          <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
            <button type="button" className="workflow__cta" onClick={() => void handleCreateActor()} disabled={loading}>
              + Agregar actor
            </button>
          </div>

          <div style={{ marginTop: 12, overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ textAlign: "left", borderBottom: "1px solid #e5e7eb" }}>
                  <th style={{ padding: "8px 6px" }}>Alias</th>
                  <th style={{ padding: "8px 6px" }}>Consentimiento</th>
                  <th style={{ padding: "8px 6px" }}>Demografía</th>
                  <th style={{ padding: "8px 6px" }}>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {actors.map((a) => (
                  <tr key={a.actor_id} style={{ borderBottom: "1px solid #f3f4f6" }}>
                    <td style={{ padding: "8px 6px", fontWeight: 600 }}>{a.alias}</td>
                    <td style={{ padding: "8px 6px" }}>
                      {a.has_active_consent ? (
                        <span>✅ v{a.latest_consent_version ?? "-"}</span>
                      ) : (
                        <span>❌ faltante</span>
                      )}
                    </td>
                    <td style={{ padding: "8px 6px" }}>
                      <code style={{ fontSize: 12 }}>{JSON.stringify(a.demographics_anon || {})}</code>
                    </td>
                    <td style={{ padding: "8px 6px" }}>
                      <button
                        type="button"
                        className="workflow__cta"
                        onClick={() => openConsentForActor(a.actor_id)}
                        disabled={loading}
                      >
                        {consentOpenFor === a.actor_id ? "Cerrar" : "Agregar consentimiento"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {consentOpenFor && (
            <div style={{ marginTop: 14, border: "1px solid #e5e7eb", borderRadius: 8, padding: 12 }}>
              <div style={{ fontWeight: 700, marginBottom: 8 }}>Nuevo consentimiento</div>
              <div style={{ display: "grid", gridTemplateColumns: "160px 1fr", gap: 10, alignItems: "center" }}>
                <label>Versión</label>
                <input type="number" min={1} value={consentVersion} onChange={(e) => setConsentVersion(Number(e.target.value || 1))} />
                <label>Firmado (fecha)</label>
                <input type="date" value={consentSignedAt} onChange={(e) => setConsentSignedAt(e.target.value)} />
                <label>Evidence URL</label>
                <input value={consentEvidenceUrl} onChange={(e) => setConsentEvidenceUrl(e.target.value)} placeholder="(opcional)" />
                <label>Scope (JSON)</label>
                <textarea
                  value={consentScopeJson}
                  onChange={(e) => setConsentScopeJson(e.target.value)}
                  rows={3}
                  style={{ width: "100%", fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}
                />
                <label>Notas</label>
                <input value={consentNotes} onChange={(e) => setConsentNotes(e.target.value)} placeholder="(opcional)" />
              </div>
              <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
                <button type="button" className="workflow__cta" onClick={() => void handleCreateConsent(consentOpenFor)} disabled={loading}>
                  Guardar consentimiento
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {tab === "sampling" && (
        <div style={{ marginTop: 14 }}>
          <p style={{ marginTop: 0, fontSize: 13, opacity: 0.85 }}>
            Criterios de muestreo (inclusión/exclusión, cuotas, criterios teóricos). Se guarda como Markdown.
          </p>
          <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: 10, alignItems: "center" }}>
            <label>Versión</label>
            <input type="number" min={1} value={samplingVersion} onChange={(e) => setSamplingVersion(Number(e.target.value || 1))} />
          </div>
          <div style={{ marginTop: 10 }}>
            <textarea
              value={samplingMarkdown}
              onChange={(e) => setSamplingMarkdown(e.target.value)}
              rows={12}
              style={{ width: "100%", fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}
              placeholder="# Muestreo\n\n- Población objetivo\n- Criterios de inclusión\n- Criterios de exclusión\n"
            />
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
            <button type="button" className="workflow__cta" onClick={() => setSamplingVersion((v) => v + 1)} disabled={loading}>
              Nueva versión
            </button>
            <button type="button" className="workflow__cta" onClick={() => void handleSaveSampling()} disabled={loading}>
              Guardar muestreo
            </button>
          </div>
        </div>
      )}

      {tab === "analysis" && (
        <div style={{ marginTop: 14 }}>
          <p style={{ marginTop: 0, fontSize: 13, opacity: 0.85 }}>
            Plan de análisis: estrategias, pasos, criterios de calidad, saturación, y trazabilidad.
          </p>
          <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: 10, alignItems: "center" }}>
            <label>Versión</label>
            <input type="number" min={1} value={analysisVersion} onChange={(e) => setAnalysisVersion(Number(e.target.value || 1))} />
          </div>
          <div style={{ marginTop: 10 }}>
            <textarea
              value={analysisMarkdown}
              onChange={(e) => setAnalysisMarkdown(e.target.value)}
              rows={12}
              style={{ width: "100%", fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}
              placeholder="# Plan de análisis\n\n- Etapas\n- Reglas de codificación\n- Validación\n"
            />
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
            <button type="button" className="workflow__cta" onClick={() => setAnalysisVersion((v) => v + 1)} disabled={loading}>
              Nueva versión
            </button>
            <button type="button" className="workflow__cta" onClick={() => void handleSaveAnalysisPlan()} disabled={loading}>
              Guardar plan
            </button>
          </div>
        </div>
      )}

      {tab === "overrides" && (
        <div style={{ marginTop: 14 }}>
          <p style={{ marginTop: 0, fontSize: 13, opacity: 0.85 }}>
            Overrides permiten continuar ingest/analyze si la Etapa 0 no está lista. Se registran en auditoría.
          </p>

          <div style={{ display: "grid", gridTemplateColumns: "180px 1fr", gap: 10, alignItems: "center" }}>
            <label>Scope</label>
            <select value={overrideScope} onChange={(e) => setOverrideScope(e.target.value as any)}>
              <option value="both">both</option>
              <option value="ingest">ingest</option>
              <option value="analyze">analyze</option>
            </select>

            <label>Reason category</label>
            <select value={overrideReasonCategory} onChange={(e) => setOverrideReasonCategory(e.target.value as any)}>
              <option value="protocol_exception">protocol_exception</option>
              <option value="data_validation">data_validation</option>
              <option value="critical_incident">critical_incident</option>
              <option value="service_continuity">service_continuity</option>
              <option value="other">other</option>
            </select>

            <label>TTL sugerido (horas)</label>
            <input
              type="number"
              min={1}
              max={168}
              value={overrideRequestedExpiresHours}
              onChange={(e) => setOverrideRequestedExpiresHours(Number(e.target.value || 24))}
            />

            <label>Motivo</label>
            <textarea value={overrideReasonDetails} onChange={(e) => setOverrideReasonDetails(e.target.value)} rows={4} />
          </div>

          <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
            <button type="button" className="workflow__cta" onClick={() => void handleRequestOverride()} disabled={loading}>
              Solicitar override
            </button>
          </div>

          <div style={{ marginTop: 12, overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ textAlign: "left", borderBottom: "1px solid #e5e7eb" }}>
                  <th style={{ padding: "8px 6px" }}>Estado</th>
                  <th style={{ padding: "8px 6px" }}>Scope</th>
                  <th style={{ padding: "8px 6px" }}>Categoría</th>
                  <th style={{ padding: "8px 6px" }}>Solicitado</th>
                  <th style={{ padding: "8px 6px" }}>Expira</th>
                  <th style={{ padding: "8px 6px" }}>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {overrides.map((o) => (
                  <tr key={o.override_id} style={{ borderBottom: "1px solid #f3f4f6" }}>
                    <td style={{ padding: "8px 6px" }}>{o.status}</td>
                    <td style={{ padding: "8px 6px" }}>{o.scope}</td>
                    <td style={{ padding: "8px 6px" }}>{o.reason_category}</td>
                    <td style={{ padding: "8px 6px" }}>{o.requested_at || "-"}</td>
                    <td style={{ padding: "8px 6px" }}>{o.expires_at || "-"}</td>
                    <td style={{ padding: "8px 6px" }}>
                      {isAdmin && o.status === "pending" ? (
                        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                          <button type="button" className="workflow__cta" onClick={() => void handleApproveReject(o.override_id, "approve")} disabled={loading}>
                            Aprobar
                          </button>
                          <button type="button" className="workflow__cta" onClick={() => void handleApproveReject(o.override_id, "reject")} disabled={loading}>
                            Rechazar
                          </button>
                        </div>
                      ) : (
                        <span style={{ opacity: 0.7 }}>-</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

export default Stage0PreparationPanel;
