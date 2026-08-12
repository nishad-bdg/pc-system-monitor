import { redirect } from "next/navigation";
import { auth } from "@/../auth";
import { ReportPcDetail } from "@/components/reports/report-pc-detail";

export default async function ReportPcPage({
  params,
}: {
  params: Promise<{ key: string }>;
}) {
  const session = await auth();
  if (!session?.user) redirect("/login");
  const { key } = await params;
  return <ReportPcDetail encodedKey={key} />;
}
