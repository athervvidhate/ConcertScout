"use client";
import { Bookmark, Check } from "lucide-react";
export function SaveButton({
  saved,
  onToggle,
  pending = false,
  compact = false,
  name,
}: {
  saved: boolean;
  onToggle: () => void;
  pending?: boolean;
  compact?: boolean;
  name?: string;
}) {
  const label = saved ? "Unsave" : "Save";
  return (
    <button
      type="button"
      className={`save-action${compact ? " card-save" : ""}`}
      aria-label={compact ? `${label} ${name}` : undefined}
      title={compact ? `${label} ${name}` : undefined}
      aria-pressed={saved}
      aria-busy={pending}
      disabled={pending}
      onClick={(event) => {
        const button = event.currentTarget,
          r = button.getBoundingClientRect();
        button.style.setProperty(
          "--save-x",
          `${event.clientX ? event.clientX - r.left : r.width / 2}px`,
        );
        button.style.setProperty(
          "--save-y",
          `${event.clientY ? event.clientY - r.top : r.height / 2}px`,
        );
        onToggle();
      }}
    >
      <span className="save-fill" aria-hidden />
      <span className={saved ? "save-symbol saved" : "save-symbol"}>
        {compact ? (
          <Bookmark
            aria-hidden
            size={19}
            style={{ fill: saved ? "currentColor" : "none" }}
          />
        ) : saved ? (
          <Check aria-hidden size={19} />
        ) : (
          <Bookmark aria-hidden size={19} />
        )}
      </span>
      {!compact && <span>{label}</span>}
    </button>
  );
}
