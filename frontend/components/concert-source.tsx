"use client";

import Image, { type ImageProps } from "next/image";
import { useState, type ComponentProps } from "react";

import type { Concert } from "@/lib/search";

type PhotoProps = Pick<ImageProps, "sizes" | "loading" | "priority" | "draggable"> & {
  concert: Concert;
  /** The frame's class. The frame is left out with the photo, so layouts can test for it. */
  className: string;
};

/**
 * A Concert's own source photo in a frame, or nothing.
 *
 * Ticketmaster serves sized photos, so they load directly. JamBase uploads are full size, so
 * they pass through the Next.js image cache, which only accepts JamBase's upload path. A photo
 * that fails to load takes its frame with it.
 */
export function ConcertPhoto({ concert, className, ...image }: PhotoProps) {
  const [failed, setFailed] = useState<string>();
  if (!concert.image || failed === concert.image) return null;
  return (
    <div className={className}>
      <Image
        src={concert.image}
        alt=""
        fill
        unoptimized={concert.source !== "jambase"}
        onError={() => setFailed(concert.image)}
        {...image}
      />
    </div>
  );
}

/** A link out to a source listing. Listings are third-party pages, so they pass no ranking. */
export function SourceLink(props: Omit<ComponentProps<"a">, "target" | "rel">) {
  return <a {...props} target="_blank" rel="nofollow noopener noreferrer" />;
}
