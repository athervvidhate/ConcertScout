import type { Metadata } from "next";
import { Anton, Bricolage_Grotesque, Big_Shoulders, Hanken_Grotesk, Doto } from "next/font/google";
import "./globals.css";
const poster = Anton({ subsets: ["latin"], weight: "400", variable: "--font-poster" });
const ui = Bricolage_Grotesque({ subsets: ["latin"], variable: "--font-ui" });
const display = Big_Shoulders({ subsets: ["latin"], weight: "800", variable: "--font-display" });
const body = Hanken_Grotesk({ subsets: ["latin"], variable: "--font-body" });
const date = Doto({ subsets: ["latin"], weight: "800", variable: "--font-date" });

export const metadata: Metadata = {
  title: "Concert Scout",
  description: "Find live music you would want to see.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body className={`${poster.variable} ${ui.variable} ${display.variable} ${body.variable} ${date.variable}`}>{children}</body>
    </html>
  );
}
