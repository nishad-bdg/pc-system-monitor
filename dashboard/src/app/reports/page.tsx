import { redirect } from "next/navigation";
import { auth } from "@/../auth";
import { ReportsBrowser } from "@/components/reports/reports-browser";

export default async function ReportsPage() {
  const session = await auth();
  if (!session?.user) redirect("/login");
  return <ReportsBrowser />;
}
