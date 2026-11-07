import { useCallback, useEffect, useRef, useState } from "react";

import { type Recommendation, streamSearch } from "@/lib/search";

export type SearchState = {
  phase: "idle" | "searching" | "finished";
  city: string;
  status: string | null;
  recommendations: Recommendation[];
  error: string | null;
};

const IDLE: SearchState = {
  phase: "idle",
  city: "",
  status: null,
  recommendations: [],
  error: null,
};

const DROPPED = "The connection dropped before the Search finished.";
const UNREACHABLE = "Concert Scout's API is not responding.";

export function useSearch() {
  const [state, setState] = useState(IDLE);
  const current = useRef<AbortController | null>(null);

  useEffect(() => () => current.current?.abort(), []);

  const search = useCallback(async (city: string) => {
    current.current?.abort();
    const controller = new AbortController();
    current.current = controller;
    setState({ ...IDLE, phase: "searching", city });

    let finished = false;
    let error: string | null = null;
    try {
      for await (const { event, data } of streamSearch(city, controller.signal)) {
        if (event === "status") {
          setState((state) => ({ ...state, status: data.message }));
        } else if (event === "poster") {
          setState((state) => ({ ...state, recommendations: data.recommendations }));
        } else if (event === "error") {
          error = data.message;
        } else {
          finished = true;
        }
      }
      if (!finished) error = DROPPED;
    } catch (caught) {
      if (controller.signal.aborted) return;
      error = caught instanceof TypeError ? UNREACHABLE : (caught as Error).message;
    }
    if (controller.signal.aborted) return;
    setState((state) => ({ ...state, phase: "finished", status: null, error }));
  }, []);

  return { ...state, search };
}
