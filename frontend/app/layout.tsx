import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";
import { Footer } from "@/components/footer";
import { THEME_BOOT } from "@/lib/theme";
const poster = localFont({src:"./fonts/anton.woff2", variable:"--font-poster", display:"swap"});
const ui = localFont({src:"./fonts/bricolage.woff2", variable:"--font-ui", display:"swap"});

export const metadata: Metadata = {
  title: "Concert Scout",
  description: "Find live music you would want to see.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{__html: THEME_BOOT}} /></head>
      <body className={`${poster.variable} ${ui.variable} `}>{children}<Footer /></body>
    </html>
  );
}
