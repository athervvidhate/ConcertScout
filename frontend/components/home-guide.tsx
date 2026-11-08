import { Button } from "@base-ui/react/button";

const STEPS = [
  {
    title: "Say it your way",
    text: "Name an Artist, a sound or a city. Shorthand like UKG in SF works too.",
  },
  {
    title: "We check the listings",
    text: "Real Concert listings are matched to Artists who sound like what you asked for.",
  },
  {
    title: "Keep the good ones",
    text: "Go through the Poster one Ticket at a time. Save what you like and skip the rest.",
  },
];

type Props = {
  /** A connected visitor already has both of these from the shelf and the menu. */
  personal: boolean;
  locationLabel: string;
  onLocation: () => void;
  onTaste: () => void;
};

export function HomeGuide({ personal, locationLabel, onLocation, onTaste }: Props) {
  return (
    <div className="home-guide">
      <section aria-labelledby="home-how">
        <h2 id="home-how">How it works</h2>
        <ol className="ticket-strip">
          {STEPS.map(({ title, text }) => (
            <li key={title}>
              <h3>{title}</h3>
              <p>{text}</p>
            </li>
          ))}
        </ol>
      </section>

      {personal && <section className="home-personal" aria-labelledby="home-yours">
        <h2 id="home-yours">Make it yours</h2>
        <p>
          Share your location and Searches look near you unless you name a place. Add your Taste
          by connecting Spotify or importing from Last.fm, ListenBrainz or a list, and we can find
          Concerts for the Artists you already play. With Spotify and your location, this page also
          shows your Artists near you for the next two months.
        </p>
        <div>
          <Button type="button" onClick={onLocation}>
            {locationLabel}
          </Button>
          <Button type="button" onClick={onTaste}>
            Add your Taste
          </Button>
        </div>
      </section>}
    </div>
  );
}
