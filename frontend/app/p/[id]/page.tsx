import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { loadShared } from "@/app/p/[id]/load";
import { SharedPosterView } from "@/components/shared-poster";
import { sharedHeading, sharedSummary } from "@/lib/shared-heading";

type Props = PageProps<"/p/[id]">;

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const shared = await loadShared((await params).id);
  if (!shared) return { title: "Shared Poster · Concert Scout" };
  const title = `${sharedHeading(shared)} · Shared Poster`;
  const description = sharedSummary(shared);
  return {
    title,
    description,
    openGraph: { title, description, siteName: "Concert Scout", type: "website" },
    twitter: { card: "summary_large_image", title, description },
  };
}

export default async function SharedPosterPage({ params, searchParams }: Props) {
  const { id } = await params;
  const shared = await loadShared(id);
  if (!shared) notFound();
  const { ticket } = await searchParams;
  return (
    <main className="scout">
      <SharedPosterView
        id={id}
        shared={shared}
        ticket={typeof ticket === "string" ? ticket : undefined}
      />
    </main>
  );
}
