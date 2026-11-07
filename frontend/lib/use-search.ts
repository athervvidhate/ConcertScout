import { useCallback, useEffect, useRef, useState } from "react";

import {
  type Candidates,
  type Interpreted,
  NEEDS_A_NEW_SEARCH,
  type Recommendation,
  SearchRefused,
  streamSearch,
} from "@/lib/search";

export type SearchState = {
  phase: "idle" | "searching" | "finished";
  searched: string;
  status: string | null;
  interpreted: Interpreted | null;
  candidates: Candidates | null;
  recommendations: Recommendation[];
  hasPoster: boolean;
  error: string | null;
  retryable: boolean;
};

const IDLE: SearchState = {
  phase: "idle",
  searched: "",
  status: null,
  interpreted: null,
  candidates: null,
  recommendations: [],
  hasPoster: false,
  error: null,
  retryable: true,
};

const DROPPED = "The connection dropped before the Search finished.";
const UNREACHABLE = "Concert Scout's API is not responding.";

export function useSearch() {
  const [state, setState] = useState(IDLE);
  const current = useRef<AbortController | null>(null);

  useEffect(() => () => current.current?.abort(), []);

  const search = useCallback(async (text: string, token: string) => {
    current.current?.abort();
    const controller = new AbortController();
    current.current = controller;
    setState({ ...IDLE, phase: "searching", searched: text });

    let finished = false;
    let error: string | null = null;
    let retryable = true;
    try {
      for await (const { event, data } of streamSearch(text, token, controller.signal)) {
        if (event === "status") {
          setState((state) => ({ ...state, status: data.message }));
        } else if (event === "interpreted") {
          setState((state) => ({ ...state, interpreted: data }));
        } else if (event === "candidates") {
          setState((state) => ({ ...state, candidates: data }));
        } else if (event === "poster") {
          setState((state) => ({ ...state, hasPoster: true, recommendations: data.recommendations }));
        } else if (event === "done") {
          finished = true;
        } else if (event === "error") {
          error = data.message;
          retryable = !NEEDS_A_NEW_SEARCH.includes(data.code) && data.retry_after === undefined;
        }
      }
      if (!finished) error = DROPPED;
    } catch (caught) {
      if (controller.signal.aborted) return;
      error = caught instanceof TypeError ? UNREACHABLE : (caught as Error).message;
      if (caught instanceof SearchRefused) retryable = caught.retryable;
    }
    if (controller.signal.aborted) return;
    setState((state) => ({ ...state, phase: "finished", status: null, error, retryable }));
  }, []);

  return { ...state, search };
}
