"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { InviteStaffDialog } from "@/components/staff/InviteStaffDialog";
import { ReEnrollDialog } from "@/components/staff/ReEnrollDialog";
import { Avatar, PageHeader, PrimaryButton, SecondaryButton } from "@/components/ui/primitives";

type Employee = {
  id: string;
  tenant_id: string;
  shop_id: string;
  name: string;
  email: string;
  phone: string | null;
  position: string;
  credential_type: "pin" | "password";
  device_id: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

type Shop = { id: string; tenant_id: string; name: string };

export default function StaffPage() {
  const [rows, setRows] = useState<Employee[]>([]);
  const [shops, setShops] = useState<Shop[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [reEnrollOpen, setReEnrollOpen] = useState(false);
  const [emailConfigured, setEmailConfigured] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refreshEmployees = useCallback(async () => {
    const r = await fetch("/api/ims/v1/admin/employees");
    if (!r.ok) throw new Error(await r.text());
    const list = (await r.json()) as Employee[];
    setRows(list);
    setSelectedId((prev) => {
      if (prev && list.some((x) => x.id === prev)) return prev;
      return list[0]?.id ?? null;
    });
  }, []);

  const refreshShops = useCallback(async () => {
    const r = await fetch("/api/ims/v1/admin/shops");
    if (!r.ok) throw new Error(await r.text());
    setShops((await r.json()) as Shop[]);
  }, []);

  const refreshEmailConfig = useCallback(async () => {
    const r = await fetch("/api/ims/v1/admin/tenant-settings/email");
    if (r.ok) {
      const data = (await r.json()) as { is_active: boolean };
      setEmailConfigured(data.is_active);
      return;
    }
    setEmailConfigured(false);
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      await Promise.all([refreshEmployees(), refreshShops(), refreshEmailConfig()]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load staff");
    } finally {
      setLoading(false);
    }
  }, [refreshEmailConfig, refreshEmployees, refreshShops]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const selected = rows.find((o) => o.id === selectedId) ?? null;
  const activeNow = useMemo(() => rows.filter((o) => o.is_active).length, [rows]);
  const enrolledCount = useMemo(() => rows.filter((o) => !!o.device_id).length, [rows]);
  const pendingEnrollments = rows.length - enrolledCount;
  const shopLabel = (shopId: string) => shops.find((s) => s.id === shopId)?.name ?? "Unknown";

  async function deactivateSelected() {
    if (!selected) return;
    const ok = window.confirm(`Deactivate ${selected.name}?`);
    if (!ok) return;
    const r = await fetch(`/api/ims/v1/admin/employees/${selected.id}`, { method: "DELETE" });
    if (!r.ok) {
      window.alert("Failed to deactivate employee");
      return;
    }
    await refresh();
  }

  return (
    <div className="space-y-10">
      <PageHeader
        kicker="Staff onboarding"
        title="Employees & devices"
        subtitle="Create employee records, assign shop, and invite by email or QR for cashier app enrollment."
        action={
          <PrimaryButton type="button" onClick={() => setInviteOpen(true)}>
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
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Pending enrollments</p>
          <p className="mt-4 font-headline text-3xl font-extrabold text-primary">{pendingEnrollments}</p>
          <p className="mt-1 text-xs text-on-surface-variant">{enrolledCount} already linked to devices</p>
        </div>
      </div>

      {error ? (
        <p className="rounded-xl border border-error/20 bg-error-container/20 px-4 py-3 text-sm text-on-error-container">{error}</p>
      ) : null}

      <div className="grid grid-cols-12 gap-6">
        <div className="col-span-12 space-y-3 lg:col-span-7">
          <h2 className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Employees</h2>
          {loading ? <p className="text-sm text-on-surface-variant">Loading employees...</p> : null}
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
                  <Avatar name={o.name} className="h-12 w-12 text-sm" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-headline text-base font-bold text-on-surface">{o.name}</p>
                    <p className="text-sm text-on-surface-variant">{o.email}</p>
                    <p className="mt-1 text-xs text-on-surface-variant">
                      {o.position.replaceAll("_", " ")} · {shopLabel(o.shop_id)} · {o.is_active ? "active" : "disabled"} · joined{" "}
                      {o.created_at.slice(0, 10)}
                    </p>
                  </div>
                  <button
                    type="button"
                    aria-label={`Re-enroll ${o.name}`}
                    onClick={(e) => { e.stopPropagation(); setSelectedId(o.id); setReEnrollOpen(true); }}
                    className="rounded p-1 transition hover:bg-primary/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
                  >
                    <span className={`material-symbols-outlined text-2xl ${o.device_id ? "text-primary" : "text-secondary"}`}>
                      {o.device_id ? "devices" : "qr_code_2"}
                    </span>
                  </button>
                </div>
              </button>
            );
          })}
        </div>

        <div className="col-span-12 lg:col-span-5">
          <div className="sticky top-6 overflow-hidden rounded-xl border border-outline-variant/10 bg-surface-container-lowest shadow-sm">
            <div className="ink-gradient px-6 py-5">
              <p className="text-xs font-bold uppercase tracking-widest text-on-primary/90">Employee detail</p>
              <p className="mt-1 font-headline text-xl font-extrabold text-on-primary">
                {selected ? selected.name : "Select an employee"}
              </p>
              <p className="mt-1 text-sm text-on-primary/90">{selected ? selected.position.replaceAll("_", " ") : "—"}</p>
            </div>
            <div className="space-y-3 p-6">
              {selected ? (
                <>
                  <p className="text-sm text-on-surface-variant">Email: {selected.email}</p>
                  <p className="text-sm text-on-surface-variant">Phone: {selected.phone || "—"}</p>
                  <p className="text-sm text-on-surface-variant">Shop: {shopLabel(selected.shop_id)}</p>
                  <p className="text-sm text-on-surface-variant">Credential: {selected.credential_type}</p>
                  <p className="text-sm text-on-surface-variant">Device status: {selected.device_id ? "Linked" : "Not enrolled"}</p>
                  <div className="flex flex-wrap gap-2 pt-2">
                    <PrimaryButton type="button" onClick={() => setReEnrollOpen(true)}>
                      Re-enroll / reset
                    </PrimaryButton>
                    <SecondaryButton type="button" onClick={() => void deactivateSelected()}>
                      Deactivate
                    </SecondaryButton>
                  </div>
                </>
              ) : (
                <p className="text-sm text-on-surface-variant">Select an employee to manage enrollment and credentials.</p>
              )}
            </div>
          </div>
        </div>
      </div>

      <InviteStaffDialog
        open={inviteOpen}
        shops={shops}
        emailConfigured={emailConfigured}
        onClose={() => setInviteOpen(false)}
        onCreated={refresh}
      />
      <ReEnrollDialog
        open={reEnrollOpen}
        employee={selected ? { id: selected.id, name: selected.name, email: selected.email, credential_type: selected.credential_type } : null}
        emailConfigured={emailConfigured}
        onClose={() => setReEnrollOpen(false)}
        onDone={refresh}
      />
    </div>
  );
}
