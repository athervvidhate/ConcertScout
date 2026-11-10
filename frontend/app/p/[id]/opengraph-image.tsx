import { readFile } from "node:fs/promises";
import { join } from "node:path";

import { ImageResponse } from "next/og";

import { loadShared } from "@/app/p/[id]/load";
import { formatMonthDay } from "@/lib/format";
import { nameOf } from "@/lib/lineup";
import { sharedHeading } from "@/lib/shared-heading";

export const alt = "A Shared Poster on Concert Scout";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

// The Moss palette's dark pair, because previews sit on both light and dark chats.
const PINE = "#12352b";
const INK = "#eef4ef";
const MUTED = "#a3b5ac";
const CORAL = "#ff7449";
const PICKS = 5;

export default async function Image({ params }: { params: Promise<{ id: string }> }) {
  const shared = await loadShared((await params).id);
  // Satori cannot read WOFF2, so anton.ttf is the same typeface as anton.woff2, unpacked.
  const anton = await readFile(join(process.cwd(), "app/fonts/anton.ttf"));
  const picks = shared?.recommendations.slice(0, PICKS) ?? [];
  const more = (shared?.recommendations.length ?? 0) - picks.length;
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: "56px 72px",
          background: PINE,
          color: INK,
          fontFamily: "Anton",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 28 }}>
          <span style={{ color: CORAL, letterSpacing: 6, textTransform: "uppercase" }}>
            Shared Poster
          </span>
          <span style={{ color: MUTED }}>Concert Scout</span>
        </div>
        <div
          style={{
            display: "flex",
            fontSize: 84,
            lineHeight: 1,
            textTransform: "uppercase",
            maxHeight: 176,
            overflow: "hidden",
          }}
        >
          {shared ? sharedHeading(shared) : "Concerts worth going out for"}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {picks.map((pick) => {
            const { concert } = pick;
            return (
            <div key={concert.id} style={{ display: "flex", alignItems: "baseline", gap: 24 }}>
              <span style={{ width: 130, fontSize: 28, color: CORAL }}>
                {concert.date ? formatMonthDay(concert.date) : ""}
              </span>
              <span style={{ fontSize: 40, textTransform: "uppercase" }}>
                {nameOf(pick)}
              </span>
              <span style={{ fontSize: 26, color: MUTED }}>{concert.city ?? ""}</span>
            </div>
            );
          })}
          {more > 0 && <span style={{ fontSize: 26, color: MUTED }}>and {more} more</span>}
        </div>
      </div>
    ),
    {
      ...size,
      fonts: [{ name: "Anton", data: anton, weight: 400, style: "normal" }],
    },
  );
}
