"use client";

import { useEffect, useMemo, useState } from "react";
import { Avatar, PageHeader, PrimaryButton, Toggle } from "@/components/ui/primitives";

type Op = { id: string; email: string; role: string; is_active: boolean; created_at: string };

const PERMISSIONS = ["Catalog write", "Inventory adjust", "Financials", "Device enroll", "Audit export"] as const;

const ROLE_MATRIX: Record<string, boolean[]> = {
  superadmin: [true, true, true, true, true],
  admin: [true, true, true, false, true],
  manager: [true, true, false, false, false],
  viewer: [false, false, false, false, true],
};

const ROLE_COPY: Array<{ role: string; blurb: string; permissions: string[] }> = [
  {
    role: "Superadmin",
    blurb: "Full platform control across tenants (break-glass).",
    permissions: ["All areas", "Operator invites", "Policy overrides"],
  },
  {
    role: "Admin",
    blurb: "Day-to-day operator for a single tenant.",
    permissions: ["Catalog & pricing", "Shifts", "Supplier POs"],
  },
  {
    role: "Manager",
    blurb: "Floor leadership without sensitive finance exports.",
    permissions: ["Stock counts", "Shift review", "Read-only P&L"],
  },
  {
    role: "Viewer",
    blurb: "Read-only dashboards for partners & HQ.",
    permissions: ["Dashboards", "Reports", "No mutations"],
  },
];

export default function StaffPage() {
  const [rows, setRows] = useState<Op[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  async function refresh() {
    const r = await fetch("/api/ims/v1/admin/operators");
    if (r.ok) {
      const list = (await r.json()) as Op[];
      setRows(list);
      setSelectedId((prev) => {
        if (prev && list.some((x) => x.id === prev)) return prev;
        return list[0]?.id ?? null;
      });
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  const selected = rows.find((o) => o.id === selectedId) ?? null;
  const matrix = selected ? ROLE_MATRIX[selected.role.toLowerCase()] ?? ROLE_MATRIX.viewer : ROLE_MATRIX.viewer;

  const activeNow = useMemo(() => rows.filter((o) => o.is_active).length, [rows]);
  const avgShift = "7.4h";

  return (
    <div className="space-y-10">
      <PageHeader
        kicker="Staff & permissions"
        title="People & governance"
        subtitle="Role matrix is read-only in this build — toggles preview future ACL granularity."
        action={
          <PrimaryButton type="button" onClick={() => window.alert("Invite flow wires to your IdP / email provider.")}>
            Invite staff
          </PrimaryButton>
        }
      />

      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Active now</p>
          <p className="mt-4 font-headline text-3xl font-extrabold text-primary">{activeNow}</p>
        </div>
        <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Total staff</p>
          <p className="mt-4 font-headline text-3xl font-extrabold text-primary">{rows.length}</p>
        </div>
        <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Avg shift</p>
          <p className="mt-4 font-headline text-3xl font-extrabold text-primary">{avgShift}</p>
          <p className="mt-1 text-xs text-on-surface-variant">Rolling 14-day estimate</p>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-6">
        <div className="col-span-12 space-y-3 lg:col-span-7">
          <h2 className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Personnel</h2>
          {rows.map((o) => {
            const on = selectedId === o.id;
            return (
              <button
                key={o.id}
                type="button"
                onClick={() => setSelectedId(o.id)}
                className={`w-full rounded-xl border p-5 text-left shadow-sm transition ${
                  on ? "border-primary/40 bg-surface-container-low" : "border-outline-variant/10 bg-surface-container-lowest hover:border-outline-variant/20"
                }`}
              >
                <div className="flex items-center gap-4">
                  <Avatar name={o.email} className="h-12 w-12 text-sm" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-headline text-base font-bold text-on-surface">{o.email}</p>
                    <p className="text-xs uppercase tracking-wider text-on-surface-variant">{o.role}</p>
                    <p className="mt-1 text-xs text-on-surface-variant">
                      Last active · {o.is_active ? "currently enabled" : "disabled"} · joined {o.created_at.slice(0, 10)}
                    </p>
                  </div>
                  <span
                    className={`material-symbols-outlined text-2xl ${o.is_active ? "text-primary" : "text-on-surface-variant/40"}`}
                  >
                    {o.is_active ? "verified_user" : "person_off"}
                  </span>
                </div>
              </button>
            );
          })}
        </div>

        <div className="col-span-12 lg:col-span-5">
          <div className="sticky top-6 overflow-hidden rounded-xl border border-outline-variant/10 bg-surface-container-lowest shadow-sm">
            <div className="ink-gradient px-6 py-5">
              <p className="text-xs font-bold uppercase tracking-widest text-on-primary/90">Governance</p>
              <p className="mt-1 font-headline text-xl font-extrabold text-on-primary">
                {selected ? selected.email : "Select a teammate"}
              </p>
              <p className="mt-1 text-sm text-on-primary/90">{selected ? selected.role : "—"}</p>
            </div>
            <div className="space-y-4 p-6">
              <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Access matrix</p>
              {PERMISSIONS.map((label, i) => (
                <div key={label} className="flex items-center justify-between gap-3 border-b border-outline-variant/10 pb-3 last:border-none">
                  <span className="text-sm font-medium text-on-surface">{label}</span>
                  <Toggle checked={matrix[i] ?? false} disabled onChange={() => {}} />
                </div>
              ))}
              <p className="text-xs text-on-surface-variant">Toggles are disabled until ACL service ships.</p>
            </div>
          </div>
        </div>
      </div>

      <section className="space-y-4">
        <h2 className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Role definitions</h2>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {ROLE_COPY.map((r) => (
            <div key={r.role} className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-5 shadow-sm">
              <p className="font-headline text-lg font-bold text-on-surface">{r.role}</p>
              <p className="mt-2 text-sm text-on-surface-variant">{r.blurb}</p>
              <ul className="mt-4 space-y-2 text-sm text-on-surface">
                {r.permissions.map((p) => (
                  <li key={p} className="flex items-start gap-2">
                    <span className="material-symbols-outlined text-lg text-primary">check_circle</span>
                    <span>{p}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
