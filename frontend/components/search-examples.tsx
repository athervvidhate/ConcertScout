import { Button } from "@base-ui/react/button";

import { SEARCH_EXAMPLES } from "@/lib/search-examples";

type Props = {
  onExample: (text: string) => void;
  // Every Search needs a bot check token, which arrives a moment after the page.
  ready: boolean;
};

export function SearchExamples({ onExample, ready }: Props) {
  return (
    <section className="home-try" aria-labelledby="home-try">
      <h2 id="home-try">Try one of these</h2>
      <ul className="home-examples">
        {SEARCH_EXAMPLES.map((example) => (
          <li key={example}>
            <Button type="button" disabled={!ready} onClick={() => onExample(example)}>
              {example}
            </Button>
          </li>
        ))}
      </ul>
    </section>
  );
}
