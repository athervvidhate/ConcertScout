import { ChevronLeft, ChevronRight } from "lucide-react";
import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { useReducedMotion } from "motion/react";

// A swipe this long turns the page on touch.
const SWIPE_PX = 40;

type Props = {
  heading: ReactNode;
  /** Columns on one page. A long list fills them top to bottom, then the next page. */
  columns: 1 | 2;
  children: ReactNode;
};

/**
 * A list that never scrolls. It fills the height it is given in columns, and what does not fit
 * goes on later pages, turned by arrows or a swipe. The browser lays the columns out, so a list
 * of any length and item size pages the same way.
 */
export function Paged({ heading, columns, children }: Props) {
  const windowRef = useRef<HTMLDivElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);
  const [pages, setPages] = useState(1);
  const [page, setPage] = useState(0);
  const reduced = useReducedMotion();
  const swipe = useRef<number | null>(null);

  useLayoutEffect(() => {
    const frame = windowRef.current;
    const track = trackRef.current;
    if (!frame || !track) return;
    const measure = () => {
      const gap = parseFloat(getComputedStyle(track).columnGap) || 0;
      const width = frame.clientWidth + gap;
      const count = width > 0 ? Math.max(1, Math.round((track.scrollWidth + gap) / width)) : 1;
      setPages(count);
      setPage((current) => Math.min(current, count - 1));
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(frame);
    observer.observe(track);
    return () => observer.disconnect();
  }, []);

  // Keyboard focus on a later page turns to that page, since nothing here scrolls into view.
  const follow = (target: EventTarget) => {
    const frame = windowRef.current;
    const track = trackRef.current;
    if (!frame || !track || !(target instanceof HTMLElement)) return;
    const gap = parseFloat(getComputedStyle(track).columnGap) || 0;
    // Both boxes move with the page, so this is the target's place along the whole track.
    const left = target.getBoundingClientRect().left - track.getBoundingClientRect().left;
    const at = Math.floor(left / (frame.clientWidth + gap));
    setPage(Math.min(pages - 1, Math.max(0, at)));
  };

  return (
    <div className="paged">
      <div className="paged-head">
        {heading}
        {pages > 1 && (
          <div className="pager">
            <button
              type="button"
              aria-label="Previous page"
              disabled={page === 0}
              onClick={() => setPage(page - 1)}
            >
              <ChevronLeft aria-hidden size={18} />
            </button>
            <span aria-live="polite">
              {page + 1} of {pages}
            </span>
            <button
              type="button"
              aria-label="Next page"
              disabled={page === pages - 1}
              onClick={() => setPage(page + 1)}
            >
              <ChevronRight aria-hidden size={18} />
            </button>
          </div>
        )}
      </div>
      <div
        ref={windowRef}
        className="paged-window"
        onFocus={(event) => follow(event.target)}
        onPointerDown={(event) => {
          swipe.current = event.clientX;
        }}
        onPointerUp={(event) => {
          if (swipe.current === null) return;
          const moved = event.clientX - swipe.current;
          swipe.current = null;
          if (moved <= -SWIPE_PX) setPage((p) => Math.min(pages - 1, p + 1));
          if (moved >= SWIPE_PX) setPage((p) => Math.max(0, p - 1));
        }}
      >
        <div
          ref={trackRef}
          className="paged-track"
          style={{
            columnCount: columns,
            transform: `translateX(calc(${-page} * (100% + var(--page-gap))))`,
            transition: reduced ? "none" : undefined,
          }}
        >
          {children}
        </div>
      </div>
    </div>
  );
}
