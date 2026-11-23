"use client";

import { ArrowRight, Calendar, DollarSign, MapPin, Users } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { GroupArtistPicker } from "@/components/group-artist-picker";
import { SiteHeader } from "@/components/site-header";
import { dateIn, viewerZone } from "@/lib/format";
import { createGroupRoom, rememberRoomMemberId } from "@/lib/group-scout";
import { SearchRefused } from "@/lib/search";

export default function GroupCreatePage() {
  const router = useRouter();
  const today = dateIn(viewerZone(), new Date());

  const [place, setPlace] = useState("");
  const [title, setTitle] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [memberName, setMemberName] = useState("");
  const [artists, setArtists] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!place.trim()) {
      setError("Enter a city or place for your group.");
      return;
    }
    if (!memberName.trim()) {
      setError("Enter your name so friends know whose picks these are.");
      return;
    }
    if (artists.length === 0) {
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
        artists,
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

          <GroupArtistPicker
            id="group-artists"
            label="Your Taste (Artists you love)"
            artists={artists}
            onChange={(next) => {
              setArtists(next);
              setError(null);
            }}
          />

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
