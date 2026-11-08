"use client";

import { Menu } from "@base-ui/react/menu";
import { Menu as MenuIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { AccountDialog } from "@/components/account-dialog";
import { useAccount } from "@/lib/account";

type Props = {
  /** Returns the page that holds a Search to its resting state. */
  onHome?: () => void;
  /** The resting home page already says Concert Scout at full size. */
  hideBrand?: boolean;
  onTaste?: () => void;
  tasteLabel?: string;
};

export function SiteHeader({ onHome, hideBrand, onTaste, tasteLabel }: Props) {
  const path = usePathname();
  const account = useAccount();
  const [signingIn, setSigningIn] = useState(false);
  const showSaved = path !== "/saved";
  const showSignIn = account.status === "guest";
  const showAccount = account.status === "signed-in" && path !== "/account";

  return (
    <header className={hideBrand ? "site-header site-header-bare" : "site-header"}>
      {!hideBrand && (
        <Link href="/" className="site-brand" onClick={onHome}>
          Concert Scout
        </Link>
      )}
      {(onTaste || showSaved || showSignIn || showAccount) && (
        <Menu.Root modal={false}>
          <Menu.Trigger className="site-menu" aria-label="Menu">
            <MenuIcon aria-hidden size={26} />
          </Menu.Trigger>
          <Menu.Portal>
            <Menu.Positioner className="site-menu-position" align="end" sideOffset={4}>
              <Menu.Popup className="site-menu-popup">
                {showSaved && (
                  <Menu.LinkItem render={<Link href="/saved" />} closeOnClick>
                    Saved Concerts
                  </Menu.LinkItem>
                )}
                {onTaste && <Menu.Item onClick={onTaste}>{tasteLabel}</Menu.Item>}
                {showSignIn && <Menu.Item onClick={() => setSigningIn(true)}>Sign in</Menu.Item>}
                {showAccount && (
                  <Menu.LinkItem render={<Link href="/account" />} closeOnClick>
                    Account
                  </Menu.LinkItem>
                )}
              </Menu.Popup>
            </Menu.Positioner>
          </Menu.Portal>
        </Menu.Root>
      )}
      {account.status !== "off" && <AccountDialog open={signingIn} onOpenChange={setSigningIn} />}
    </header>
  );
}
