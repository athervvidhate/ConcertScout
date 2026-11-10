"use client";

import { Button } from "@base-ui/react/button";
import { ArrowRight } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";

import { Poster } from "@/components/poster";
import { SearchChips } from "@/components/search-chips";
import { SiteHeader } from "@/components/site-header";
import type { SharedPoster } from "@/lib/share";
import { sharedUrl } from "@/lib/share";
import { formatMade, sharedHeading } from "@/lib/shared-heading";

type Props = { id: string; shared: SharedPoster; ticket?: string };

// A Shared Poster is already kept, so the link needs no request.
export function SharedPosterView({ id, shared, ticket }: Props) {
  const reduced = useReducedMotion();
  const { reading, recommendations, made } = shared;
  return (
    <>
      <SiteHeader />
      <header className="shared-head">
        <p className="shared-label">Shared Poster</p>
        <h1>{sharedHeading(shared)}</h1>
        <p className="shared-made">
          Made <time dateTime={made}>{formatMade(made)}</time>
        </p>
        {reading && (
          <motion.div
            className="understood"
            aria-label="How the Search was read"
            initial="hidden"
            animate="shown"
            variants={{
              hidden: {},
              shown: { transition: { staggerChildren: reduced ? 0 : 0.08 } },
            }}
          >
            <SearchChips reading={reading} />
          </motion.div>
        )}
      </header>
      {recommendations.length > 0 ? (
        <Poster
          candidates={null}
          recommendations={recommendations}
          hasPoster
          searching={false}
          status={null}
          instant
          openConcert={ticket}
          shareLink={async (concertId) => sharedUrl(id, concertId)}
        />
      ) : (
        <section className="empty" aria-label="Poster">
          <h2>These Concerts have passed</h2>
          <p>Nothing on this Poster is still to come. Start your own Search for what is.</p>
        </section>
      )}
      <form action="/" className="search-bar shared-search">
        <label htmlFor="shared-search" className="sr-only">
          Search
        </label>
        <input
          id="shared-search"
          name="q"
          required
          maxLength={500}
          placeholder="Start your own Search"
        />
        <Button type="submit" className="search-send" aria-label="Search">
          <span className="send-label">Search</span>
          <ArrowRight aria-hidden size={22} />
        </Button>
      </form>
    </>
  );
}
