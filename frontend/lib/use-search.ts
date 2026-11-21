import { useCallback, useEffect, useRef, useState } from "react";

import {
  DEFAULT_SCULPT,
  isDefaultSculpt,
  sculptPoster,
  type SculptMeta,
  type SculptState,
} from "@/lib/sculpt";
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

type BasePoster = {
  recommendations: Recommendation[];
  candidates: Candidates | null;
  searchId: string | null;
};

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
  // Names this Poster to the server, which alone can turn it into a Shared Poster or Sculpt it.
  searchId: string | null;
  elsewhere: Elsewhere | null;
  error: string | null;
  retryable: boolean;
  // Restored after a reload, so the Poster shows at once instead of replaying its reveal.
  resumed: boolean;
  // Active Poster Sculpting dials, steering artists, and metadata.
  sculpt: SculptState;
  sculpting: boolean;
  sculptMeta: SculptMeta | null;
  sculptError: { code: string; message: string } | null;
  sculptVersion: number;
  basePoster: BasePoster | null;
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
  sculpt: DEFAULT_SCULPT,
  sculpting: false,
  sculptMeta: null,
  sculptError: null,
  sculptVersion: 0,
  basePoster: null,
};

const DROPPED = "The connection dropped before the Search finished.";
const RELOADED = "The page reloaded before the Search finished.";

// A stream cannot continue across a reload, so an unfinished Search becomes a retry.
function resume(kept: SearchState): SearchState {
  const base = {
    ...IDLE,
    ...kept,
    sculpt: kept.sculpt ?? DEFAULT_SCULPT,
    sculpting: false,
    sculptMeta: kept.sculptMeta ?? null,
    sculptError: null,
    sculptVersion: kept.sculptVersion ?? 0,
    basePoster: kept.basePoster ?? null,
    resumed: true,
  };
  if (kept.phase !== "searching") return base;
  return {
    ...base,
    phase: "finished",
    status: null,
    step: null,
    error: kept.hasPoster ? null : RELOADED,
    retryable: true,
  };
}

export function useSearch() {
  const [state, setState] = useState(IDLE);
  const current = useRef<AbortController | null>(null);
  const sculptAbort = useRef<AbortController | null>(null);
  const stateRef = useRef(state);

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  useEffect(
    () => () => {
      current.current?.abort();
      sculptAbort.current?.abort();
    },
    [],
  );

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
            setState((state) => ({
              ...state,
              searchId: data.search_id,
              basePoster: {
                recommendations: state.recommendations,
                candidates: state.candidates,
                searchId: data.search_id,
              },
            }));
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
    sculptAbort.current?.abort();
    forgetSearch();
    setState(IDLE);
  }, []);

  const applySculpt = useCallback(async (next: SculptState) => {
    const snap = stateRef.current;
    if (isDefaultSculpt(next) && snap.basePoster) {
      sculptAbort.current?.abort();
      setState((prev) => ({
        ...prev,
        sculpt: DEFAULT_SCULPT,
        sculpting: false,
        sculptMeta: null,
        sculptError: null,
        recommendations: prev.basePoster?.recommendations ?? prev.recommendations,
        candidates: prev.basePoster?.candidates ?? prev.candidates,
        searchId: prev.basePoster?.searchId ?? prev.searchId,
        sculptVersion: prev.sculptVersion + 1,
      }));
      return;
    }

    const activeId = snap.searchId;
    if (!activeId) return;

    sculptAbort.current?.abort();
    const controller = new AbortController();
    sculptAbort.current = controller;
    setState((prev) => ({
      ...prev,
      sculpt: next,
      sculpting: true,
      sculptError: null,
    }));

    try {
      const response = await sculptPoster(activeId, next, controller.signal);
      if (controller.signal.aborted) return;
      setState((prev) => ({
        ...prev,
        searchId: response.search_id,
        recommendations: response.poster.recommendations,
        candidates: response.candidates,
        sculpt: next,
        sculpting: false,
        sculptMeta: response.meta,
        sculptError: null,
        sculptVersion: prev.sculptVersion + 1,
      }));
    } catch (caught) {
      if (controller.signal.aborted) return;
      const err =
        caught instanceof SearchRefused
          ? { code: caught.code, message: caught.message }
          : {
              code: "unreachable",
              message:
                caught instanceof TypeError
                  ? UNREACHABLE
                  : (caught as Error).message,
            };
      setState((prev) => ({
        ...prev,
        sculpting: false,
        sculptError: err,
      }));
    }
  }, []);

  const resetSculpt = useCallback(() => {
    void applySculpt(DEFAULT_SCULPT);
  }, [applySculpt]);

  const showExample = useCallback(
    (example: {
      text: string;
      reading: Reading | null;
      candidates: Candidates | null;
      poster: { recommendations: Recommendation[] };
    }) => {
      current.current?.abort();
      sculptAbort.current?.abort();
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

  return { ...state, search, clear, showExample, applySculpt, resetSculpt };
}
