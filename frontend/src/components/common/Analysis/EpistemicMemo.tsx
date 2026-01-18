import React from "react";
import { EpistemicBadge } from "./EpistemicBadge";

export interface EpistemicStatement {
  type: string;
  text: string;
  evidence_ids?: number[];
  evidence?: {
    node_ids?: string[];
    relationship_ids?: string[];
  };
}

export function EpistemicMemo({
  statements,
  onSelect,
  selectedId,
}: {
  statements: EpistemicStatement[];
  onSelect?: (st: EpistemicStatement) => void;
  selectedId?: string | null;
}) {
  if (!statements || statements.length === 0) return null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
      {statements.map((st, idx) => {
        const id = (st as any).id ? String((st as any).id) : `item_${idx}`;
        const isSelected = selectedId ? selectedId === id : false;
        const clickable = typeof onSelect === "function";

        return (
          <button
            key={id}
            type="button"
            onClick={clickable ? () => onSelect(st) : undefined}
            style={{
              textAlign: "left",
              border: `1px solid ${isSelected ? "#2563eb" : "#e5e7eb"}`,
              background: isSelected ? "#eff6ff" : "#ffffff",
              borderRadius: "0.5rem",
              padding: "0.6rem 0.75rem",
              cursor: clickable ? "pointer" : "default",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.35rem" }}>
              <EpistemicBadge type={st.type} />
              {Array.isArray(st.evidence_ids) && st.evidence_ids.length > 0 && (
                <span style={{ fontSize: "0.75rem", color: "#64748b" }}>
                  evid: {st.evidence_ids.join(", ")}
                </span>
              )}
            </div>
            <div style={{ color: "#0f172a", lineHeight: 1.35 }}>{st.text}</div>
          </button>
        );
      })}
    </div>
  );
}
