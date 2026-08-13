import { redirect } from "next/navigation";
import { auth } from "@/../auth";
import { GroupsPanel } from "@/components/groups/groups-panel";

export default async function GroupsPage() {
  const session = await auth();
  if (!session?.user) redirect("/login");
  return <GroupsPanel />;
}
