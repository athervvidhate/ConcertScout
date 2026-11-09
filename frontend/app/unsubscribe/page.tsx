import type { Metadata } from "next";
import { Suspense } from "react";

import { SiteHeader } from "@/components/site-header";
import { StopAlerts } from "@/components/stop-alerts";

export const metadata: Metadata = { title: "Stop Alerts · Concert Scout", robots: { index: false } };

export default function UnsubscribePage() {
  return (
    <main className="scout information">
      <SiteHeader />
      <Suspense>
        <StopAlerts />
      </Suspense>
    </main>
  );
}
