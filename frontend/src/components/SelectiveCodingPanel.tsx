import { useMemo, useState } from "react";
import {
  getNucleusLight,
  type NucleusAuditSummary,
  type NucleusExploratoryScan,
  type NucleusLightResponse,
  type NucleusStoryline,
} from "../services/api";

interface SelectiveCodingPanelProps {
  project: string;
}

type CheckItem = { key: string; label: string };

const CHECK_ITEMS: CheckItem[] = [
  { key: "centrality", label: "Centralidad" },
  { key: "coverage", label: "Cobertura" },
  { key: "quotes", label: "Citas" },
  { key: "probe", label: "Probe" },
];

export function SelectiveCodingPanel({ project }: SelectiveCodingPanelProps) {
  const [categoria, setCategoria] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<NucleusLightResponse | null>(null);

  const storyline: NucleusStoryline = data?.storyline || {};
  const audit: NucleusAuditSummary = data?.audit_summary || {};
  const exploratory: NucleusExploratoryScan | null = data?.exploratory_scan || null;
  const abstention = data?.abstention || null;
  const isGrounded = Boolean(storyline?.is_grounded);

  const handleRun = async () => {
    const cat = (categoria || "").trim();
    if (!cat) {
      setError("Debes ingresar una categoría núcleo para analizar.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await getNucleusLight(project, cat);
      setData(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error consultando núcleo.");
    } finally {
      setLoading(false);
    }
  };

  const nextStep = useMemo(() => {
    if (isGrounded) {
      return "Recomendación: consolidar el núcleo selectivo, revisar la storyline y formalizar memos analíticos.";
    }
    const score = exploratory?.relevance_score;
    if (typeof score === "number" && score < 0.25) {
      return "Recomendación: ampliar ingesta o ajustar términos de búsqueda; densificar códigos antes de concluir.";
    }
    return "Recomendación: volver a codificación abierta/axial para fortalecer evidencia y relaciones.";
  }, [isGrounded, exploratory?.relevance_score]);

  const topNodes = (() => {
    const list = audit?.pagerank_top || [];
    if (!Array.isArray(list)) return [];
    return list
      .map((item: any) => item?.nombre || item?.label || item?.code_id || item?.id)
      .filter(Boolean)
      .slice(0, 6);
  })();

  const coverage = audit?.coverage || {};
  const thresholds = audit?.thresholds || {};
  const checks = audit?.checks || {};

  return (
    <section className="selective-panel">
      <header className="selective-panel__header">
        <div>
          <h2>Codificación selectiva · Núcleo</h2>
          <p className="selective-panel__hint">
            Storyline grounded, auditoría trazable y un Exploratory Scan separado cuando el modelo se abstiene.
          </p>
        </div>
        <div className="selective-panel__controls">
          <input
            type="text"
            value={categoria}
            onChange={(e) => setCategoria(e.target.value)}
            placeholder="Categoría núcleo (ej: resiliencia_comunitaria)"
            className="selective-panel__input"
          />
          <button
            type="button"
            onClick={handleRun}
            disabled={loading}
            className="selective-panel__button"
          >
            {loading ? "Analizando..." : "Analizar núcleo"}
          </button>
        </div>
      </header>

      {error && <div className="selective-panel__error">{error}</div>}

      {data && (
        <>
          <div className="selective-grid">
            <article className="selective-card">
              <div className="selective-card__header">
                <div>
                  <h3>Storyline (Grounded)</h3>
                  <span className="selective-card__sub">
                    {isGrounded ? "Evidencia suficiente" : "Abstención por baja señal"}
                  </span>
                </div>
                <span className={`selective-card__badge ${isGrounded ? "selective-card__badge--ok" : "selective-card__badge--warn"}`}>
                  {isGrounded ? "Grounded" : "Abstención"}
                </span>
              </div>

              {!isGrounded && abstention && (
                <div className="selective-card__alert">
                  <div className="selective-tooltip">
                    <span className="selective-tooltip__icon">i</span>
                    <div className="selective-tooltip__bubble">
                      <strong>Por qué se abstuvo</strong>
                      <div className="selective-tooltip__line">Causa: {abstention.reason || "Señal insuficiente"}</div>
                      {typeof abstention.top_score === "number" && (
                        <div className="selective-tooltip__line">Score max: {abstention.top_score.toFixed(2)}</div>
                      )}
                      {typeof abstention.fragments_found === "number" && (
                        <div className="selective-tooltip__line">Fragmentos: {abstention.fragments_found}</div>
                      )}
                      {abstention.suggestion && (
                        <div className="selective-tooltip__line">Sugerencia: {abstention.suggestion}</div>
                      )}
                    </div>
                  </div>
                  <span className="selective-card__alert-text">
                    El modelo se abstuvo de afirmar causalidad. Revisa la evidencia o activa el Exploratory Scan.
                  </span>
                </div>
              )}

              <div className="selective-card__content">
                {storyline?.answer ? (
                  <p className="selective-card__text">{storyline.answer}</p>
                ) : (
                  <p className="selective-card__empty">Sin storyline disponible.</p>
                )}
              </div>

              {Array.isArray(storyline?.evidence) && storyline.evidence.length > 0 && (
                <div className="selective-card__section">
                  <h4>Evidencia destacada</h4>
                  <ul className="selective-list">
                    {storyline.evidence.slice(0, 4).map((ev, idx) => (
                      <li key={`${ev.fragment_id || idx}`}>
                        <span className="selective-list__label">{ev.source_doc || "Documento"}</span>
                        <span className="selective-list__text">{ev.quote || "Fragmento disponible"}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </article>

            <article className="selective-card">
              <div className="selective-card__header">
                <div>
                  <h3>Audit Summary</h3>
                  <span className="selective-card__sub">Trazabilidad metodológica y checks</span>
                </div>
                <span className="selective-card__badge selective-card__badge--info">Auditoría</span>
              </div>

              <div className="selective-card__content">
                {audit?.text_summary || audit?.summary_md ? (
                  <p className="selective-card__text">{audit.text_summary || audit.summary_md}</p>
                ) : (
                  <p className="selective-card__empty">Sin resumen técnico disponible.</p>
                )}
              </div>

              <div className="selective-card__section">
                <h4>Checks</h4>
                <div className="selective-checks">
                  {CHECK_ITEMS.map((item) => {
                    const value = checks ? Boolean(checks[item.key]) : false;
                    return (
                      <span
                        key={item.key}
                        className={`selective-checks__item ${value ? "selective-checks__item--ok" : "selective-checks__item--warn"}`}
                      >
                        {item.label}: {value ? "OK" : "Pendiente"}
                      </span>
                    );
                  })}
                </div>
              </div>

              <div className="selective-card__section">
                <h4>Cobertura</h4>
                <div className="selective-metrics">
                  <span>Entrevistas: {coverage.interviews ?? "-"}</span>
                  <span>Roles: {coverage.roles ?? "-"}</span>
                  <span>Fragmentos: {coverage.fragments ?? "-"}</span>
                </div>
              </div>

              <div className="selective-card__section">
                <h4>Umbrales</h4>
                <div className="selective-metrics">
                  <span>Rank max: {thresholds.centrality_rank_max ?? "-"}</span>
                  <span>Min entrevistas: {thresholds.min_interviews ?? "-"}</span>
                  <span>Min roles: {thresholds.min_roles ?? "-"}</span>
                  <span>Min citas: {thresholds.min_quotes ?? "-"}</span>
                </div>
              </div>

              {topNodes.length > 0 && (
                <div className="selective-card__section">
                  <h4>Top centralidad</h4>
                  <div className="selective-tags">
                    {topNodes.map((node) => (
                      <span key={node} className="selective-tag">
                        {node}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </article>

            <article className="selective-card">
              <div className="selective-card__header">
                <div>
                  <h3>Exploratory Scan</h3>
                  <span className="selective-card__sub">Descriptivo · no causal</span>
                </div>
                <span className="selective-card__badge selective-card__badge--neutral">
                  {exploratory?.mode || "Exploratorio"}
                </span>
              </div>

              {exploratory ? (
                <>
                  <div className="selective-card__content">
                    <p className="selective-card__text">
                      {exploratory.graph_summary || "Sin resumen exploratorio disponible."}
                    </p>
                  </div>
                  {exploratory.research_feedback?.diagnosis && (
                    <div className="selective-card__section">
                      <h4>Diagnóstico</h4>
                      <p className="selective-card__text">{exploratory.research_feedback.diagnosis}</p>
                    </div>
                  )}
                  {Array.isArray(exploratory.questions) && exploratory.questions.length > 0 && (
                    <div className="selective-card__section">
                      <h4>Preguntas sugeridas</h4>
                      <ul className="selective-list">
                        {exploratory.questions.slice(0, 4).map((q, idx) => (
                          <li key={`${idx}-q`}>{q}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {Array.isArray(exploratory.recommendations) && exploratory.recommendations.length > 0 && (
                    <div className="selective-card__section">
                      <h4>Acciones recomendadas</h4>
                      <ul className="selective-list">
                        {exploratory.recommendations.slice(0, 4).map((rec, idx) => (
                          <li key={`${idx}-rec`}>{rec}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </>
              ) : (
                <div className="selective-card__content">
                  <p className="selective-card__empty">No fue necesario un Exploratory Scan.</p>
                </div>
              )}
            </article>
          </div>

          <div className="selective-panel__next-step">
            <strong>Siguiente paso recomendado:</strong> {nextStep}
          </div>
        </>
      )}
    </section>
  );
}
