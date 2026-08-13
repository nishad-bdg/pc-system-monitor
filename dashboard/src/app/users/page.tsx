import { redirect } from "next/navigation";
import { auth } from "@/../auth";
import { UsersPanel } from "@/components/users/users-panel";

export default async function UsersPage() {
  const session = await auth();
  if (!session?.user) redirect("/login");
  if (session.user.role !== "super_admin") redirect("/dashboard");
  return <UsersPanel />;
}
