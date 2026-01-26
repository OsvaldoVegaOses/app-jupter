import { useCallback, useEffect, useState } from "react";
import { apiFetch, apiFetchJson } from "../services/api";
import { logClient } from "../utils/clientLogger";
import type { ProjectEntry, EpistemicMode } from "../types";

interface ProjectsState {
  items: ProjectEntry[];
  loading: boolean;
  error: string | null;
}

interface UseProjectsResult {
  state: ProjectsState;
  reload: () => Promise<void>;
  create: (input: { name: string; description?: string; epistemic_mode?: EpistemicMode }) => Promise<ProjectEntry | null>;
  update: (projectId: string, input: { name?: string; description?: string; epistemic_mode?: EpistemicMode }) => Promise<ProjectEntry | null>;
  deleteProject: (projectId: string) => Promise<boolean>;
  exportProject: (projectId: string) => Promise<boolean>;
}

const slugify = (value: string): string =>
  value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "") || "default";

const suggestUniqueName = (name: string, existingIds: Set<string>): string => {
  let suffix = 2;
  let candidate = name;
  let slug = slugify(candidate);
  while (existingIds.has(slug)) {
    candidate = `${name} ${suffix}`;
    slug = slugify(candidate);
    suffix += 1;
  }
  return candidate;
};

async function postJSON<T>(url: string, body: unknown): Promise<T> {
  return apiFetchJson<T>(url, {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export function useProjects(): UseProjectsResult {
  const [state, setState] = useState<ProjectsState>({
    items: [],
    loading: true,
    error: null
  });

  const load = useCallback(async () => {
    logClient("projects.load.start");
    setState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const payload = await apiFetchJson<{ projects?: ProjectEntry[] }>("/api/projects");
      logClient("projects.load.success", { count: payload.projects?.length ?? 0 });
      setState({
        items: payload.projects ?? [],
        loading: false,
        error: null
      });
    } catch (error) {
      logClient(
        "projects.load.error",
        { message: error instanceof Error ? error.message : String(error) },
        "error"
      );
      setState({
        items: [],
        loading: false,
        error: error instanceof Error ? error.message : "Error desconocido"
      });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const create = useCallback(
    async (input: { name: string; description?: string; epistemic_mode?: EpistemicMode }) => {
      const trimmedName = input.name.trim();
      const existingIds = new Set(state.items.map((item) => item.id));
      const slug = slugify(trimmedName);
      if (existingIds.has(slug)) {
        const suggestion = suggestUniqueName(trimmedName, existingIds);
        const message = `Ya existe un proyecto con el identificador '${slug}'. Cree un proyecto con diferente nombre. Sugerencia: "${suggestion}".`;
        logClient("projects.create.duplicate", { name: trimmedName, slug, suggestion }, "warn");
        setState((prev) => ({ ...prev, error: message }));
        throw new Error(message);
      }

      try {
        logClient("projects.create.start", { name: trimmedName, slug, epistemic_mode: input.epistemic_mode });
        const result = await postJSON<ProjectEntry>("/api/projects", {
          name: trimmedName,
          description: input.description,
          epistemic_mode: input.epistemic_mode || "constructivist"
        });
        logClient("projects.create.success", { id: result.id, name: result.name });
        // Refresh the project list to show the new project
        logClient("projects.create.refreshing_list");
        await load();
        logClient("projects.create.list_refreshed", { itemCount: state.items.length + 1 });
        return result;
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error);
        logClient(
          "projects.create.error",
          { name: trimmedName, message: errorMsg },
          "error"
        );
        
        // Si el error menciona "Ya existe", recargar lista por si se creó pero no se mostró
        if (errorMsg.includes("Ya existe") || errorMsg.includes("already exists")) {
          logClient("projects.create.reloading_after_duplicate_error");
          await load();
        }
        
        setState((prev) => ({
          ...prev,
          error: errorMsg
        }));
        throw error;
      }
    },
    [load, state.items]
  );

  const update = useCallback(
    async (projectId: string, input: { name?: string; description?: string; epistemic_mode?: EpistemicMode }) => {
      try {
        logClient("projects.update.start", { projectId, updates: Object.keys(input) });
        const { epistemic_mode, ...details } = input;

        // Dedicated endpoint for epistemic_mode (guarded server-side).
        if (epistemic_mode) {
          await apiFetchJson<{ project_id: string; epistemic_mode: string; changed: boolean; message?: string }>(
            `/api/projects/${encodeURIComponent(projectId)}/epistemic-mode`,
            {
              method: "PUT",
              body: JSON.stringify({ epistemic_mode })
            }
          );
        }

        let patched: ProjectEntry | null = null;
        const hasDetails = Object.keys(details).some((k) => (details as any)[k] !== undefined);
        if (hasDetails) {
          patched = await apiFetchJson<ProjectEntry>(
            `/api/projects/${encodeURIComponent(projectId)}`,
            {
              method: "PATCH",
              body: JSON.stringify(details)
            }
          );
        }

        // Reload list so UI reflects epistemic_mode changes too.
        const payload = await apiFetchJson<{ projects?: ProjectEntry[] }>("/api/projects");
        setState({
          items: payload.projects ?? [],
          loading: false,
          error: null
        });

        const refreshed = (payload.projects ?? []).find((p) => p.id === projectId) ?? null;
        logClient("projects.update.success", { projectId });
        return refreshed ?? patched;
      } catch (error) {
        logClient(
          "projects.update.error",
          { projectId, message: error instanceof Error ? error.message : String(error) },
          "error"
        );
        setState((prev) => ({
          ...prev,
          error: error instanceof Error ? error.message : "Error actualizando proyecto"
        }));
        return null;
      }
    },
    []
  );

  const deleteProject = useCallback(
    async (projectId: string): Promise<boolean> => {
      try {
        logClient("projects.delete.start", { projectId });
        await apiFetch(`/api/projects/${encodeURIComponent(projectId)}`, {
          method: "DELETE"
        });
        logClient("projects.delete.success", { projectId });
        await load();
        return true;
      } catch (error) {
        logClient(
          "projects.delete.error",
          { projectId, message: error instanceof Error ? error.message : String(error) },
          "error"
        );
        setState((prev) => ({
          ...prev,
          error: error instanceof Error ? error.message : "Error eliminando proyecto"
        }));
        return false;
      }
    },
    [load]
  );

  const exportProject = useCallback(
    async (projectId: string): Promise<boolean> => {
      try {
        const response = await apiFetch(`/api/projects/${encodeURIComponent(projectId)}/export`);
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${projectId}_backup.zip`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        return true;
      } catch (error) {
        setState((prev) => ({
          ...prev,
          error: error instanceof Error ? error.message : "Error exportando proyecto"
        }));
        return false;
      }
    },
    []
  );

  return { state, reload: load, create, update, deleteProject, exportProject };
}
