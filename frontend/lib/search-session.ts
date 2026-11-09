// A tab keeps its latest Search so a reload returns to it without starting a paid Search.
const SEARCH_KEY = "concert-scout-search";

// Run before paint so a reload never flashes the home sections above a kept Search.
export const SEARCH_BOOT = `(function(){try{if(sessionStorage.getItem('${SEARCH_KEY}'))document.documentElement.dataset.searchKept=''}catch{}})()`;

export function readSearch<T>(): T | null {
  try {
    return JSON.parse(sessionStorage.getItem(SEARCH_KEY) ?? "null");
  } catch {
    return null;
  }
}

export function keepSearch(search: unknown) {
  document.documentElement.dataset.searchKept = "";
  try {
    sessionStorage.setItem(SEARCH_KEY, JSON.stringify(search));
  } catch {
    /* A reload returns home instead. */
  }
}

export function forgetSearch() {
  delete document.documentElement.dataset.searchKept;
  try {
    sessionStorage.removeItem(SEARCH_KEY);
  } catch {}
}
