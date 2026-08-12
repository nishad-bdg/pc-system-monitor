import { redirect } from "next/navigation";
import { auth } from "@/../auth";
import { LoginForm } from "@/components/login-form";

export default async function LoginPage() {
  const session = await auth();
  if (session?.user) redirect("/dashboard");

  return (
    <div className="flex flex-1 items-center justify-center p-6">
      <div className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white/90 p-8 shadow-lg shadow-slate-300/40 backdrop-blur">
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-blue-600">
          System Info
        </p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">
          Admin sign in
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Monitor machines across your fleet
        </p>
        <LoginForm />
      </div>
    </div>
  );
}
