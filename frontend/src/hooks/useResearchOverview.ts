import { useEffect, useState } from "react";
import { apiFetchJson } from "../services/api";

export type ResearchOverview = {
  project: string;
  generated_at: string;
  availability: { postgres: boolean };
  validated: any | null;
  observed: any | null;
  discovery: any | null;
  panorama?: {
    project: string;
    current_stage?: { key?: string | null; label?: string | null } | null;
    primary_action?: {
      id: string;
      label: string;
      view: string;
      subview?: string | null;
      params?: Record<string, any>;
      reason?: string;
      score?: number;
    } | null;
    secondary_actions?: Array<{
      id: string;
      label: string;
      view: string;
      subview?: string | null;
      params?: Record<string, any>;
      reason?: string;
      score?: number;
    }>;
    axial_gate?: {
      status: "locked" | "unlocked";
      policy_used?: string;
      reasons?: string[];
      unlock_hint?: string | null;
      metrics?: Record<string, any>;
    } | null;
    signals?: Record<string, any>;
    saturation?: Record<string, any> | null;
  } | null;
  warnings: string[];
};

type State = {
  loading: boolean;
  error: string | null;
  data: ResearchOverview | null;
};

export function useResearchOverview(project: string, refreshKey: number = 0) {
  const [state, setState] = useState<State>({ loading: false, error: null, data: null });

  useEffect(() => {
    let cancelled = false;

    async function load() {
      if (!project) {
        setState({ loading: false, error: null, data: null });
        return;
      }
      setState((prev) => ({ ...prev, loading: true, error: null }));
      try {
        const result = await apiFetchJson<ResearchOverview>(
          `/api/research/overview?project=${encodeURIComponent(project)}`
        );
        if (!cancelled) {
          setState({ loading: false, error: null, data: result });
        }
      } catch (err: any) {
        if (!cancelled) {
          setState({ loading: false, error: err?.message ?? String(err), data: null });
        }
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [project, refreshKey]);

  return state;
}
