import { Suspense } from "react";
import { LoginClient } from "./login-client";

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <main className="flex min-h-screen items-center justify-center text-sm text-primary/60">Loading…</main>
      }
    >
      <LoginClient />
    </Suspense>
  );
}
