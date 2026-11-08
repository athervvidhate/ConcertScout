"use client";
import { Bookmark, Check } from "lucide-react";
export function SaveButton({
  saved,
  onSave,
}: {
  saved: boolean;
  onSave: () => void;
}) {
  return (
    <button
      className="save-action"
      aria-pressed={saved}
      disabled={saved}
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
        onSave();
      }}
    >
      <span className="save-fill" aria-hidden />
      <span className={saved ? "save-symbol saved" : "save-symbol"}>
        {saved ? (
          <Check aria-hidden size={19} />
        ) : (
          <Bookmark aria-hidden size={19} />
        )}
      </span>
      <span>{saved ? "Saved" : "Save"}</span>
    </button>
  );
}
