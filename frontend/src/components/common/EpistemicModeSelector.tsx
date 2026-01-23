/**
 * @fileoverview Selector component for choosing epistemic mode.
 * 
 * Radio group for selecting the epistemological paradigm when creating
 * or editing a project. Includes descriptions to help users choose.
 * 
 * @module EpistemicModeSelector
 */

import React from "react";

export type EpistemicMode = "constructivist" | "post_positivist";

interface EpistemicModeSelectorProps {
  value: EpistemicMode;
  onChange: (mode: EpistemicMode) => void;
  disabled?: boolean;
  compact?: boolean;
}

const OPTIONS: Array<{
  value: EpistemicMode;
  label: string;
  description: string;
  author: string;
}> = [
  {
    value: "constructivist",
    label: "Constructivista",
    description: "Códigos en gerundio, in-vivo, memos reflexivos",
    author: "Charmaz"
  },
  {
    value: "post_positivist",
    label: "Post-positivista",
    description: "Abstracción temprana, modelo paradigmático",
    author: "Glaser/Strauss"
  }
];

/**
 * Radio group for selecting epistemic mode.
 */
export function EpistemicModeSelector({
  value,
  onChange,
  disabled = false,
  compact = false
}: EpistemicModeSelectorProps): React.ReactElement {
  const containerStyle: React.CSSProperties = {
    display: "flex",
    flexDirection: compact ? "row" : "column",
    gap: compact ? "1rem" : "0.5rem"
  };

  const labelStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "flex-start",
    gap: "0.5rem",
    cursor: disabled ? "not-allowed" : "pointer",
    opacity: disabled ? 0.6 : 1,
    padding: compact ? "0" : "0.5rem",
    borderRadius: "0.375rem",
    border: "1px solid transparent"
  };

  const selectedStyle: React.CSSProperties = {
    ...labelStyle,
    background: "#f3f4f6",
    borderColor: "#d1d5db"
  };

  return (
    <div style={containerStyle}>
      {OPTIONS.map((option) => (
        <label
          key={option.value}
          style={value === option.value ? selectedStyle : labelStyle}
        >
          <input
            type="radio"
            name="epistemic-mode"
            value={option.value}
            checked={value === option.value}
            onChange={() => onChange(option.value)}
            disabled={disabled}
            style={{ marginTop: "0.2rem" }}
          />
          <div style={{ display: "flex", flexDirection: "column" }}>
            <span style={{ fontWeight: 600, fontSize: "0.875rem" }}>
              {option.label}
              <span style={{ fontWeight: 400, color: "#6b7280", marginLeft: "0.25rem" }}>
                ({option.author})
              </span>
            </span>
            {!compact && (
              <span style={{ fontSize: "0.75rem", color: "#6b7280" }}>
                {option.description}
              </span>
            )}
          </div>
        </label>
      ))}
    </div>
  );
}

export default EpistemicModeSelector;
