import { redirect } from "next/navigation";
import { auth } from "@/../auth";
import { FleetGraphs } from "@/components/graphs/fleet-graphs";

export default async function GraphsPage() {
  const session = await auth();
  if (!session?.user) redirect("/login");
  return <FleetGraphs />;
}
