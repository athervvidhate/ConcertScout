import Link from "next/link";

import { SiteHeader } from "@/components/site-header";

export default function SharedPosterNotFound() {
  return (
    <main className="scout">
      <SiteHeader />
      <h1 className="saved-title">That Poster is not here</h1>
      <p className="shared-note">
        The link may be wrong, or it is older than 90 days. Start a Search to make a new Poster.
      </p>
      <Link className="quiet" href="/">
        Search for Concerts
      </Link>
    </main>
  );
}
