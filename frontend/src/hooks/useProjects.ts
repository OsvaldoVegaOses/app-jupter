import { useCallback, useEffect, useState } from "react";
import { apiFetch, apiFetchJson } from "../services/api";
import { logClient } from "../utils/clientLogger";
import type { ProjectEntry } from "../types";

interface ProjectsState {
  items: ProjectEntry[];
  loading: boolean;
  error: string | null;
}

interface UseProjectsResult {
  state: ProjectsState;
  reload: () => Promise<void>;
  create: (input: { name: string; description?: string }) => Promise<ProjectEntry | null>;
  update: (projectId: string, input: { name?: string; description?: string }) => Promise<ProjectEntry | null>;
  deleteProject: (projectId: string) => Promise<boolean>;
  exportProject: (projectId: string) => Promise<boolean>;
}

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
    async (input: { name: string; description?: string }) => {
      try {
        logClient("projects.create.start", { name: input.name });
        const result = await postJSON<ProjectEntry>("/api/projects", input);
        logClient("projects.create.success", { id: result.id, name: result.name });
        await load();
        return result;
      } catch (error) {
        logClient(
          "projects.create.error",
          { name: input.name, message: error instanceof Error ? error.message : String(error) },
          "error"
        );
        setState((prev) => ({
          ...prev,
          error: error instanceof Error ? error.message : "Error desconocido"
        }));
        return null;
      }
    },
    [load]
  );

  const update = useCallback(
    async (projectId: string, input: { name?: string; description?: string }) => {
      try {
        logClient("projects.update.start", { projectId, updates: Object.keys(input) });
        const result = await apiFetchJson<ProjectEntry>(
          `/api/projects/${encodeURIComponent(projectId)}`,
          {
            method: "PATCH",
            body: JSON.stringify(input)
          }
        );
        logClient("projects.update.success", { projectId });
        await load();
        return result;
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
    [load]
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
