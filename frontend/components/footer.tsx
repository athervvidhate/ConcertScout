import Link from "next/link";

export function Footer() {
  return (
    <footer className="site-footer">
      <div>
        <Link href="/privacy" target="_blank" rel="noopener noreferrer">Privacy</Link>
        <a href="https://www.jambase.com" target="_blank" rel="nofollow noopener noreferrer">Concert data by JamBase</a>
        <a href="https://atherv.com" target="_blank" rel="noopener noreferrer">Atherv Vidhate</a>
      </div>
    </footer>
  );
}
