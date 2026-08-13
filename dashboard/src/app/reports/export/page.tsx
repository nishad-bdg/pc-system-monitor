import { redirect } from "next/navigation";
import { auth } from "@/../auth";
import { ReportExportPanel } from "@/components/reports/report-export-panel";

export default async function ReportExportPage() {
  const session = await auth();
  if (!session?.user) redirect("/login");
  return <ReportExportPanel />;
}
