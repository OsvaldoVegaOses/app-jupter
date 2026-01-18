import React, { useEffect, useRef } from "react";
import "./ConfirmModal.css";
import "./CodeHistoryModal.css";

import type { CodeHistoryEntry } from "../services/api";

interface CodeHistoryModalProps {
  isOpen: boolean;
  codigo: string;
  loading: boolean;
  error?: string | null;
  history: CodeHistoryEntry[];
  onClose: () => void;
}

function formatDate(value: string | null): string {
  if (!value) return "-";
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return value;
  return dt.toLocaleString();
}

export function CodeHistoryModal({
  isOpen,
  codigo,
  loading,
  error,
  history,
  onClose,
}: CodeHistoryModalProps) {
  const closeBtnRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    closeBtnRef.current?.focus();

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };

    document.addEventListener("keydown", handleKeyDown);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "";
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="confirm-modal-overlay" onClick={onClose}>
      <div
        className="confirm-modal code-history-modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="code-history-title"
      >
        <header className="confirm-modal__header">
          <span className="confirm-modal__icon">🕒</span>
          <h2 id="code-history-title" className="confirm-modal__title">
            Historial del código: {codigo}
          </h2>
        </header>

        <div className="confirm-modal__body">
          {loading && <p className="confirm-modal__message">Cargando historial...</p>}
          {!loading && error && (
            <p className="confirm-modal__message" style={{ color: "#b91c1c" }}>
              {error}
            </p>
          )}

          {!loading && !error && history.length === 0 && (
            <p className="confirm-modal__message code-history-modal__muted">
              No hay entradas de historial para este código.
            </p>
          )}

          {!loading && !error && history.length > 0 && (
            <div className="code-history-modal__scroll">
              <table className="code-history-modal__table">
                <thead>
                  <tr>
                    <th>Versión</th>
                    <th>Acción</th>
                    <th>Changed by</th>
                    <th>Fecha</th>
                    <th>Antes</th>
                    <th>Después</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((h) => (
                    <tr key={h.id}>
                      <td>
                        <span className="code-history-modal__badge">v{h.version}</span>
                      </td>
                      <td>{h.accion}</td>
                      <td className="code-history-modal__muted">{h.changed_by || "-"}</td>
                      <td className="code-history-modal__muted">{formatDate(h.created_at)}</td>
                      <td>{h.memo_anterior || "-"}</td>
                      <td>{h.memo_nuevo || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <footer className="confirm-modal__footer">
          <button
            type="button"
            ref={closeBtnRef}
            className="confirm-modal__btn confirm-modal__btn--primary"
            onClick={onClose}
          >
            Cerrar
          </button>
        </footer>
      </div>
    </div>
  );
}
