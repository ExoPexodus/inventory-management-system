import { redirect } from "next/navigation";
import { cookies } from "next/headers";
import { PLATFORM_JWT_COOKIE } from "@/lib/auth/constants";

export default async function RootPage() {
  const jar = await cookies();
  const token = jar.get(PLATFORM_JWT_COOKIE)?.value;
  if (token) {
    redirect("/dashboard");
  }
  redirect("/login");
}
