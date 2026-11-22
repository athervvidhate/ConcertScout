import type { Metadata } from "next";

import { GroupRoom } from "@/components/group-room";

type Props = { params: Promise<{ id: string }> };

export const metadata: Metadata = {
  title: "Group Scout · Concert Scout",
  description: "Plan a Concert with 2 to 6 friends, match everyone's Taste fairly, and vote live.",
};

export default async function GroupRoomPage({ params }: Props) {
  const { id } = await params;
  return (
    <main className="scout group-page">
      <GroupRoom roomId={id} />
    </main>
  );
}
