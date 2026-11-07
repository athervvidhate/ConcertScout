import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Concert Scout",
  description: "Find live music you would want to see.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body className="bg-stone-50 text-stone-900">{children}</body>
    </html>
  );
}
