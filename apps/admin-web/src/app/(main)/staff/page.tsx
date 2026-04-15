import { redirect } from "next/navigation";

// Staff management has moved to the unified Team page.
export default function StaffPage() {
  redirect("/team");
}
