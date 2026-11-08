"use client";

import { Menu } from "@base-ui/react/menu";
import { Menu as MenuIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { Brand } from "@/components/brand";
import { useSavedConcerts } from "@/lib/saved";
import { toggleTheme } from "@/lib/theme";
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
  useEffect(() => {
    const system = matchMedia("(prefers-color-scheme:dark)");
    const changed = () => {
      try {
        if (localStorage.getItem("concert-scout-mode")) return;
      } catch {
        /* Use system. */
      }
      document.documentElement.dataset.mode = system.matches ? "dark" : "light";
    };
    system.addEventListener("change", changed);
    return () => system.removeEventListener("change", changed);
  }, []);
  const account = useAccount();
  const { saved } = useSavedConcerts();
  const [signingIn, setSigningIn] = useState(false);
  const showSaved = path !== "/saved";
  const showSignIn = account.status === "guest";
  const showAccount = account.status === "signed-in" && path !== "/account";

  return (
    <header
      className={hideBrand ? "site-header site-header-bare" : "site-header"}
    >
      {!hideBrand && (
        <Link href="/" className="site-brand" onClick={onHome}>
          <Brand />
        </Link>
      )}
      {(onTaste || showSaved || showSignIn || showAccount) && (
        <Menu.Root modal={false}>
          <Menu.Trigger className="site-menu" aria-label="Menu">
            <MenuIcon aria-hidden size={26} />
          </Menu.Trigger>
          <Menu.Portal>
            <Menu.Positioner
              className="site-menu-position"
              align="end"
              sideOffset={4}
            >
              <Menu.Popup className="site-menu-popup">
                <Menu.Item onClick={toggleTheme}>
                  Switch light / dark mode
                </Menu.Item>
                {showSaved && (
                  <Menu.LinkItem render={<Link href="/saved" />} closeOnClick>
                    Saved Concerts{" "}
                    {saved.length > 0 && (
                      <span
                        className="saved-count"
                        aria-label={`${saved.length} saved`}
                      >
                        {saved.length}
                      </span>
                    )}
                  </Menu.LinkItem>
                )}
                {onTaste && (
                  <Menu.Item onClick={onTaste}>{tasteLabel}</Menu.Item>
                )}
                {showSignIn && (
                  <Menu.Item onClick={() => setSigningIn(true)}>
                    Sign in
                  </Menu.Item>
                )}
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
      {account.status !== "off" && (
        <AccountDialog open={signingIn} onOpenChange={setSigningIn} />
      )}
    </header>
  );
}
