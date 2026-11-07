import type { Metadata } from "next";
import Link from "next/link";

import { SavedConcerts } from "@/components/saved-concerts";

export const metadata: Metadata = { title: "Saved Concerts · Concert Scout" };

export default function SavedPage() {
  return (
    <main className="scout">
      <header className="saved-header">
        <h1>Saved Concerts</h1>
        <Link href="/">Back to Search</Link>
      </header>
      <SavedConcerts />
    </main>
  );
}
