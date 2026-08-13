import { redirect } from "next/navigation";
import { auth } from "@/../auth";
import { ApiKeysPanel } from "@/components/api-keys/api-keys-panel";

export default async function ApiKeysPage() {
  const session = await auth();
  if (!session?.user) redirect("/login");
  return <ApiKeysPanel />;
}
