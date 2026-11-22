"use client";

import {
  AlertTriangle,
  Calendar,
  Check,
  Copy,
  DollarSign,
  ExternalLink,
  LogOut,
  MapPin,
  Plus,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  HelpCircle,
  UserPlus,
  Users,
  X,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";

import { AddToCalendar } from "@/components/add-to-calendar";
import { SiteHeader } from "@/components/site-header";
import {
  countOf,
  dateIn,
  formatConcertTime,
  formatDate,
  formatMonthDay,
  formatPrice,
  viewerZone,
} from "@/lib/format";
import {
  MAX_GROUP_MEMBERS,
  QUICK_PICK_ARTISTS,
  castGroupVote,
  fetchGroupRoom,
  forgetRoomMemberId,
  formatDateWindow,
  groupShareUrl,
  joinGroupRoom,
  leaveGroupRoom,
  memberInitials,
  mergeArtists,
  parseArtistsInput,
  readRoomMemberId,
  rememberRoomMemberId,
  sortGroupPicks,
  subscribeGroupRoom,
  type GroupPick,
  type GroupRoomState,
  type GroupSort,
  type VoteChoice,
} from "@/lib/group-scout";
import { SearchRefused } from "@/lib/search";
import { showTitle } from "@/lib/show-title";
import { useImportedTaste } from "@/lib/taste";

const POLL_MS = 2500;

const AVATAR_TONES = [
  "tone-0",
  "tone-1",
  "tone-2",
  "tone-3",
  "tone-4",
  "tone-5",
] as const;

export function GroupRoom({ roomId }: { roomId: string }) {
  const savedTaste = useImportedTaste();
  const today = dateIn(viewerZone(), new Date());

  const [room, setRoom] = useState<GroupRoomState | null>(null);
  const [memberId, setMemberId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [sort, setSort] = useState<GroupSort>("fit");
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState<string | null>(null);
  const [syncMode, setSyncMode] = useState<"connecting" | "live" | "polling">("connecting");

  // Guest join form state
  const [joinName, setJoinName] = useState("");
  const [joinArtists, setJoinArtists] = useState<string[]>([]);
  const [joinArtistInput, setJoinArtistInput] = useState("");
  const [joinStart, setJoinStart] = useState("");
  const [joinEnd, setJoinEnd] = useState("");
  const [joinMaxPrice, setJoinMaxPrice] = useState("");
  const [joining, setJoining] = useState(false);
  const [joinError, setJoinError] = useState<string | null>(null);

  const [votingConcertId, setVotingConcertId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [leaving, setLeaving] = useState(false);

  const copyTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const applyLoadedRoom = useCallback(
    (next: GroupRoomState) => {
      setRoom(next);
      setNotFound(false);
      setLoadError(null);
      const stored = readRoomMemberId(roomId);
      if (stored && next.members.some((m) => m.id === stored)) {
        setMemberId(stored);
      } else if (stored) {
        forgetRoomMemberId(roomId);
        setMemberId(null);
      }
    },
    [roomId],
  );

  const applyLoadError = useCallback((caught: unknown) => {
    if (caught instanceof SearchRefused && caught.code === "group_not_found") {
      setNotFound(true);
      setRoom(null);
    } else {
      setLoadError(
        caught instanceof SearchRefused
          ? caught.message
          : "Could not load this Group Scout room.",
      );
    }
  }, []);

  const refreshRoom = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const next = await fetchGroupRoom(roomId, signal);
        if (!signal?.aborted) applyLoadedRoom(next);
      } catch (caught) {
        if (!signal?.aborted) applyLoadError(caught);
      } finally {
        if (!signal?.aborted) setLoading(false);
      }
    },
    [roomId, applyLoadedRoom, applyLoadError],
  );

  useEffect(() => {
    const controller = new AbortController();
    fetchGroupRoom(roomId, controller.signal)
      .then((next) => {
        if (!controller.signal.aborted) applyLoadedRoom(next);
      })
      .catch((caught) => {
        if (!controller.signal.aborted) applyLoadError(caught);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [roomId, applyLoadedRoom, applyLoadError]);

  const activeRoomId = room?.id ?? null;

  // Live updates: Supabase Realtime first, graceful polling fallback if unavailable.
  useEffect(() => {
    if (!activeRoomId) return;
    let pollInterval: ReturnType<typeof setInterval> | null = null;

    const startPolling = () => {
      setSyncMode("polling");
      if (pollInterval) return;
      pollInterval = setInterval(() => {
        if (document.visibilityState === "visible") {
          void refreshRoom();
        }
      }, POLL_MS);
    };

    const unsubscribe = subscribeGroupRoom(
      activeRoomId,
      () => void refreshRoom(),
      startPolling,
      () => setSyncMode("live"),
    );

    return () => {
      unsubscribe();
      if (pollInterval) clearInterval(pollInterval);
    };
  }, [activeRoomId, refreshRoom]);

  useEffect(() => {
    return () => {
      if (copyTimer.current) clearTimeout(copyTimer.current);
    };
  }, []);

  const currentMember = useMemo(
    () => (room && memberId ? room.members.find((m) => m.id === memberId) ?? null : null),
    [room, memberId],
  );

  const memberNameById = useMemo(() => {
    const map = new Map<string, string>();
    for (const member of room?.members ?? []) map.set(member.id, member.name);
    return map;
  }, [room?.members]);

  const sortedPicks = useMemo(
    () => (room ? sortGroupPicks(room.picks, sort) : []),
    [room, sort],
  );

  async function handleCopyInvite() {
    setCopyError(null);
    const url = groupShareUrl(roomId);
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      if (copyTimer.current) clearTimeout(copyTimer.current);
      copyTimer.current = setTimeout(() => setCopied(false), 3000);
    } catch {
      setCopyError("Copy the URL from your browser address bar to invite friends.");
    }
  }

  function addJoinArtists() {
    const parsed = parseArtistsInput(joinArtistInput);
    if (parsed.length === 0) return;
    setJoinArtists((current) => mergeArtists(current, parsed));
    setJoinArtistInput("");
    setJoinError(null);
  }

  function toggleJoinQuickArtist(name: string) {
    const lower = name.toLowerCase();
    setJoinArtists((current) =>
      current.some((a) => a.toLowerCase() === lower)
        ? current.filter((a) => a.toLowerCase() !== lower)
        : mergeArtists(current, [name]),
    );
    setJoinError(null);
  }

  async function handleJoin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const combined = mergeArtists(joinArtists, parseArtistsInput(joinArtistInput));
    if (!joinName.trim()) {
      setJoinError("Enter your name to join this room.");
      return;
    }
    if (combined.length === 0) {
      setJoinError("Add at least one Artist to your Taste.");
      return;
    }
    if (joinStart && joinEnd && joinEnd < joinStart) {
      setJoinError("End date must be on or after the start date.");
      return;
    }
    const parsedPrice = joinMaxPrice.trim() ? Number(joinMaxPrice) : undefined;
    if (parsedPrice !== undefined && (!Number.isFinite(parsedPrice) || parsedPrice <= 0)) {
      setJoinError("Max price must be greater than $0.");
      return;
    }

    setJoining(true);
    setJoinError(null);
    try {
      const joined = await joinGroupRoom(roomId, {
        name: joinName.trim(),
        artists: combined,
        start_date: joinStart || undefined,
        end_date: joinEnd || undefined,
        max_price: parsedPrice,
      });
      rememberRoomMemberId(roomId, joined.member_id);
      setMemberId(joined.member_id);
      setRoom(joined.room);
      setJoinName("");
      setJoinArtists([]);
      setJoinArtistInput("");
      setJoinStart("");
      setJoinEnd("");
      setJoinMaxPrice("");
    } catch (caught) {
      setJoinError(
        caught instanceof SearchRefused ? caught.message : "Could not join this room. Try again.",
      );
    } finally {
      setJoining(false);
    }
  }

  async function handleVote(concertId: string, vote: VoteChoice) {
    if (!currentMember) return;
    setVotingConcertId(concertId);
    setActionError(null);
    try {
      const updated = await castGroupVote(roomId, currentMember.id, concertId, vote);
      setRoom(updated);
    } catch (caught) {
      setActionError(
        caught instanceof SearchRefused ? caught.message : "Could not save your vote. Try again.",
      );
    } finally {
      setVotingConcertId(null);
    }
  }

  async function handleLeave() {
    if (!currentMember) return;
    setLeaving(true);
    setActionError(null);
    try {
      const updated = await leaveGroupRoom(roomId, currentMember.id);
      forgetRoomMemberId(roomId);
      setMemberId(null);
      setRoom(updated);
    } catch (caught) {
      setActionError(
        caught instanceof SearchRefused ? caught.message : "Could not leave this room. Try again.",
      );
    } finally {
      setLeaving(false);
    }
  }

  if (loading) {
    return (
      <>
        <SiteHeader />
        <section className="group-state-box" aria-live="polite">
          <p className="group-eyebrow">Group Scout</p>
          <h1>Loading room...</h1>
        </section>
      </>
    );
  }

  if (notFound) {
    return (
      <>
        <SiteHeader />
        <section className="group-state-box">
          <p className="group-eyebrow">Group Scout</p>
          <h1>That Group Scout room is not here</h1>
          <p>Its invite link may be wrong or older than 30 days.</p>
          <div className="group-state-actions">
            <Link href="/g" className="group-primary-btn">
              Start a new Group Room
            </Link>
            <Link href="/" className="group-quiet-btn">
              Back to Search
            </Link>
          </div>
        </section>
      </>
    );
  }

  if (loadError || !room) {
    return (
      <>
        <SiteHeader />
        <section className="group-state-box">
          <p className="group-eyebrow">Group Scout</p>
          <h1>Could not load this room</h1>
          <p>{loadError ?? "Try again in a moment."}</p>
          <div className="group-state-actions">
            <button
              type="button"
              className="group-primary-btn"
              onClick={() => {
                setLoading(true);
                void refreshRoom();
              }}
            >
              Try again
            </button>
          </div>
        </section>
      </>
    );
  }

  const effectiveDates = formatDateWindow(room.effective.start_date, room.effective.end_date);
  const canJoin = !currentMember && room.members.length < MAX_GROUP_MEMBERS;
  const isFullForGuest = !currentMember && room.members.length >= MAX_GROUP_MEMBERS;

  return (
    <>
      <SiteHeader />

      <header className="group-room-header">
        <div className="group-room-header-inner">
          <div className="group-room-top">
            <div>
              <p className="group-eyebrow">
                <Users aria-hidden size={15} />
                Group Scout · {room.members.length} of {MAX_GROUP_MEMBERS} friends
                {syncMode === "live" && <span className="group-live-dot">Live</span>}
              </p>
              <h1>{room.title}</h1>
              <div className="group-meta-pills">
                <span className="group-meta-pill">
                  <MapPin aria-hidden size={14} />
                  {room.place.name}
                </span>
                {effectiveDates && (
                  <span className="group-meta-pill group-num">
                    <Calendar aria-hidden size={14} />
                    {effectiveDates}
                  </span>
                )}
                {room.effective.max_price !== undefined && (
                  <span className="group-meta-pill group-num">
                    <DollarSign aria-hidden size={14} />
                    Under ${Math.round(room.effective.max_price)}
                  </span>
                )}
              </div>
            </div>

            <div className="group-header-actions">
              <button
                type="button"
                className="group-copy-btn"
                onClick={handleCopyInvite}
              >
                {copied ? <Check aria-hidden size={17} /> : <Copy aria-hidden size={17} />}
                {copied ? "Link copied" : "Copy invite link"}
              </button>
              {currentMember && (
                <button
                  type="button"
                  className="group-leave-btn"
                  onClick={handleLeave}
                  disabled={leaving}
                >
                  <LogOut aria-hidden size={16} />
                  {leaving ? "Leaving..." : "Leave room"}
                </button>
              )}
            </div>
          </div>

          {copyError && (
            <p className="group-band-note" role="status">
              {copyError}
            </p>
          )}

          {room.effective.dates_conflict && (
            <div className="group-conflict-banner" role="status">
              <AlertTriangle aria-hidden size={17} />
              <span>
                Your dates do not overlap yet, so we are showing Concerts across the wider window.
              </span>
            </div>
          )}

          <ul className="group-members-bar" aria-label="Friends in this room">
            {room.members.map((member, idx) => {
              const isYou = member.id === currentMember?.id;
              return (
                <li
                  key={member.id}
                  className={isYou ? "group-member-pill is-you" : "group-member-pill"}
                >
                  <span
                    className={`group-avatar ${AVATAR_TONES[idx % AVATAR_TONES.length]}`}
                    aria-hidden
                  >
                    {memberInitials(member.name)}
                  </span>
                  <span className="group-member-info">
                    <strong>
                      {member.name}
                      {isYou ? " (you)" : ""}
                    </strong>
                    <span className="group-member-sub">
                      {countOf(member.artists.length, "Artist")}
                    </span>
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      </header>

      <div className="group-room-body">
        {canJoin && (
          <section className="group-join-card" aria-labelledby="group-join-heading">
            <div className="group-join-head">
              <h2 id="group-join-heading">
                <UserPlus aria-hidden size={20} />
                Join this Group Scout room
              </h2>
              <p>Add your Taste so picks balance everyone in the group. No account needed.</p>
            </div>

            <form className="group-join-form" onSubmit={handleJoin} noValidate>
              <div className="group-join-grid">
                <div className="group-field">
                  <label htmlFor="join-name">Your name</label>
                  <input
                    id="join-name"
                    type="text"
                    required
                    maxLength={48}
                    placeholder="Sam"
                    value={joinName}
                    onChange={(e) => setJoinName(e.target.value)}
                  />
                </div>
                <div className="group-field">
                  <label htmlFor="join-start">Available from (optional)</label>
                  <input
                    id="join-start"
                    type="date"
                    min={today}
                    value={joinStart}
                    onChange={(e) => setJoinStart(e.target.value)}
                  />
                </div>
                <div className="group-field">
                  <label htmlFor="join-end">Available until (optional)</label>
                  <input
                    id="join-end"
                    type="date"
                    min={joinStart || today}
                    value={joinEnd}
                    onChange={(e) => setJoinEnd(e.target.value)}
                  />
                </div>
                <div className="group-field">
                  <label htmlFor="join-price">Max price $ (optional)</label>
                  <input
                    id="join-price"
                    type="number"
                    min={1}
                    max={10000}
                    step={1}
                    inputMode="numeric"
                    placeholder="60"
                    value={joinMaxPrice}
                    onChange={(e) => setJoinMaxPrice(e.target.value)}
                  />
                </div>
              </div>

              <div className="group-taste-block">
                <div className="group-taste-head">
                  <label htmlFor="join-artists">Your Taste (Artists)</label>
                  {savedTaste && savedTaste.artists.length > 0 && (
                    <button
                      type="button"
                      className="group-prefill-btn"
                      onClick={() => {
                        setJoinArtists((c) => mergeArtists(c, savedTaste.artists));
                        setJoinError(null);
                      }}
                    >
                      <Sparkles aria-hidden size={15} />
                      Use saved Taste ({savedTaste.artists.length})
                    </button>
                  )}
                </div>

                <div className="group-artist-entry">
                  <input
                    id="join-artists"
                    type="text"
                    placeholder="Type Artists (comma separated)"
                    value={joinArtistInput}
                    onChange={(e) => setJoinArtistInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        addJoinArtists();
                      }
                    }}
                  />
                  <button
                    type="button"
                    className="group-add-btn"
                    onClick={addJoinArtists}
                    aria-label="Add Artists to join"
                  >
                    <Plus aria-hidden size={18} />
                    Add
                  </button>
                </div>

                {joinArtists.length > 0 && (
                  <ul className="group-artist-chips" aria-label="Your selected Artists">
                    {joinArtists.map((artist) => (
                      <li key={artist} className="group-artist-chip">
                        <span>{artist}</span>
                        <button
                          type="button"
                          aria-label={`Remove ${artist}`}
                          onClick={() =>
                            setJoinArtists((c) => c.filter((item) => item !== artist))
                          }
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
                    const active = joinArtists.some(
                      (a) => a.toLowerCase() === artist.toLowerCase(),
                    );
                    return (
                      <button
                        key={artist}
                        type="button"
                        className="group-quick-chip"
                        aria-pressed={active}
                        onClick={() => toggleJoinQuickArtist(artist)}
                      >
                        {artist}
                      </button>
                    );
                  })}
                </div>
              </div>

              {joinError && (
                <p className="group-error" role="alert">
                  {joinError}
                </p>
              )}

              <div className="group-join-actions">
                <button type="submit" className="group-primary-btn" disabled={joining}>
                  {joining ? "Joining room..." : "Join room & rank picks"}
                </button>
              </div>
            </form>
          </section>
        )}

        {isFullForGuest && (
          <p className="group-full-note" role="status">
            This room is full ({MAX_GROUP_MEMBERS} of {MAX_GROUP_MEMBERS} friends). You can still
            browse the Group Poster and live votes.
          </p>
        )}

        {actionError && (
          <p className="group-error" role="alert">
            {actionError}
          </p>
        )}

        <section className="group-poster" aria-label="Group Poster">
          <div className="group-poster-bar">
            <div>
              <h2>
                <span className="group-num">{countOf(sortedPicks.length, "Concert")}</span>
              </h2>
              <p className="group-poster-sub">
                {sort === "fit"
                  ? "Ranked fairly across everyone's Taste so nobody is left out."
                  : "Ordered by group consensus and In votes."}
              </p>
            </div>

            <div className="group-sort" role="group" aria-label="Sort Group Poster">
              <button
                type="button"
                className="group-sort-btn"
                aria-pressed={sort === "fit"}
                onClick={() => setSort("fit")}
              >
                Best group fit
              </button>
              <button
                type="button"
                className="group-sort-btn"
                aria-pressed={sort === "votes"}
                onClick={() => setSort("votes")}
              >
                Top voted
              </button>
            </div>
          </div>

          {sortedPicks.length === 0 ? (
            <div className="group-empty">
              <h3>No Concerts fit the current dates and budget</h3>
              <p>
                Every Concert fact comes from Ticketmaster &amp; JamBase. Try widening the dates or
                starting a fresh room.
              </p>
              <Link href="/g" className="group-primary-btn">
                Start another Group Room
              </Link>
            </div>
          ) : (
            <ol className="group-grid">
              {sortedPicks.map((pick) => (
                <GroupConcertCard
                  key={pick.concert.id}
                  pick={pick}
                  currentMemberId={currentMember?.id ?? null}
                  memberNameById={memberNameById}
                  voting={votingConcertId === pick.concert.id}
                  onVote={handleVote}
                />
              ))}
            </ol>
          )}
        </section>
      </div>
    </>
  );
}

function GroupConcertCard({
  pick,
  currentMemberId,
  memberNameById,
  voting,
  onVote,
}: {
  pick: GroupPick;
  currentMemberId: string | null;
  memberNameById: Map<string, string>;
  voting: boolean;
  onVote: (concertId: string, vote: VoteChoice) => void;
}) {
  const { concert } = pick;
  const primaryName = concert.festival
    ? concert.name
    : concert.artists[0]?.name || concert.name;
  const subtitle = concert.festival ? null : showTitle(concert, primaryName);
  const timeText = formatConcertTime(concert);
  const locationText = [concert.venue, concert.city, concert.region].filter(Boolean).join(", ");
  const myVote = currentMemberId ? pick.member_votes[currentMemberId] : undefined;

  const votersByChoice = useMemo(() => {
    const groups: Record<VoteChoice, string[]> = { in: [], maybe: [], pass: [] };
    for (const [mId, choice] of Object.entries(pick.member_votes)) {
      const label = memberNameById.get(mId);
      if (label) groups[choice].push(label);
    }
    return groups;
  }, [pick.member_votes, memberNameById]);

  const hasAnyVotes =
    pick.vote_counts.in > 0 || pick.vote_counts.maybe > 0 || pick.vote_counts.pass > 0;

  return (
    <li
      className={pick.consensus_in ? "group-card is-consensus" : "group-card"}
      data-concert-id={concert.id}
    >
      <div className="group-card-media">
        {concert.image ? (
          // Source images come from arbitrary Ticketmaster/JamBase hosts.
          // eslint-disable-next-line @next/next/no-img-element
          <img src={concert.image} alt="" loading="lazy" />
        ) : (
          <div className="group-card-media-empty" aria-hidden />
        )}
        {concert.date && (
          <span className="group-card-date group-num">{formatMonthDay(concert.date)}</span>
        )}
        <div className="group-card-flags">
          {pick.consensus_in && <span className="group-flag is-consensus">Consensus · All In</span>}
          {!pick.consensus_in && pick.everyone_fits && (
            <span className="group-flag is-fit">Fits everyone</span>
          )}
        </div>
      </div>

      <div className="group-card-content">
        <h3 className="group-card-title">{primaryName}</h3>
        {subtitle && <p className="group-card-subtitle">{subtitle}</p>}

        <dl className="group-facts">
          {concert.date && (
            <div>
              <dt className="sr-only">Date</dt>
              <dd className="group-num">
                {formatDate(concert.date)}
                {timeText ? ` · ${timeText}` : ""}
              </dd>
            </div>
          )}
          {locationText && (
            <div>
              <dt className="sr-only">Venue</dt>
              <dd>{locationText}</dd>
            </div>
          )}
          {concert.price && (
            <div>
              <dt className="sr-only">Price</dt>
              <dd className="group-num">{formatPrice(concert.price, true)}</dd>
            </div>
          )}
        </dl>

        {pick.member_matches.length > 0 && (
          <ul className="group-badges" aria-label={`Match signals for ${primaryName}`}>
            {pick.member_matches.map((match) => (
              <li
                key={`${match.member_id}-${match.signal}`}
                className="group-badge"
                data-signal={match.signal}
                title={
                  match.via && match.signal !== "seed"
                    ? `${match.name}: ${match.badge} via ${match.via}`
                    : `${match.name}: ${match.badge} (${match.matched_artist})`
                }
              >
                <strong>{match.name}</strong>
                <span aria-hidden>·</span>
                <span>{match.badge}</span>
              </li>
            ))}
          </ul>
        )}

        <div className="group-votes" role="group" aria-label={`Vote on ${primaryName}`}>
          <button
            type="button"
            className="group-vote-btn is-in"
            aria-pressed={myVote === "in"}
            disabled={!currentMemberId || voting}
            onClick={() => onVote(concert.id, "in")}
          >
            <ThumbsUp aria-hidden size={15} />
            <span>In</span>
            <span className="group-vote-count group-num">{pick.vote_counts.in}</span>
          </button>
          <button
            type="button"
            className="group-vote-btn is-maybe"
            aria-pressed={myVote === "maybe"}
            disabled={!currentMemberId || voting}
            onClick={() => onVote(concert.id, "maybe")}
          >
            <HelpCircle aria-hidden size={15} />
            <span>Maybe</span>
            <span className="group-vote-count group-num">{pick.vote_counts.maybe}</span>
          </button>
          <button
            type="button"
            className="group-vote-btn is-pass"
            aria-pressed={myVote === "pass"}
            disabled={!currentMemberId || voting}
            onClick={() => onVote(concert.id, "pass")}
          >
            <ThumbsDown aria-hidden size={15} />
            <span>Pass</span>
            <span className="group-vote-count group-num">{pick.vote_counts.pass}</span>
          </button>
        </div>

        {hasAnyVotes && (
          <p className="group-voter-summary">
            {[
              votersByChoice.in.length > 0 ? `In: ${votersByChoice.in.join(", ")}` : null,
              votersByChoice.maybe.length > 0 ? `Maybe: ${votersByChoice.maybe.join(", ")}` : null,
              votersByChoice.pass.length > 0 ? `Pass: ${votersByChoice.pass.join(", ")}` : null,
            ]
              .filter(Boolean)
              .join(" · ")}
          </p>
        )}

        <div className="group-card-actions">
          <a
            href={concert.url}
            target="_blank"
            rel="noopener noreferrer"
            className="group-ticket-link"
            aria-label={`Tickets for ${concert.name}`}
          >
            Tickets
            <ExternalLink aria-hidden size={15} />
          </a>
          <AddToCalendar concert={concert} name={primaryName} />
        </div>
      </div>
    </li>
  );
}
