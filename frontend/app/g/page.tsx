"use client";

import { ArrowRight, Calendar, DollarSign, MapPin, Plus, Sparkles, Users, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { SiteHeader } from "@/components/site-header";
import { dateIn, viewerZone } from "@/lib/format";
import {
  QUICK_PICK_ARTISTS,
  createGroupRoom,
  mergeArtists,
  parseArtistsInput,
  rememberRoomMemberId,
} from "@/lib/group-scout";
import { SearchRefused } from "@/lib/search";
import { useImportedTaste } from "@/lib/taste";

export default function GroupCreatePage() {
  const router = useRouter();
  const savedTaste = useImportedTaste();
  const today = dateIn(viewerZone(), new Date());

  const [place, setPlace] = useState("");
  const [title, setTitle] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [memberName, setMemberName] = useState("");
  const [artists, setArtists] = useState<string[]>([]);
  const [artistInput, setArtistInput] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function addTypedArtists() {
    const parsed = parseArtistsInput(artistInput);
    if (parsed.length === 0) return;
    setArtists((current) => mergeArtists(current, parsed));
    setArtistInput("");
    setError(null);
  }

  function toggleQuickArtist(name: string) {
    const lower = name.toLowerCase();
    setArtists((current) => {
      if (current.some((a) => a.toLowerCase() === lower)) {
        return current.filter((a) => a.toLowerCase() !== lower);
      }
      return mergeArtists(current, [name]);
    });
    setError(null);
  }

  function removeArtist(name: string) {
    setArtists((current) => current.filter((a) => a !== name));
  }

  function applySavedTaste() {
    if (!savedTaste || savedTaste.artists.length === 0) return;
    setArtists((current) => mergeArtists(current, savedTaste.artists));
    setError(null);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const combinedArtists = mergeArtists(artists, parseArtistsInput(artistInput));
    if (!place.trim()) {
      setError("Enter a city or place for your group.");
      return;
    }
    if (!memberName.trim()) {
      setError("Enter your name so friends know whose picks these are.");
      return;
    }
    if (combinedArtists.length === 0) {
      setError("Add at least one Artist to your Taste.");
      return;
    }
    if (startDate && endDate && endDate < startDate) {
      setError("End date must be on or after the start date.");
      return;
    }
    const parsedPrice = maxPrice.trim() ? Number(maxPrice) : undefined;
    if (parsedPrice !== undefined && (!Number.isFinite(parsedPrice) || parsedPrice <= 0)) {
      setError("Max price must be greater than $0.");
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      const created = await createGroupRoom({
        place: place.trim(),
        title: title.trim() || undefined,
        start_date: startDate || undefined,
        end_date: endDate || undefined,
        max_price: parsedPrice,
        member_name: memberName.trim(),
        artists: combinedArtists,
      });
      rememberRoomMemberId(created.room.id, created.member_id);
      router.push(`/g/${created.room.id}`);
    } catch (caught) {
      setError(
        caught instanceof SearchRefused
          ? caught.message
          : "Could not start the Group Scout room. Try again.",
      );
      setSubmitting(false);
    }
  }

  return (
    <main className="scout group-page">
      <SiteHeader />

      <section className="group-hero" aria-labelledby="group-create-heading">
        <div className="group-hero-inner">
          <p className="group-eyebrow">
            <Users aria-hidden size={15} />
            Group Scout · 2 to 6 friends · No account needed
          </p>
          <h1 id="group-create-heading">Pick a Concert everyone wants to see</h1>
          <p className="group-hero-lead">
            Start with a place, optional dates and budget, and your Taste. Share the room link so
            friends can add theirs, see fair group picks, and vote live.
          </p>
        </div>
      </section>

      <section className="group-studio" aria-label="Start a Group Scout room">
        <form className="group-form" onSubmit={handleSubmit} noValidate>
          <div className="group-form-grid">
            <div className="group-field">
              <label htmlFor="group-place">
                <MapPin aria-hidden size={15} />
                Place
              </label>
              <input
                id="group-place"
                type="text"
                required
                maxLength={200}
                placeholder="Brooklyn, NY or San Francisco, CA"
                value={place}
                onChange={(e) => setPlace(e.target.value)}
              />
            </div>

            <div className="group-field">
              <label htmlFor="group-title">Room name (optional)</label>
              <input
                id="group-title"
                type="text"
                maxLength={120}
                placeholder="Friday night crew"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </div>

            <div className="group-field">
              <label htmlFor="group-start">
                <Calendar aria-hidden size={15} />
                From date (optional)
              </label>
              <input
                id="group-start"
                type="date"
                min={today}
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
              />
            </div>

            <div className="group-field">
              <label htmlFor="group-end">Until date (optional)</label>
              <input
                id="group-end"
                type="date"
                min={startDate || today}
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
              />
            </div>

            <div className="group-field">
              <label htmlFor="group-budget">
                <DollarSign aria-hidden size={15} />
                Max ticket price (optional)
              </label>
              <input
                id="group-budget"
                type="number"
                min={1}
                max={10000}
                step={1}
                inputMode="numeric"
                placeholder="60"
                value={maxPrice}
                onChange={(e) => setMaxPrice(e.target.value)}
              />
            </div>

            <div className="group-field">
              <label htmlFor="group-name">Your name</label>
              <input
                id="group-name"
                type="text"
                required
                maxLength={48}
                placeholder="Maya"
                value={memberName}
                onChange={(e) => setMemberName(e.target.value)}
              />
            </div>
          </div>

          <div className="group-taste-block">
            <div className="group-taste-head">
              <label htmlFor="group-artists">Your Taste (Artists you love)</label>
              {savedTaste && savedTaste.artists.length > 0 && (
                <button
                  type="button"
                  className="group-prefill-btn"
                  onClick={applySavedTaste}
                >
                  <Sparkles aria-hidden size={15} />
                  Use saved Taste ({savedTaste.artists.length})
                </button>
              )}
            </div>

            <div className="group-artist-entry">
              <input
                id="group-artists"
                type="text"
                placeholder="Paste or type Artists (e.g. Khruangbin, Bonobo, Parcels)"
                value={artistInput}
                onChange={(e) => setArtistInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    addTypedArtists();
                  }
                }}
              />
              <button
                type="button"
                className="group-add-btn"
                onClick={addTypedArtists}
                aria-label="Add Artists"
              >
                <Plus aria-hidden size={18} />
                Add
              </button>
            </div>

            {artists.length > 0 && (
              <ul className="group-artist-chips" aria-label="Selected Artists">
                {artists.map((artist) => (
                  <li key={artist} className="group-artist-chip">
                    <span>{artist}</span>
                    <button
                      type="button"
                      aria-label={`Remove ${artist}`}
                      onClick={() => removeArtist(artist)}
                    >
                      <X aria-hidden size={14} />
                    </button>
                  </li>
                ))}
              </ul>
            )}

            <div className="group-quick-picks">
              <span className="group-quick-label">Quick picks:</span>
              {QUICK_PICK_ARTISTS.map((artist) => {
                const active = artists.some((a) => a.toLowerCase() === artist.toLowerCase());
                return (
                  <button
                    key={artist}
                    type="button"
                    className="group-quick-chip"
                    aria-pressed={active}
                    onClick={() => toggleQuickArtist(artist)}
                  >
                    {artist}
                  </button>
                );
              })}
            </div>
          </div>

          {error && (
            <p className="group-error" role="alert">
              {error}
            </p>
          )}

          <div className="group-form-footer">
            <p className="group-privacy-note">
              Facts come straight from Ticketmaster &amp; JamBase. Spotify account data never enters
              a room.
            </p>
            <button type="submit" className="group-primary-btn" disabled={submitting}>
              {submitting ? "Creating room..." : "Create Group Room"}
              <ArrowRight aria-hidden size={18} />
            </button>
          </div>
        </form>
      </section>
    </main>
  );
}
