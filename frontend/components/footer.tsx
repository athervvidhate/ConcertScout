import Link from "next/link";

export function Footer() {
  return (
    <footer className="site-footer">
      <Link href="/privacy" target="_blank" rel="noopener noreferrer">Privacy</Link>
      <Link href="/credits" target="_blank" rel="noopener noreferrer">Data credits</Link>
      <a href="https://atherv.com" target="_blank" rel="noopener noreferrer">Atherv Vidhate</a>
    </footer>
  );
}
