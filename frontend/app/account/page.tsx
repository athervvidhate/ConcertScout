import type { Metadata } from "next";

import { AccountSettings } from "@/components/account-settings";
import { SiteHeader } from "@/components/site-header";

export const metadata: Metadata = { title: "Account · Concert Scout" };

export default function AccountPage() {
  return (
    <main className="scout information">
      <SiteHeader />
      <AccountSettings />
    </main>
  );
}
