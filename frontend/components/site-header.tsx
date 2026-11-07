"use client";

import { Menu } from "@base-ui/react/menu";
import { Menu as MenuIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

type Props = {
  /** Returns the page that holds a Search to its resting state. */
  onHome?: () => void;
  /** The resting home page already says Concert Scout at full size. */
  hideBrand?: boolean;
  onTaste?: () => void;
  tasteLabel?: string;
};

export function SiteHeader({ onHome, hideBrand, onTaste, tasteLabel }: Props) {
  const onSavedPage = usePathname() === "/saved";

  return (
    <header className="site-header">
      {!hideBrand && (
        <Link href="/" className="site-brand" onClick={onHome}>
          Concert Scout
        </Link>
      )}
      {(onTaste || !onSavedPage) && (
        <Menu.Root modal={false}>
          <Menu.Trigger className="site-menu" aria-label="Menu">
            <MenuIcon aria-hidden size={26} />
          </Menu.Trigger>
          <Menu.Portal>
            <Menu.Positioner className="site-menu-position" align="end" sideOffset={4}>
              <Menu.Popup className="site-menu-popup">
                {!onSavedPage && (
                  <Menu.LinkItem render={<Link href="/saved" />} closeOnClick>
                    Saved Concerts
                  </Menu.LinkItem>
                )}
                {onTaste && <Menu.Item onClick={onTaste}>{tasteLabel}</Menu.Item>}
              </Menu.Popup>
            </Menu.Positioner>
          </Menu.Portal>
        </Menu.Root>
      )}
    </header>
  );
}
