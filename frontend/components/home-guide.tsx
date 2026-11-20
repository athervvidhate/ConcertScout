"use client";

import { Button } from "@base-ui/react/button";
import { HowSearchWorks } from "@/components/how-search-works";

type Props = {
  personal: boolean;
  locationLabel: string;
  onLocation: () => void;
  onTaste: () => void;
  onPickArtists?: () => void;
};

export function HomeGuide({
  personal,
  locationLabel,
  onLocation,
  onTaste,
  onPickArtists,
}: Props) {
  return (
    <div className="home-guide">
      <HowSearchWorks />
      {personal && (
        <section className="home-personal" aria-labelledby="home-yours">
          <div>
            <h2 id="home-yours">Make it yours</h2>
            <p>
              Bring the Artists you already play. Connect Spotify, pick 3–5 Artists,
              or import a playlist CSV, and share your location to find Concerts near you.
            </p>
          </div>
          <div className="yours-actions">
            <Button onClick={onTaste}>Add your Taste</Button>
            {onPickArtists && <Button onClick={onPickArtists}>Pick Artists</Button>}
            <Button onClick={onLocation}>{locationLabel}</Button>
          </div>
        </section>
      )}
    </div>
  );
}
