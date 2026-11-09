export type Place = { lat: number; lon: number };

const PLACE_KEY = "concert-scout-place";

/** Only a place the visitor chose lands here. It stays on this device. */
export function readPlace(): Place | null {
  try {
    return JSON.parse(localStorage.getItem(PLACE_KEY) ?? "null");
  } catch {
    return null;
  }
}

export function keepPlace(place: Place): void {
  try {
    localStorage.setItem(PLACE_KEY, JSON.stringify(place));
  } catch {
    // Without storage, the visitor only has to choose the place again next time.
  }
}

export function forgetPlace(): void {
  try {
    localStorage.removeItem(PLACE_KEY);
  } catch {
    // Nothing was stored, so there is nothing to forget.
  }
}
