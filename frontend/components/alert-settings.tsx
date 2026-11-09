"use client";

import { type FormEvent, useState } from "react";

import {
  RADII,
  setAlertPlace,
  setAlertsEnabled,
  unfollowArtist,
  useAlerts,
} from "@/lib/alerts";
import { SearchRefused } from "@/lib/search";

function failure(caught: unknown): string {
  return caught instanceof SearchRefused ? caught.message : "That did not save. Try again soon.";
}

/** Followed Artists, the Alert place and the switch for the daily Alert email. */
export function AlertSettings() {
  const alerts = useAlerts();
  const [place, setPlace] = useState("");
  const [radius, setRadius] = useState<number>(50);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!alerts) return <p role="status">Loading your Alerts</p>;

  async function act(change: () => Promise<void>): Promise<boolean> {
    setBusy(true);
    setError(null);
    try {
      await change();
      return true;
    } catch (caught) {
      setError(failure(caught));
      return false;
    } finally {
      setBusy(false);
    }
  }

  function savePlace(event: FormEvent) {
    event.preventDefault();
    if (!place.trim()) return;
    void act(() => setAlertPlace(place.trim(), radius)).then((saved) => saved && setPlace(""));
  }

  return (
    <section aria-labelledby="alerts-heading">
      <h2 id="alerts-heading">Alerts</h2>
      <p>
        Follow an Artist from their name on any Ticket. Once a day, Concert Scout emails you about
        their new Concerts near your Alert place. You get at most one email a day.
      </p>

      <form className="alert-place" onSubmit={savePlace}>
        <label htmlFor="alert-place">Alert place</label>
        <p className="alert-current">
          {alerts.place
            ? `Within ${alerts.place.radius_miles ?? 50} miles of ${alerts.place.name}`
            : "No Alert place yet."}
        </p>
        <div className="alert-fields">
          <input
            id="alert-place"
            value={place}
            onChange={(event) => setPlace(event.target.value)}
            placeholder="A city, such as Chicago"
            maxLength={120}
            autoComplete="off"
          />
          <select
            aria-label="Distance"
            value={radius}
            onChange={(event) => setRadius(Number(event.target.value))}
          >
            {RADII.map((miles) => (
              <option key={miles} value={miles}>
                {miles} miles
              </option>
            ))}
          </select>
          <button type="submit" disabled={busy || !place.trim()}>
            {alerts.place ? "Change place" : "Set place"}
          </button>
        </div>
      </form>

      <label className="alert-switch">
        <input
          type="checkbox"
          checked={alerts.enabled}
          disabled={busy || !alerts.place}
          onChange={(event) => void act(() => setAlertsEnabled(event.target.checked))}
        />
        Email me about new Concerts by Artists I follow
      </label>

      <h3>Followed Artists</h3>
      {alerts.followed.length === 0 ? (
        <p>You follow no Artists yet.</p>
      ) : (
        <ul className="followed-artists">
          {alerts.followed.map((artist) => (
            <li key={artist.artist_key}>
              <span>{artist.name}</span>
              <button
                type="button"
                disabled={busy}
                onClick={() => void act(() => unfollowArtist(artist.artist_key))}
              >
                Unfollow<span className="sr-only"> {artist.name}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
