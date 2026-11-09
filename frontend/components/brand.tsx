import Image from "next/image";

/** Both renditions are paths, so the wordmark never depends on a downloaded font. */
export function Brand({ large = false }: { large?: boolean }) {
  return (
    <span className={`brand-lockup ${large ? "brand-large" : ""}`}>
      <Image
        className="brand-light"
        src="/brand/logo-light.svg"
        alt="Concert Scout"
        width={439}
        height={64}
        priority
      />
      <Image
        className="brand-dark"
        src="/brand/logo-dark.svg"
        alt="Concert Scout"
        width={439}
        height={64}
        priority
      />
    </span>
  );
}
