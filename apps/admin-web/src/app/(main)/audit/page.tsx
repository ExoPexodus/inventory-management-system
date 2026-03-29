"use client";

import { useCallback, useEffect, useState } from "react";
import { Avatar, Badge, SearchBar } from "@/components/ui/primitives";

type AuditEvent = {
  id: string;
  actor: string;
  action: string;
  resource: string;
  resource_id?: string | null;
  ip_address?: string | null;
  created_at: string;
};

type Page = { items: AuditEvent[] };

function actionTone(action: string): "default" | "good" | "warn" | "danger" {
  const a = action.toLowerCase();
  if (a.includes("delete") || a.includes("destroy") || a.includes("revoke")) return "danger";
  if (a.includes("fail") || a.includes("denied") || a.includes("blocked")) return "warn";
  if (a.includes("create") || a.includes("insert") || a.includes("login")) return "good";
  return "default";
}

export default function AuditPage() {
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [rows, setRows] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), 300);
    return () => clearTimeout(t);
  }, [q]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const sp = new URLSearchParams();
      if (debounced) sp.set("q", debounced);
      sp.set("limit", "100");
      const r = await fetch(`/api/ims/v1/admin/audit-log?${sp.toString()}`);
      if (!r.ok) return;
      const data = (await r.json()) as Page;
      setRows(Array.isArray(data.items) ? data.items : []);
    } finally {
      setLoading(false);
    }
  }, [debounced]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-8">
      <div>
        <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Security</p>
        <h2 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface">Audit log</h2>
        <p className="mt-2 font-light text-on-surface-variant">Immutable trail of privileged actions across your tenant.</p>
      </div>

      <div className="max-w-md">
        <SearchBar value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search actor, action, resource…" />
      </div>

      <div className="overflow-hidden rounded-xl border border-outline-variant/10 bg-surface-container-lowest shadow-sm">
        <div className="border-b border-outline-variant/10 px-6 py-4">
          <h3 className="font-headline text-lg font-bold text-primary">Event log</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[880px] text-left text-sm">
            <thead>
              <tr className="border-b border-outline-variant/10">
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Actor</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Action</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Resource</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">IP</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Time</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/10">
              {loading ? (
                <tr>
                  <td colSpan={5} className="px-6 py-8 text-on-surface-variant">
                    Loading events…
                  </td>
                </tr>
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-6 py-8 text-center text-on-surface-variant">
                    No audit events match your search.
                  </td>
                </tr>
              ) : (
                rows.map((e) => (
                  <tr key={e.id} className="transition-colors hover:bg-surface-container-low/50">
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <Avatar name={e.actor || "?"} />
                        <span className="font-medium text-on-surface">{e.actor}</span>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <Badge tone={actionTone(e.action)}>{e.action}</Badge>
                    </td>
                    <td className="px-6 py-4 text-on-surface">
                      <span>{e.resource}</span>
                      {e.resource_id ? (
                        <span className="mt-0.5 block font-mono text-xs text-on-surface-variant">{e.resource_id}</span>
                      ) : null}
                    </td>
                    <td className="px-6 py-4 font-mono text-xs text-on-surface-variant">{e.ip_address ?? "—"}</td>
                    <td className="px-6 py-4 text-on-surface-variant">{new Date(e.created_at).toLocaleString()}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
