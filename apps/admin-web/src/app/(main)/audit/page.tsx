"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Avatar,
  Badge,
  PageHeader,
  Panel,
  SecondaryButton,
  SearchBar,
} from "@/components/ui/primitives";
import { DateInput } from "@/components/ui/DateInput";

type AuditEvent = {
  id: string;
  actor: string;
  action: string;
  resource_type: string;
  resource_id?: string | null;
  ip_address?: string | null;
  created_at: string;
};

type Page = { items: AuditEvent[]; next_cursor: string | null };

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
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [rows, setRows] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [nextCursor, setNextCursor] = useState<string | null>(null);

  // Track current filter context to reset rows on filter change
  const filterKey = useRef("");

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), 300);
    return () => clearTimeout(t);
  }, [q]);

  const buildUrl = useCallback(
    (cursor?: string) => {
      const sp = new URLSearchParams();
      if (debounced) sp.set("q", debounced);
      if (fromDate) sp.set("from_date", fromDate);
      if (toDate) sp.set("to_date", toDate);
      if (cursor) sp.set("after", cursor);
      return `/api/ims/v1/admin/audit-log?${sp.toString()}`;
    },
    [debounced, fromDate, toDate]
  );

  const load = useCallback(async () => {
    setLoading(true);
    setRows([]);
    setNextCursor(null);
    filterKey.current = buildUrl();
    try {
      const r = await fetch(buildUrl());
      if (!r.ok) return;
      const data = (await r.json()) as Page;
      setRows(Array.isArray(data.items) ? data.items : []);
      setNextCursor(data.next_cursor ?? null);
    } finally {
      setLoading(false);
    }
  }, [buildUrl]);

  useEffect(() => { void load(); }, [load]);

  async function loadMore() {
    if (!nextCursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const r = await fetch(buildUrl(nextCursor));
      if (!r.ok) return;
      const data = (await r.json()) as Page;
      setRows((prev) => [...prev, ...(Array.isArray(data.items) ? data.items : [])]);
      setNextCursor(data.next_cursor ?? null);
    } finally {
      setLoadingMore(false);
    }
  }

  return (
    <div className="space-y-8">
      <PageHeader
        kicker="Security"
        title="Audit log"
        subtitle="Immutable trail of privileged actions across your tenant."
      />

      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-outline-variant/10 bg-surface-container-low p-4 shadow-sm">
        <SearchBar className="min-w-[14rem] flex-1" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search actor, action, resource…" />
        <DateInput className="min-w-[10rem]" value={fromDate} onChange={setFromDate} placeholder="From date" />
        <DateInput className="min-w-[10rem]" value={toDate} onChange={setToDate} placeholder="To date" />
        {(fromDate || toDate) && (
          <SecondaryButton type="button" onClick={() => { setFromDate(""); setToDate(""); }}>
            Clear dates
          </SecondaryButton>
        )}
      </div>

      <Panel title="Event log" subtitle={`${rows.length}${nextCursor ? "+" : ""} events`} noPad>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
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
                  <td colSpan={5} className="px-6 py-8 text-on-surface-variant">Loading events…</td>
                </tr>
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-6 py-8 text-center text-on-surface-variant">No audit events match your search.</td>
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
                      <span>{e.resource_type}</span>
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
        {nextCursor && (
          <div className="border-t border-outline-variant/10 px-6 py-4">
            <SecondaryButton type="button" disabled={loadingMore} onClick={() => void loadMore()}>
              {loadingMore ? "Loading…" : "Load more"}
            </SecondaryButton>
          </div>
        )}
      </Panel>
    </div>
  );
}
