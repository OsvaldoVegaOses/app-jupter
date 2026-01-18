type LogLevel = "info" | "warn" | "error";

type LogEntry = {
  ts: string;
  level: LogLevel;
  event: string;
  data?: Record<string, unknown>;
};

const STORAGE_KEY = "app_frontend_logs";
const MAX_ENTRIES = 300;

function safeRead(): LogEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as LogEntry[]) : [];
  } catch {
    return [];
  }
}

function safeWrite(entries: LogEntry[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entries.slice(-MAX_ENTRIES)));
  } catch {
    // ignore storage errors
  }
}

export function logClient(event: string, data?: Record<string, unknown>, level: LogLevel = "info"): void {
  const entry: LogEntry = {
    ts: new Date().toISOString(),
    level,
    event,
    data,
  };

  if (level === "error") {
    console.error("[client]", event, data ?? "");
  } else if (level === "warn") {
    console.warn("[client]", event, data ?? "");
  } else {
    console.log("[client]", event, data ?? "");
  }

  const entries = safeRead();
  entries.push(entry);
  safeWrite(entries);
}

export function readClientLogs(): LogEntry[] {
  return safeRead();
}

export function clearClientLogs(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
}
