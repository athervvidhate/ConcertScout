import { useCallback, useEffect, useRef, useState } from "react";

import {
  type Asked,
  type Candidates,
  type Coordinates,
  type Elsewhere,
  type Reading,
  NEEDS_A_NEW_SEARCH,
  type Recommendation,
  SearchRefused,
  streamSearch,
  UNREACHABLE,
} from "@/lib/search";
import { forgetSearch, keepSearch, readSearch } from "@/lib/search-session";

export type SearchState = {
  phase: "idle" | "searching" | "finished";
  // Counts Searches, because running the same text again is still a new Poster.
  run: number;
  // The words typed for this Search. A corrected Reading keeps the words it corrects.
  searched: string;
  // What the latest Search sent, so Try again and a reload repeat it exactly.
  asked: Asked | null;
  status: string | null;
  step: string | null;
  reading: Reading | null;
  candidates: Candidates | null;
  recommendations: Recommendation[];
  hasPoster: boolean;
  // Names this Poster to the server, which alone can turn it into a Shared Poster.
  searchId: string | null;
  elsewhere: Elsewhere | null;
  error: string | null;
  retryable: boolean;
  // Restored after a reload, so the Poster shows at once instead of replaying its reveal.
  resumed: boolean;
};

const IDLE: SearchState = {
  phase: "idle",
  run: 0,
  searched: "",
  asked: null,
  status: null,
  step: null,
  reading: null,
  candidates: null,
  recommendations: [],
  hasPoster: false,
  searchId: null,
  elsewhere: null,
  error: null,
  retryable: true,
  resumed: false,
};

const DROPPED = "The connection dropped before the Search finished.";
const RELOADED = "The page reloaded before the Search finished.";

// A stream cannot continue across a reload, so an unfinished Search becomes a retry.
function resume(kept: SearchState): SearchState {
  if (kept.phase !== "searching") return { ...kept, resumed: true };
  return {
    ...kept,
    phase: "finished",
    status: null,
    step: null,
    error: kept.hasPoster ? null : RELOADED,
    retryable: true,
    resumed: true,
  };
}

export function useSearch() {
  const [state, setState] = useState(IDLE);
  const current = useRef<AbortController | null>(null);

  useEffect(() => () => current.current?.abort(), []);

  useEffect(() => {
    const timer = setTimeout(() => {
      const kept = readSearch<SearchState>();
      if (kept?.run) setState(resume(kept));
      else forgetSearch();
    }, 0);
    return () => clearTimeout(timer);
  }, []);

  // Only a Search or an example counts runs, so the first idle render never erases a kept one.
  useEffect(() => {
    if (state.run) keepSearch(state);
  }, [state]);

  const search = useCallback(
    async (
      asked: Asked,
      token: string,
      taste: string[],
      near: Coordinates | null,
    ) => {
      current.current?.abort();
      const controller = new AbortController();
      current.current = controller;
      // A corrected Reading shows at once, so its chips never blink out while it runs.
      setState(({ run, searched }) => ({
        ...IDLE,
        phase: "searching",
        run: run + 1,
        searched: "text" in asked ? asked.text : searched,
        asked,
        reading: "reading" in asked ? asked.reading : null,
      }));

      let finished = false;
      let error: string | null = null;
      let retryable = true;
      try {
        for await (const { event, data } of streamSearch(
          asked,
          token,
          taste,
          near,
          controller.signal,
        )) {
          if (event === "status") {
            setState((state) => ({
              ...state,
              status: data.message,
              step: data.step,
            }));
          } else if (event === "reading") {
            setState((state) => ({ ...state, reading: data }));
          } else if (event === "candidates") {
            setState((state) => ({ ...state, candidates: data }));
          } else if (event === "poster") {
            setState((state) => ({
              ...state,
              hasPoster: true,
              recommendations: data.recommendations,
            }));
          } else if (event === "shareable") {
            setState((state) => ({ ...state, searchId: data.search_id }));
          } else if (event === "elsewhere") {
            setState((state) => ({ ...state, elsewhere: data }));
          } else if (event === "done") {
            finished = true;
          } else if (event === "error") {
            error = data.message;
            retryable =
              !NEEDS_A_NEW_SEARCH.includes(data.code) &&
              data.retry_after === undefined;
          }
        }
        if (!finished) error = DROPPED;
      } catch (caught) {
        if (controller.signal.aborted) return;
        error =
          caught instanceof TypeError ? UNREACHABLE : (caught as Error).message;
        if (caught instanceof SearchRefused) retryable = caught.retryable;
      }
      if (controller.signal.aborted) return;
      setState((state) => ({
        ...state,
        phase: "finished",
        status: null,
        step: null,
        error,
        retryable,
      }));
    },
    [],
  );

  const clear = useCallback(() => {
    current.current?.abort();
    forgetSearch();
    setState(IDLE);
  }, []);

  const showExample = useCallback(
    (example: {
      text: string;
      reading: Reading | null;
      candidates: Candidates | null;
      poster: { recommendations: Recommendation[] };
    }) => {
      current.current?.abort();
      setState(({ run }) => ({
        ...IDLE,
        run: run + 1,
        phase: "finished",
        searched: example.text,
        asked: { text: example.text },
        reading: example.reading,
        candidates: example.candidates,
        hasPoster: true,
        recommendations: example.poster.recommendations,
      }));
    },
    [],
  );

  return { ...state, search, clear, showExample };
}
