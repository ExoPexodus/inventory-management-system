"use client";

import { useEffect, useState } from "react";
import { Breadcrumbs, PageHeader, PrimaryButton, TextInput } from "@/components/ui/primitives";

export default function SettingsCustomerGroupsPage() {
  const [customerGroups, setCustomerGroups] = useState<Array<{ id: string; name: string; colour: string | null }>>([]);
  const [newGroupName, setNewGroupName] = useState("");
  const [groupsLoading, setGroupsLoading] = useState(true);
  const [groupsError, setGroupsError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const r = await fetch("/api/ims/v1/admin/customer-groups");
        if (r.ok) setCustomerGroups(await r.json() as Array<{ id: string; name: string; colour: string | null }>);
      } catch {
        setGroupsError("Failed to load groups");
      } finally {
        setGroupsLoading(false);
      }
    })();
  }, []);

  async function createGroup() {
    if (!newGroupName.trim()) return;
    setGroupsError(null);
    try {
      const r = await fetch("/api/ims/v1/admin/customer-groups", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newGroupName.trim() }),
      });
      if (r.ok) {
        const g = await r.json() as { id: string; name: string; colour: string | null };
        setCustomerGroups((prev) => [...prev, g].sort((a, b) => a.name.localeCompare(b.name)));
        setNewGroupName("");
      } else {
        const b = await r.json().catch(() => ({})) as { detail?: string };
        setGroupsError(b.detail === "group_name_conflict" ? "A group with this name already exists." : (b.detail ?? "Failed to create group"));
      }
    } catch {
      setGroupsError("Network error. Please try again.");
    }
  }

  async function deleteGroup(id: string) {
    try {
      const r = await fetch(`/api/ims/v1/admin/customer-groups/${id}`, { method: "DELETE" });
      if (r.ok) setCustomerGroups((prev) => prev.filter((g) => g.id !== id));
    } catch {
      setGroupsError("Failed to delete group.");
    }
  }

  return (
    <div className="space-y-8">
      <Breadcrumbs items={[{ label: "Settings", href: "/settings" }, { label: "Customer Groups" }]} />
      <PageHeader kicker="Settings" title="Customer Groups" subtitle="Manage customer segment labels for reporting and targeting." />

      <section className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm space-y-4">
        <h3 className="font-headline text-lg font-bold text-primary">Customer Groups</h3>
        {groupsLoading ? (
          <p className="text-sm text-on-surface-variant">Loading groups…</p>
        ) : (
          <>
            <div className="space-y-2">
              {customerGroups.map((g) => (
                <div key={g.id} className="flex items-center justify-between rounded-lg border border-outline-variant/10 px-4 py-2">
                  <span className="text-sm font-medium text-on-surface">{g.name}</span>
                  <button type="button" onClick={() => void deleteGroup(g.id)} className="text-xs text-error hover:underline">Delete</button>
                </div>
              ))}
              {customerGroups.length === 0 && <p className="text-sm text-on-surface-variant">No groups yet. Create one below.</p>}
            </div>
            {groupsError && <p className="text-sm text-error">{groupsError}</p>}
            <div className="flex gap-2">
              <TextInput className="flex-1" placeholder="Group name, e.g. VIP" value={newGroupName} onChange={(e) => setNewGroupName(e.target.value)} />
              <PrimaryButton type="button" disabled={!newGroupName.trim()} onClick={() => void createGroup()}>Add group</PrimaryButton>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
