import type { Metadata } from "next";

import { SavedConcerts } from "@/components/saved-concerts";
import { SiteHeader } from "@/components/site-header";

export const metadata: Metadata = { title: "Saved Concerts · Concert Scout" };

export default function SavedPage() {
  return (
    <main className="scout">
      <SiteHeader />
      <h1 className="saved-title">Saved Concerts</h1>
      <SavedConcerts />
    </main>
  );
}
