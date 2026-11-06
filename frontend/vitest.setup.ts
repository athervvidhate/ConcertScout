import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// Cloudflare's script cannot load in tests, so the widget passes as soon as it mounts.
vi.mock("@marsidev/react-turnstile", async () => {
  const { useEffect } = await import("react");
  return {
    Turnstile: ({ onSuccess }: { onSuccess: (token: string) => void }) => {
      useEffect(() => onSuccess("test-token"), [onSuccess]);
      return null;
    },
  };
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
