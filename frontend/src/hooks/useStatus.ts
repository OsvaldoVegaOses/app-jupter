import { useCallback, useEffect, useState } from "react";
import { apiFetchJson } from "../services/api";
import type { StatusSnapshot } from "../types";

interface StatusState {
  data: StatusSnapshot | null;
  loading: boolean;
  error: string | null;
}

export function useStatus(project: string): [StatusState, () => void] {
  const [state, setState] = useState<StatusState>({
    data: null,
    loading: true,
    error: null
  });

  const load = useCallback(async () => {
    setState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const payload = await apiFetchJson<StatusSnapshot>(
        `/api/status?project=${encodeURIComponent(project)}`
      );
      setState({ data: payload, loading: false, error: null });
    } catch (error) {
      setState({
        data: null,
        loading: false,
        error: error instanceof Error ? error.message : "Error desconocido"
      });
    }
  }, [project]);

  useEffect(() => {
    void load();
  }, [load]);

  return [state, load];
}
