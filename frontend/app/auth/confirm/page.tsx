import type { Metadata } from "next";

import { ConfirmSignIn } from "@/components/confirm-sign-in";
import { SiteHeader } from "@/components/site-header";

export const metadata: Metadata = { title: "Signing in · Concert Scout" };

export default function ConfirmPage() {
  return (
    <main className="scout information">
      <SiteHeader />
      <ConfirmSignIn />
    </main>
  );
}
