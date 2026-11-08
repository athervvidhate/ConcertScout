"use client";

import { useState, type RefObject } from "react";
import { useSearchExample } from "@/lib/search-examples";

/** Keep the typing animation local: it must not rerender the photo strip or the home demo. */
export function SearchInput({
  text,
  onText,
  home,
  inputRef,
}: {
  text: string;
  onText: (text: string) => void;
  home: boolean;
  inputRef: RefObject<HTMLInputElement | null>;
}) {
  const [focused, setFocused] = useState(false);
  const example = useSearchExample(!text && home && !focused);
  return (
    <input
      id="search"
      ref={inputRef}
      value={text}
      onChange={(event) => onText(event.target.value)}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      placeholder={home && !focused && !text ? example : undefined}
      required
      maxLength={500}
    />
  );
}
