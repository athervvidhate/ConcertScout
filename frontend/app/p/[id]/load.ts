import { cache } from "react";

import { fetchSharedPoster } from "@/lib/share";

// The page, its metadata and its preview image read one Poster per request.
export const loadShared = cache(fetchSharedPoster);
