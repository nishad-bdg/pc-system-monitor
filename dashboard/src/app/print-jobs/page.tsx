import { redirect } from "next/navigation";
import { auth } from "@/../auth";
import { PrintActivity } from "@/components/print-jobs/print-activity";

export default async function PrintJobsPage() {
  const session = await auth();
  if (!session?.user) redirect("/login");
  return <PrintActivity />;
}
