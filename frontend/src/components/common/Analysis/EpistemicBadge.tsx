import React from "react";

export type EpistemicType = "OBSERVATION" | "INTERPRETATION" | "HYPOTHESIS" | "NORMATIVE_INFERENCE";

function styleForType(type: string): React.CSSProperties {
  const t = (type || "").toUpperCase();
  if (t === "OBSERVATION") return { background: "#dcfce7", color: "#166534" };
  if (t === "INTERPRETATION") return { background: "#dbeafe", color: "#1e40af" };
  if (t === "HYPOTHESIS") return { background: "#fde68a", color: "#92400e" };
  if (t === "NORMATIVE_INFERENCE") return { background: "#fbcfe8", color: "#9d174d" };
  return { background: "#e5e7eb", color: "#374151" };
}

export function EpistemicBadge({ type }: { type: string }) {
  const style = styleForType(type);
  return (
    <span
      style={{
        ...style,
        borderRadius: "999px",
        padding: "0.15rem 0.5rem",
        fontSize: "0.75rem",
        fontWeight: 700,
        display: "inline-flex",
        alignItems: "center",
        gap: "0.25rem",
      }}
      title={type}
    >
      {String(type || "").toUpperCase()}
    </span>
  );
}
