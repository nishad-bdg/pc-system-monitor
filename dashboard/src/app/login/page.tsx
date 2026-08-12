import { redirect } from "next/navigation";
import { auth } from "@/../auth";
import { LoginForm } from "@/components/login-form";

export default async function LoginPage() {
  const session = await auth();
  if (session?.user) redirect("/dashboard");

  return (
    <div className="flex flex-1 items-center justify-center p-6">
      <div className="w-full max-w-sm rounded-2xl border border-gray-200 bg-white p-8 shadow-sm">
        <h1 className="text-2xl font-semibold text-gray-900">System Info</h1>
        <p className="mt-1 text-sm text-gray-500">
          Sign in to the admin dashboard
        </p>
        <LoginForm />
      </div>
    </div>
  );
}