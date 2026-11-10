import type { Metadata } from "next";
import { Anton, Bricolage_Grotesque } from "next/font/google";
import "./globals.css";
import { Footer } from "@/components/footer";
import { SEARCH_BOOT } from "@/lib/search-session";
import { THEME_BOOT } from "@/lib/theme";
// Every subset is self-hosted at build time; the browser fetches a non-Latin one only for a name that needs it.
const poster = Anton({weight:"400", subsets:["latin"], variable:"--font-poster", display:"swap"});
const ui = Bricolage_Grotesque({subsets:["latin"], variable:"--font-ui", display:"swap"});

export const metadata: Metadata = {
  title: "Concert Scout",
  description: "Find live music you would want to see.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{__html: `${THEME_BOOT};${SEARCH_BOOT}`}} /></head>
      <body className={`${poster.variable} ${ui.variable} `}>{children}<Footer /></body>
    </html>
  );
}
