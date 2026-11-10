import { API_URL } from "@/lib/search";

// The public example Posters, served from this site's cache. Visitors never wait on the API:
// Next.js answers with the cached copy and asks the API again in the background.
export const revalidate = 600;

export async function GET() {
  try {
    const response = await fetch(`${API_URL}/examples`, {
      signal: AbortSignal.timeout(30_000),
    });
    if (response.ok) return Response.json(await response.json());
  } catch {
    // An unreachable API leaves the strip out, as an empty cache does.
  }
  return Response.json({ examples: [] });
}
