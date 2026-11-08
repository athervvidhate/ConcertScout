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
  useEffect(() => {
    const controller = new AbortController();
    void fetch(`${API_URL}/examples`, { signal: controller.signal })
      .then(async (response) =>
        response.ok ? response.json() : { examples: [] },
      )
      .then((data) => {
        if (!controller.signal.aborted) setExamples(data.examples ?? []);
      })
      .catch(() => {});
    return () => controller.abort();
  }, []);
  return examples;
}
