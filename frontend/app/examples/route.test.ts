import { afterEach, describe, expect, it, vi } from "vitest";

import { GET } from "@/app/examples/route";

afterEach(() => vi.unstubAllGlobals());

describe("GET /examples", () => {
  it("passes on the API's cached examples", async () => {
    const examples = { examples: [{ text: "Jazz in New Orleans this weekend" }] };
    vi.stubGlobal("fetch", vi.fn(async () => Response.json(examples)));
    expect(await (await GET()).json()).toEqual(examples);
  });

  it.each([
    ["an unreachable API", () => Promise.reject(new TypeError("fetch failed"))],
    ["an API error", async () => new Response("", { status: 503 })],
  ])("leaves the strip out for %s", async (_, answer) => {
    vi.stubGlobal("fetch", vi.fn(answer));
    expect(await (await GET()).json()).toEqual({ examples: [] });
  });
});
