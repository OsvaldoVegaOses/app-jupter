import type { LogHint } from "../types";

export function formatLogHint(logHint: LogHint | string | undefined): string {
  if (!logHint) {
    return "-";
  }
  if (typeof logHint === "string") {
    return logHint || "-";
  }
  const path = typeof logHint.path === "string" ? logHint.path : "";
  const modified = typeof logHint.modified_at === "string" ? logHint.modified_at : "";
  if (path && modified) {
    return `${path} (modificado ${modified})`;
  }
  if (path) {
    return path;
  }
  if (modified) {
    return `modificado ${modified}`;
  }
  return "-";
}

export function normaliseArtifacts(payload: unknown): string[] {
  if (!payload) {
    return [];
  }
  const rawList = Array.isArray(payload) ? payload : [payload];
  return rawList
    .map((item) => {
      if (item === null || item === undefined) {
        return "";
      }
      if (typeof item === "string") {
        return item;
      }
      if (typeof item === "object") {
        const entry = item as Record<string, unknown>;
        const label = typeof entry.label === "string" ? entry.label : "";
        const details = Object.entries(entry)
          .filter(([key, value]) => key !== "label" && value !== null && value !== undefined && value !== "")
          .map(([key, value]) => `${key}=${value}`);
        if (label && details.length) {
          return `${label}: ${details.join(", ")}`;
        }
        if (label) {
          return label;
        }
        if (details.length) {
          return details.join(", ");
        }
      }
      return String(item);
    })
    .filter((text) => text.length > 0);
}

export function formatCommand(command?: string, subcommand?: string): string {
  if (command && subcommand) {
    return `${command}:${subcommand}`;
  }
  if (command) {
    return command;
  }
  if (subcommand) {
    return subcommand;
  }
  return "-";
}

export function formatPercentage(value: number | string | null | undefined, decimals = 1): string {
  if (value === null || value === undefined) {
    return "-";
  }
  const numeric = typeof value === "string" ? Number(value) : value;
  if (Number.isNaN(numeric)) {
    return "-";
  }
  const percentage = Math.max(0, Math.min(1, numeric));
  return `${(percentage * 100).toFixed(decimals)}%`;
}
