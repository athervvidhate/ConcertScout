import type { Metadata } from "next";

import { LabView } from "@/components/lab-view";
import { SiteHeader } from "@/components/site-header";

export const metadata: Metadata = {
  title: "Engineering Lab · Concert Scout",
  description:
    "Live anonymized Search telemetry, hybrid retrieval benchmarks, and architectural invariants.",
};

export default function LabPage() {
  return (
    <main className="scout lab-page">
      <SiteHeader />
      <LabView />
    </main>
  );
}
