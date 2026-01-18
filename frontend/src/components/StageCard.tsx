import { formatCommand, formatLogHint, normaliseArtifacts } from "../utils/format";
import type { StageEntry } from "../types";

interface StageCardProps {
  index: number;
  stageKey: string;
  entry: StageEntry;
  onComplete?: (stageKey: string) => void;
  completing?: boolean;
}

const statusStyle = (completed: boolean) =>
  completed
    ? { backgroundColor: "#16a34a", color: "#f8fafc" }
    : { backgroundColor: "#ea580c", color: "#f8fafc" };

export function StageCard({ index, stageKey, entry, onComplete, completing }: StageCardProps) {
  const artifacts = normaliseArtifacts(entry.artifacts);
  const completed = Boolean(entry.completed);
  const badgeStyle = statusStyle(completed);
  const canComplete = Boolean(onComplete) && !completed;

  const handleComplete = () => {
    if (onComplete && !completed) {
      onComplete(stageKey);
    }
  };

  return (
    <article className="stage-card">
      <header className="stage-card__header">
        <div className="stage-card__index">{index.toString().padStart(2, "0")}</div>
        <div>
          <h2 className="stage-card__title">{entry.label || stageKey}</h2>
          <span className="stage-card__badge" style={badgeStyle}>
            {completed ? "Completa" : "Pendiente"}
          </span>
        </div>
      </header>
      <dl className="stage-card__meta">
        <div>
          <dt>Ultimo run_id</dt>
          <dd>{entry.last_run_id || "-"}</dd>
        </div>
        <div>
          <dt>Actualizado</dt>
          <dd>{entry.updated_at || "-"}</dd>
        </div>
        <div>
          <dt>Ultimo comando</dt>
          <dd>{formatCommand(entry.command as string | undefined, entry.subcommand as string | undefined)}</dd>
        </div>
        <div>
          <dt>Verificacion</dt>
          <dd>{entry.verify || "-"}</dd>
        </div>
        <div>
          <dt>Log</dt>
          <dd>{formatLogHint(entry.log_hint)}</dd>
        </div>
      </dl>
      {artifacts.length > 0 && (
        <section className="stage-card__artifacts">
          <h3>Evidencia</h3>
          <ul>
            {artifacts.map((item, idx) => (
              <li key={`${stageKey}-artifact-${idx}`}>{item}</li>
            ))}
          </ul>
        </section>
      )}
      {entry.notes && (
        <section className="stage-card__notes">
          <h3>Notas</h3>
          <p>{entry.notes}</p>
        </section>
      )}
      {entry.verify && (
        <section className="stage-card__notes">
          <h3>Comando sugerido</h3>
          <p className="stage-card__command">{entry.verify}</p>
        </section>
      )}
      {canComplete && (
        <div className="stage-card__actions">
          <button onClick={handleComplete} disabled={Boolean(completing)}>
            {completing ? "Marcando..." : "Marcar etapa como completada"}
          </button>
        </div>
      )}
    </article>
  );
}
