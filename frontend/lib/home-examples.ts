import { useEffect, useState } from "react";
import type {
  Candidates,
  Reading,
  Recommendation,
} from "@/lib/search";

export type HomeExample = {
  text: string;
  reading: Reading | null;
  candidates: Candidates | null;
  poster: { recommendations: Recommendation[] };
};

export function useHomeExamples() {
  const [examples, setExamples] = useState<HomeExample[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    // Same-origin and cached by app/examples/route.ts, so a cold API never delays home.
    void fetch("/examples", {
      signal: AbortSignal.any([controller.signal, AbortSignal.timeout(5000)]),
    })
      .then(async (response) =>
        response.ok ? response.json() : { examples: [] },
      )
      .then((data) => {
        if (!controller.signal.aborted) setExamples(data.examples ?? []);
      })
      .catch(() => {})
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, []);
  return { examples, loading };
}
