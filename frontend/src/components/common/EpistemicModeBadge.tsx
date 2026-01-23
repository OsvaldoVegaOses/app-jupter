/**
 * @fileoverview Badge indicator for project epistemic mode.
 * 
 * Displays the epistemological paradigm (Constructivist/Post-positivist)
 * configured for a project, with distinct colors for visual differentiation.
 * 
 * - Constructivist (Charmaz): Purple badge - reflexivity, in-vivo, gerunds
 * - Post-positivist (Glaser/Strauss): Blue badge - abstraction, paradigm model
 * 
 * @module EpistemicModeBadge
 */

import React from "react";

export type EpistemicMode = "constructivist" | "post_positivist";

interface EpistemicModeBadgeProps {
  mode: EpistemicMode | string | undefined | null;
  size?: "sm" | "md" | "lg";
  showLabel?: boolean;
}

const MODES: Record<EpistemicMode, { label: string; shortLabel: string; color: string; bg: string; description: string }> = {
  constructivist: {
    label: "Constructivista",
    shortLabel: "CONST",
    color: "#7c3aed",  // Purple
    bg: "#ede9fe",     // Purple light
    description: "Enfoque Charmaz: gerundios, códigos in-vivo, reflexividad"
  },
  post_positivist: {
    label: "Post-positivista",
    shortLabel: "P-POS",
    color: "#1d4ed8",  // Blue
    bg: "#dbeafe",     // Blue light
    description: "Enfoque Glaser/Strauss: abstracción, modelo paradigmático"
  }
};

/**
 * Badge indicating the epistemic mode of a project.
 */
export function EpistemicModeBadge({ 
  mode, 
  size = "md",
  showLabel = true 
}: EpistemicModeBadgeProps): React.ReactElement | null {
  // Normalize mode
  const normalizedMode = (mode || "constructivist").toLowerCase() as EpistemicMode;
  const config = MODES[normalizedMode] || MODES.constructivist;
  
  const sizeStyles: Record<string, React.CSSProperties> = {
    sm: { fontSize: "0.65rem", padding: "0.1rem 0.35rem" },
    md: { fontSize: "0.75rem", padding: "0.15rem 0.5rem" },
    lg: { fontSize: "0.85rem", padding: "0.2rem 0.6rem" }
  };

  return (
    <span
      style={{
        background: config.bg,
        color: config.color,
        borderRadius: "999px",
        fontWeight: 700,
        display: "inline-flex",
        alignItems: "center",
        gap: "0.25rem",
        whiteSpace: "nowrap",
        ...sizeStyles[size]
      }}
      title={config.description}
      data-testid="epistemic-mode-badge"
    >
      {showLabel ? config.label : config.shortLabel}
    </span>
  );
}

/**
 * Icon for epistemic mode (compact display).
 */
export function EpistemicModeIcon({ mode }: { mode: EpistemicMode | string | undefined | null }): React.ReactElement {
  const normalizedMode = (mode || "constructivist").toLowerCase() as EpistemicMode;
  const isConstructivist = normalizedMode === "constructivist";
  
  return (
    <span
      style={{
        fontSize: "1rem",
        display: "inline-flex",
        alignItems: "center"
      }}
      title={isConstructivist ? "Constructivista (Charmaz)" : "Post-positivista (Glaser/Strauss)"}
    >
      {isConstructivist ? "🔮" : "📐"}
    </span>
  );
}

export default EpistemicModeBadge;
