/**
 * @fileoverview Componente ActionSuggestionCard para Sprint 17.
 * 
 * Muestra sugerencia de código IA con:
 * - Código propuesto editable
 * - Memo generado por IA editable
 * - Lista de fragmentos seleccionados con scores
 * - Acciones: Enviar a Bandeja, Regenerar, Cancelar
 */

import { useState } from "react";

interface SelectedFragment {
    fragmento_id: string;
    archivo: string;
    fragmento: string;
    score: number;
}

interface ActionSuggestionCardProps {
    suggestedCode: string;
    memo: string;
    confidence: "alta" | "media" | "baja" | "ninguna";
    selectedFragments: SelectedFragment[];
    isSubmitting: boolean;
    isSavingMemo?: boolean;
    onCodeChange: (code: string) => void;
    onMemoChange: (memo: string) => void;
    onSubmit: () => void;
    onRegenerate: () => void;
    onCancel: () => void;
    onSaveMemo?: () => void;
}

export function ActionSuggestionCard({
    suggestedCode,
    memo,
    confidence,
    selectedFragments,
    isSubmitting,
    isSavingMemo,
    onCodeChange,
    onMemoChange,
    onSubmit,
    onRegenerate,
    onCancel,
    onSaveMemo,
}: ActionSuggestionCardProps) {
    const [isExpanded, setIsExpanded] = useState(true);

    const confidenceStyles = {
        alta: { bg: "#dcfce7", border: "#22c55e", text: "#166534", emoji: "🟢" },
        media: { bg: "#fef9c3", border: "#eab308", text: "#854d0e", emoji: "🟡" },
        baja: { bg: "#fee2e2", border: "#ef4444", text: "#991b1b", emoji: "🔴" },
        ninguna: { bg: "#f3f4f6", border: "#9ca3af", text: "#374151", emoji: "⚪" },
    };

    const style = confidenceStyles[confidence] || confidenceStyles.ninguna;

    return (
        <div
            className="action-suggestion-card"
            style={{
                background: `linear-gradient(135deg, ${style.bg}, white)`,
                border: `2px solid ${style.border}`,
                borderRadius: "12px",
                padding: "1rem",
                marginBottom: "1rem",
                boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.1)",
            }}
        >
            {/* Header */}
            <header
                style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    marginBottom: "1rem",
                    cursor: "pointer",
                }}
                onClick={() => setIsExpanded(!isExpanded)}
            >
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <span style={{ fontSize: "1.5rem" }}>💡</span>
                    <h3 style={{ margin: 0, color: style.text }}>
                        Sugerencia de Acción
                    </h3>
                    <span
                        style={{
                            fontSize: "0.75rem",
                            padding: "2px 8px",
                            borderRadius: "9999px",
                            background: style.border,
                            color: "white",
                        }}
                    >
                        {style.emoji} Confianza {confidence}
                    </span>
                </div>
                <button
                    type="button"
                    style={{
                        background: "none",
                        border: "none",
                        fontSize: "1.25rem",
                        cursor: "pointer",
                    }}
                >
                    {isExpanded ? "▼" : "▶"}
                </button>
            </header>

            {isExpanded && (
                <>
                    {/* Código propuesto */}
                    <div style={{ marginBottom: "1rem" }}>
                        <label
                            style={{
                                display: "block",
                                fontWeight: 600,
                                marginBottom: "0.25rem",
                                color: style.text,
                            }}
                        >
                            📝 Código propuesto:
                        </label>
                        <input
                            type="text"
                            value={suggestedCode}
                            onChange={(e) => onCodeChange(e.target.value)}
                            style={{
                                width: "100%",
                                padding: "0.5rem 0.75rem",
                                border: `1px solid ${style.border}`,
                                borderRadius: "0.375rem",
                                fontSize: "1rem",
                                fontFamily: "monospace",
                            }}
                            placeholder="nombre_del_codigo"
                        />
                    </div>

                    {/* Fragmentos seleccionados */}
                    <div style={{ marginBottom: "1rem" }}>
                        <label
                            style={{
                                display: "block",
                                fontWeight: 600,
                                marginBottom: "0.5rem",
                                color: style.text,
                            }}
                        >
                            📋 Fragmentos seleccionados ({selectedFragments.length}):
                        </label>
                        <div
                            style={{
                                maxHeight: "200px",
                                overflowY: "auto",
                                background: "white",
                                borderRadius: "0.375rem",
                                border: "1px solid #e5e7eb",
                            }}
                        >
                            {selectedFragments.map((frag, idx) => (
                                <div
                                    key={frag.fragmento_id}
                                    style={{
                                        padding: "0.5rem 0.75rem",
                                        borderBottom:
                                            idx < selectedFragments.length - 1
                                                ? "1px solid #e5e7eb"
                                                : "none",
                                        display: "flex",
                                        gap: "0.5rem",
                                        alignItems: "flex-start",
                                    }}
                                >
                                    <span
                                        style={{
                                            color: style.border,
                                            fontWeight: "bold",
                                            minWidth: "2rem",
                                        }}
                                    >
                                        [{idx + 1}]
                                    </span>
                                    <span
                                        style={{
                                            fontSize: "0.75rem",
                                            color: "#6b7280",
                                            minWidth: "3rem",
                                        }}
                                    >
                                        {(frag.score * 100).toFixed(0)}%
                                    </span>
                                    <span style={{ flex: 1, fontSize: "0.875rem" }}>
                                        {frag.fragmento?.slice(0, 100)}...
                                    </span>
                                    <span
                                        style={{
                                            fontSize: "0.75rem",
                                            color: "#9ca3af",
                                            whiteSpace: "nowrap",
                                        }}
                                    >
                                        {frag.archivo}
                                    </span>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* Memo IA */}
                    <div style={{ marginBottom: "1rem" }}>
                        <label
                            style={{
                                display: "block",
                                fontWeight: 600,
                                marginBottom: "0.25rem",
                                color: style.text,
                            }}
                        >
                            📝 Memo IA (editable):
                        </label>
                        <textarea
                            value={memo}
                            onChange={(e) => onMemoChange(e.target.value)}
                            rows={4}
                            style={{
                                width: "100%",
                                padding: "0.5rem 0.75rem",
                                border: `1px solid ${style.border}`,
                                borderRadius: "0.375rem",
                                fontSize: "0.875rem",
                                resize: "vertical",
                            }}
                            placeholder="Justificación del agrupamiento..."
                        />
                    </div>

                    {/* Acciones */}
                    <footer
                        style={{
                            display: "flex",
                            gap: "0.75rem",
                            justifyContent: "flex-end",
                            flexWrap: "wrap",
                        }}
                    >
                        {onSaveMemo && (
                            <button
                                type="button"
                                onClick={onSaveMemo}
                                disabled={isSavingMemo || !memo.trim()}
                                style={{
                                    padding: "0.5rem 1rem",
                                    background: isSavingMemo ? "#9ca3af" : "linear-gradient(135deg, #0891b2, #06b6d4)",
                                    color: "white",
                                    border: "none",
                                    borderRadius: "0.375rem",
                                    cursor: isSavingMemo || !memo.trim() ? "not-allowed" : "pointer",
                                    fontWeight: 500,
                                }}
                            >
                                {isSavingMemo ? "💾 Guardando..." : "💾 Guardar Memo"}
                            </button>
                        )}
                        <button
                            type="button"
                            onClick={onCancel}
                            style={{
                                padding: "0.5rem 1rem",
                                background: "white",
                                border: "1px solid #d1d5db",
                                borderRadius: "0.375rem",
                                cursor: "pointer",
                            }}
                        >
                            ✕ Cancelar
                        </button>
                        <button
                            type="button"
                            onClick={onRegenerate}
                            disabled={isSubmitting}
                            style={{
                                padding: "0.5rem 1rem",
                                background: "#f3f4f6",
                                border: "1px solid #9ca3af",
                                borderRadius: "0.375rem",
                                cursor: isSubmitting ? "not-allowed" : "pointer",
                            }}
                        >
                            🔄 Regenerar
                        </button>
                        <button
                            type="button"
                            onClick={onSubmit}
                            disabled={isSubmitting || !suggestedCode.trim()}
                            style={{
                                padding: "0.5rem 1.25rem",
                                background: isSubmitting ? "#9ca3af" : style.border,
                                color: "white",
                                border: "none",
                                borderRadius: "0.375rem",
                                cursor:
                                    isSubmitting || !suggestedCode.trim()
                                        ? "not-allowed"
                                        : "pointer",
                                fontWeight: 600,
                            }}
                        >
                            {isSubmitting
                                ? "Enviando..."
                                : `✓ Enviar a Bandeja (${selectedFragments.length})`}
                        </button>
                    </footer>
                </>
            )}
        </div>
    );
}

export default ActionSuggestionCard;
