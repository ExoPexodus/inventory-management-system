"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Badge,
  EmptyState,
  ErrorState,
  PageHeader,
  Panel,
  SelectInput,
  SecondaryButton,
  TextInput,
} from "@/components/ui/primitives";

type Op = { id: string; email: string; role: string; is_active: boolean; created_at: string };

export default function StaffPage() {
  const [rows, setRows] = useState<Op[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [roleFilter, setRoleFilter] = useState("");
  const [search, setSearch] = useState("");

  const refresh = useCallback(async () => {
    const sp = new URLSearchParams();
    if (roleFilter) sp.set("role", roleFilter);
    if (search.trim()) sp.set("q", search.trim());
    const r = await fetch(`/api/ims/v1/admin/operators?${sp.toString()}`);
    if (r.ok) {
      setRows((await r.json()) as Op[]);
      setErr(null);
    } else {
      setErr(`Failed to load operators (${r.status})`);
    }
  }, [roleFilter, search]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function toggleActive(o: Op) {
    setMsg(null);
    const r = await fetch(`/api/ims/v1/admin/operators/${o.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_active: !o.is_active }),
    });
    setMsg(r.ok ? "Updated" : `Failed (${r.status})`);
    if (r.ok) await refresh();
  }

  async function setRole(o: Op, role: string) {
    setMsg(null);
    const r = await fetch(`/api/ims/v1/admin/operators/${o.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role }),
    });
    setMsg(r.ok ? "Role updated" : `Failed (${r.status})`);
    if (r.ok) await refresh();
  }

  return (
    <div className="space-y-7">
      <PageHeader
        kicker="Staff & permissions"
        title="Operator access"
        subtitle="Role assignment and activation controls for operator JWT logins."
      />
      {msg ? <Badge tone="good">{msg}</Badge> : null}
      {err ? <ErrorState detail={err} /> : null}
      <Panel
        title="Staff roster"
        subtitle="Updates are applied immediately on PATCH."
      >
        <div className="mb-4 flex flex-wrap gap-3">
          <TextInput
            placeholder="Search operator email…"
            className="min-w-[16rem]"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <SelectInput value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)}>
            <option value="">All roles</option>
            <option value="admin">admin</option>
            <option value="superadmin">superadmin</option>
            <option value="viewer">viewer</option>
          </SelectInput>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
          <thead>
            <tr className="border-b border-primary/10 text-xs uppercase tracking-wide text-primary/50">
              <th className="px-4 py-3">Email</th>
              <th className="px-4 py-3">Role</th>
              <th className="px-4 py-3">Active</th>
              <th className="px-4 py-3">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-primary/5">
            {rows.map((o) => (
              <tr key={o.id}>
                <td className="px-4 py-3 font-medium">{o.email}</td>
                <td className="px-4 py-3">
                  <SelectInput
                    className="py-1 text-xs"
                    value={o.role}
                    onChange={(e) => void setRole(o, e.target.value)}
                  >
                    <option value="admin">admin</option>
                    <option value="superadmin">superadmin</option>
                    <option value="viewer">viewer</option>
                  </SelectInput>
                </td>
                <td className="px-4 py-3">
                  <Badge tone={o.is_active ? "good" : "warn"}>{o.is_active ? "active" : "disabled"}</Badge>
                </td>
                <td className="px-4 py-3">
                  <SecondaryButton
                    type="button"
                    className="px-3 py-1 text-xs"
                    onClick={() => void toggleActive(o)}
                  >
                    Toggle active
                  </SecondaryButton>
                </td>
              </tr>
            ))}
          </tbody>
          </table>
        </div>
        {rows.length === 0 ? <EmptyState title="No operators found" detail="Seed or create operator accounts first." /> : null}
      </Panel>
    </div>
  );
}
