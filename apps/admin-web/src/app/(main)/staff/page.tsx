"use client";

import { useEffect, useState } from "react";

type Op = { id: string; email: string; role: string; is_active: boolean; created_at: string };

export default function StaffPage() {
  const [rows, setRows] = useState<Op[]>([]);
  const [msg, setMsg] = useState<string | null>(null);

  async function refresh() {
    const r = await fetch("/api/ims/v1/admin/operators");
    if (r.ok) setRows((await r.json()) as Op[]);
  }

  useEffect(() => {
    void refresh();
  }, []);

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
    <div className="space-y-6">
      <header>
        <p className="text-xs font-semibold uppercase tracking-wider text-primary/50">Staff & permissions</p>
        <h1 className="font-display text-3xl font-semibold tracking-tight text-primary">Operators</h1>
        <p className="mt-1 text-sm text-primary/70">Roles are informational in MVP; expand with fine-grained ACL later.</p>
      </header>
      {msg ? <p className="text-sm text-primary/80">{msg}</p> : null}
      <div className="overflow-x-auto rounded-xl border border-primary/10 bg-white/90 shadow-sm">
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
                  <select
                    className="rounded border border-primary/15 px-2 py-1 text-xs"
                    value={o.role}
                    onChange={(e) => void setRole(o, e.target.value)}
                  >
                    <option value="admin">admin</option>
                    <option value="superadmin">superadmin</option>
                    <option value="viewer">viewer</option>
                  </select>
                </td>
                <td className="px-4 py-3">
                  <span
                    className={
                      o.is_active ? "text-emerald-700" : "text-primary/40"
                    }
                  >
                    {o.is_active ? "yes" : "no"}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <button
                    type="button"
                    className="text-xs font-medium text-primary underline"
                    onClick={() => void toggleActive(o)}
                  >
                    Toggle active
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
