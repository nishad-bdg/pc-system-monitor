import { redirect } from "next/navigation";
import { auth } from "@/../auth";
import { FleetOverview } from "@/components/overview/fleet-overview";

export default async function OverviewPage() {
  const session = await auth();
  if (!session?.user) redirect("/login");
  return <FleetOverview />;
}
