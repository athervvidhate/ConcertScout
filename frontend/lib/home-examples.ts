import { useEffect, useState } from "react";
import {
  API_URL,
  type Candidates,
  type Interpreted,
  type Recommendation,
} from "@/lib/search";

export type HomeExample = {
  text: string;
  interpreted: Interpreted | null;
  candidates: Candidates | null;
  poster: { recommendations: Recommendation[] };
};

export function useHomeExamples() {
  const [examples, setExamples] = useState<HomeExample[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    void fetch(`${API_URL}/examples`, {
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
