import type { Metadata } from "next";

import { LabView } from "@/components/lab-view";
import { SiteHeader } from "@/components/site-header";

export const metadata: Metadata = {
  title: "Engineering Lab · Concert Scout",
  description:
    "Live Search speed, cost, cache numbers, and how Concert Scout ranks shows.",
};

export default function LabPage() {
  return (
    <main className="scout lab-page">
      <SiteHeader />
      <LabView />
    </main>
  );
}
