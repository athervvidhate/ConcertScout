"use client";

import { Button } from "@base-ui/react/button";
import { type ReactNode, useState } from "react";

const STEP = 5;

type BoardProps = {
  title: string;
  subtitle?: string;
  /** Sits opposite the title, such as a source's logo or a control. */
  aside?: ReactNode;
  children?: ReactNode;
};

export function Board({ title, subtitle, aside, children }: BoardProps) {
  return (
    <section className="board" aria-label={title}>
      <header className="board-head">
        <div>
          <h2>{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        {aside}
      </header>
      {children}
    </section>
  );
}

/** Rows never leave a gap the way a grid does, and paging keeps a board from rolling on. */
export function Listings({ children }: { children: ReactNode[] }) {
  const [shown, setShown] = useState(STEP);
  const remaining = children.length - shown;
  return (
    <>
      <ul className="listings">{children.slice(0, shown)}</ul>
      {remaining > 0 && (
        <Button type="button" className="board-more" onClick={() => setShown(shown + STEP)}>
          Show {Math.min(remaining, STEP)} more
        </Button>
      )}
    </>
  );
}
