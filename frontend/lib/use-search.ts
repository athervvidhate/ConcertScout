import { useCallback, useEffect, useRef, useState } from "react";

import {
  DEFAULT_SCULPT,
  isDefaultSculpt,
  sculptPoster,
  type SculptMeta,
  type SculptState,
} from "@/lib/sculpt";
import type { RefinementEntry, UnanswerableNote } from "@/lib/refinement";
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
  // Typed Refinements trail, base Reading for undo, and inline unanswerable note.
  baseReading: Reading | null;
  refinements: RefinementEntry[];
  unanswerable: UnanswerableNote | null;
  refining: boolean;
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
  baseReading: null,
  refinements: [],
  unanswerable: null,
  refining: false,
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
    baseReading: kept.baseReading ?? kept.reading ?? null,
    refinements: kept.refinements ?? [],
    unanswerable: null,
    refining: false,
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
      options?: {
        keepTrail?: RefinementEntry[];
        keepBaseReading?: Reading | null;
      },
    ) => {
      current.current?.abort();
      sculptAbort.current?.abort();
      const controller = new AbortController();
      current.current = controller;
      const isRefinement = "refinement" in asked;
      const isInPlaceUndo = !isRefinement && options?.keepTrail !== undefined;

      if (isRefinement || isInPlaceUndo) {
        // Keep the current Poster visible while refining or undoing a Refinement chip.
        setState((prev) => ({
          ...prev,
          phase: "searching",
          refining: true,
          asked,
          status: isRefinement ? "Refining your Search" : "Updating your Poster",
          step: isRefinement ? "refine" : "resolve",
          reading: isInPlaceUndo && "reading" in asked ? asked.reading : prev.reading,
          error: null,
          unanswerable: null,
          baseReading:
            options?.keepBaseReading ?? prev.baseReading ?? prev.reading,
          refinements: options?.keepTrail ?? prev.refinements,
        }));
      } else {
        // A corrected Reading shows at once, so its chips never blink out while it runs.
        setState(({ run, searched }) => ({
          ...IDLE,
          phase: "searching",
          run: run + 1,
          searched: "text" in asked ? asked.text : searched,
          asked,
          reading: "reading" in asked ? asked.reading : null,
          baseReading:
            options?.keepBaseReading ??
            ("reading" in asked ? asked.reading : null),
          refinements: options?.keepTrail ?? [],
        }));
      }

      let finished = false;
      let error: string | null = null;
      let retryable = true;
      let refinementLabel = isRefinement ? asked.refinement : "";
      let refinedReading: Reading | null = null;
      let gotUnanswerable = false;

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
          } else if (event === "refinement") {
            refinementLabel = data.label;
          } else if (event === "unanswerable") {
            gotUnanswerable = true;
            setState((state) => ({
              ...state,
              unanswerable: {
                ...data,
                text: isRefinement ? asked.refinement : "",
              },
            }));
          } else if (event === "reading") {
            refinedReading = data;
            setState((state) => ({
              ...state,
              reading: data,
              baseReading: state.baseReading ?? data,
            }));
          } else if (event === "candidates") {
            setState((state) => ({ ...state, candidates: data }));
          } else if (event === "poster") {
            setState((state) => ({
              ...state,
              hasPoster: true,
              recommendations: data.recommendations,
              sculpt: DEFAULT_SCULPT,
              sculptMeta: null,
              sculptError: null,
              sculptVersion:
                isRefinement || isInPlaceUndo
                  ? state.sculptVersion + 1
                  : state.sculptVersion,
              elsewhere: null,
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
      setState((state) => {
        const nextRefinements =
          isRefinement && !gotUnanswerable && !error && refinedReading
            ? [
                ...state.refinements,
                {
                  id: `${Date.now()}-${state.refinements.length}`,
                  text: asked.refinement,
                  label: refinementLabel || asked.refinement,
                  reading: refinedReading,
                },
              ]
            : state.refinements;
        return {
          ...state,
          phase: "finished",
          refining: false,
          status: null,
          step: null,
          error,
          retryable,
          refinements: nextRefinements,
        };
      });
    },
    [],
  );

  const dismissUnanswerable = useCallback(() => {
    setState((prev) => ({ ...prev, unanswerable: null }));
  }, []);

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

  return {
    ...state,
    search,
    clear,
    showExample,
    applySculpt,
    resetSculpt,
    dismissUnanswerable,
  };
}
