"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { InviteStaffDialog } from "@/components/staff/InviteStaffDialog";
import { ReEnrollDialog } from "@/components/staff/ReEnrollDialog";
import {
  Avatar,
  Badge,
  EmptyState,
  ErrorState,
  PageHeader,
  Panel,
  PrimaryButton,
  SearchBar,
  SecondaryButton,
  Tabs,
} from "@/components/ui/primitives";

// ─── Types ────────────────────────────────────────────────────────────────────

type Employee = {
  id: string;
  shop_id: string;
  name: string;
  email: string;
  phone: string | null;
  position: string;
  credential_type: "pin" | "password";
  device_id: string | null;
  is_active: boolean;
  created_at: string;
};

type Operator = {
  id: string;
  email: string;
  display_name: string | null;
  role: string | null;
  role_id: string | null;
  is_active: boolean;
  created_at: string;
};

type Role = {
  id: string;
  tenant_id: string | null;
  name: string;
  display_name: string;
  is_system: boolean;
  permissions: string[];
};

type Permission = {
  id: string;
  codename: string;
  display_name: string;
  category: string;
  description: string | null;
};

type Shop = { id: string; name: string };

// ─── Helpers ──────────────────────────────────────────────────────────────────

function roleTone(role: string | null): "default" | "warn" | "good" | "danger" {
  if (role === "owner") return "warn";
  if (role === "manager") return "good";
  return "default";
}

function roleLabel(role: string | null, displayName?: string | null) {
  return displayName ?? role?.replace(/_/g, " ") ?? "No role";
}

// ─── Shared modal shell ───────────────────────────────────────────────────────

function Modal({ open, onClose, title, children }: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 w-full max-w-lg rounded-2xl border border-outline-variant/15 bg-surface shadow-2xl">
        <div className="flex items-center justify-between border-b border-outline-variant/10 px-6 py-4">
          <h3 className="font-headline text-lg font-bold text-on-surface">{title}</h3>
          <button type="button" onClick={onClose} className="text-on-surface-variant hover:text-on-surface">
            <span className="material-symbols-outlined text-xl">close</span>
          </button>
        </div>
        <div className="p-6">{children}</div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <label className="block text-xs font-bold uppercase tracking-widest text-on-surface-variant">{label}</label>
      {children}
    </div>
  );
}

const inputCls = "w-full rounded-lg border border-outline-variant/30 bg-surface-container-lowest px-3 py-2.5 text-sm text-on-surface outline-none focus:border-primary focus:ring-1 focus:ring-primary";

// ─── Staff Tab ────────────────────────────────────────────────────────────────

function StaffTab() {
  const [rows, setRows] = useState<Employee[]>([]);
  const [shops, setShops] = useState<Shop[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [reEnrollOpen, setReEnrollOpen] = useState(false);
  const [emailConfigured, setEmailConfigured] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showInactive, setShowInactive] = useState(false);
  const [q, setQ] = useState("");

  const refresh = useCallback(async (includeInactive = false) => {
    setLoading(true);
    setError(null);
    try {
      const [empR, shopR, emailR] = await Promise.all([
        fetch(includeInactive ? "/api/ims/v1/admin/employees?include_inactive=true" : "/api/ims/v1/admin/employees"),
        fetch("/api/ims/v1/admin/shops"),
        fetch("/api/ims/v1/admin/tenant-settings/email"),
      ]);
      const empList = (await empR.json()) as Employee[];
      setRows(empList);
      setShops((await shopR.json()) as Shop[]);
      if (emailR.ok) setEmailConfigured(((await emailR.json()) as { is_active: boolean }).is_active);
      setSelectedId((prev) => (prev && empList.some((x) => x.id === prev)) ? prev : (empList[0]?.id ?? null));
    } catch {
      setError("Failed to load staff data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const shopLabel = (id: string) => shops.find((s) => s.id === id)?.name ?? "Unknown";
  const selected = rows.find((o) => o.id === selectedId) ?? null;

  const filtered = useMemo(() => {
    const ql = q.toLowerCase();
    return rows.filter((e) =>
      (!ql || e.name.toLowerCase().includes(ql) || e.email.toLowerCase().includes(ql) || e.position.toLowerCase().includes(ql)) &&
      (showInactive || e.is_active)
    );
  }, [rows, q, showInactive]);

  const stats = useMemo(() => ({
    active: rows.filter((r) => r.is_active).length,
    total: rows.length,
    pending: rows.filter((r) => r.is_active && !r.device_id).length,
    enrolled: rows.filter((r) => !!r.device_id).length,
  }), [rows]);

  async function deactivate() {
    if (!selected || !confirm(`Deactivate ${selected.name}?`)) return;
    await fetch(`/api/ims/v1/admin/employees/${selected.id}`, { method: "DELETE" });
    void refresh(showInactive);
  }

  async function reactivate() {
    if (!selected || !confirm(`Reactivate ${selected.name}?`)) return;
    await fetch(`/api/ims/v1/admin/employees/${selected.id}/reactivate`, { method: "PATCH" });
    void refresh(showInactive);
  }

  return (
    <div className="space-y-6">
      {/* Stats */}
      <div className="grid gap-4 sm:grid-cols-3">
        {[
          { label: "Active staff", value: stats.active },
          { label: "Total records", value: stats.total },
          { label: "Pending enrollment", value: stats.pending, sub: `${stats.enrolled} device-linked` },
        ].map((s) => (
          <div key={s.label} className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
            <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">{s.label}</p>
            <p className="mt-4 font-headline text-3xl font-extrabold text-primary">{s.value}</p>
            {s.sub && <p className="mt-1 text-xs text-on-surface-variant">{s.sub}</p>}
          </div>
        ))}
      </div>

      {error && <ErrorState detail={error} />}

      <div className="grid grid-cols-12 gap-6">
        {/* List */}
        <div className="col-span-12 space-y-3 lg:col-span-7">
          <div className="flex items-center gap-3">
            <div className="flex-1">
              <SearchBar placeholder="Search employees…" value={q} onChange={(e) => setQ(e.target.value)} />
            </div>
            <button
              type="button"
              onClick={() => { const next = !showInactive; setShowInactive(next); void refresh(next); }}
              className={`flex shrink-0 items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-semibold transition ${showInactive ? "border-primary/30 bg-primary/10 text-primary" : "border-outline-variant/20 text-on-surface-variant hover:bg-surface-container"}`}
            >
              <span className="material-symbols-outlined text-sm">{showInactive ? "visibility" : "visibility_off"}</span>
              {showInactive ? "Showing inactive" : "Show inactive"}
            </button>
            <PrimaryButton type="button" onClick={() => setInviteOpen(true)}>
              <span className="material-symbols-outlined text-base">person_add</span>
              Invite
            </PrimaryButton>
          </div>

          {loading && <p className="text-sm text-on-surface-variant">Loading…</p>}

          {!loading && filtered.length === 0 && (
            <EmptyState title="No employees found" detail={q ? "Try a different search term" : "Invite your first staff member"} />
          )}

          {filtered.map((o) => {
            const on = selectedId === o.id;
            return (
              <button
                key={o.id}
                type="button"
                onClick={() => setSelectedId(o.id)}
                className={`w-full rounded-xl border p-4 text-left shadow-sm transition ${!o.is_active ? "border-outline-variant/10 bg-surface-container-lowest opacity-50" : on ? "border-primary/40 bg-surface-container-low" : "border-outline-variant/10 bg-surface-container-lowest hover:border-outline-variant/20"}`}
              >
                <div className="flex items-center gap-3">
                  <Avatar name={o.name} className="h-10 w-10 text-xs" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-semibold text-on-surface">{o.name}</p>
                    <p className="truncate text-xs text-on-surface-variant">{o.email}</p>
                    <p className="mt-0.5 text-xs text-on-surface-variant/70">
                      {o.position.replaceAll("_", " ")} · {shopLabel(o.shop_id)} · {o.credential_type}
                    </p>
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-1.5">
                    <Badge tone={o.is_active ? "good" : "danger"}>{o.is_active ? "Active" : "Inactive"}</Badge>
                    <span
                      className={`material-symbols-outlined text-xl ${o.device_id ? "text-primary" : "text-on-surface-variant/40"}`}
                      title={o.device_id ? "Device linked" : "No device"}
                    >
                      {o.device_id ? "smartphone" : "smartphone"}
                    </span>
                  </div>
                </div>
              </button>
            );
          })}
        </div>

        {/* Detail panel */}
        <div className="col-span-12 lg:col-span-5">
          <div className="sticky top-6 overflow-hidden rounded-xl border border-outline-variant/10 bg-surface-container-lowest shadow-sm">
            <div className="ink-gradient px-6 py-5">
              <p className="text-xs font-bold uppercase tracking-widest text-on-primary/80">Employee detail</p>
              <p className="mt-1 font-headline text-xl font-extrabold text-on-primary">
                {selected ? selected.name : "Select an employee"}
              </p>
              <p className="mt-1 text-sm text-on-primary/80">{selected ? selected.position.replaceAll("_", " ") : "—"}</p>
            </div>
            <div className="space-y-3 p-6">
              {selected ? (
                <>
                  {[
                    ["Email", selected.email],
                    ["Phone", selected.phone ?? "—"],
                    ["Shop", shopLabel(selected.shop_id)],
                    ["Credential", selected.credential_type],
                    ["Device", selected.device_id ? "Linked" : "Not enrolled"],
                    ["Joined", selected.created_at.slice(0, 10)],
                  ].map(([k, v]) => (
                    <p key={k} className="text-sm text-on-surface-variant"><span className="font-semibold text-on-surface">{k}:</span> {v}</p>
                  ))}
                  {!selected.is_active && (
                    <p className="rounded-lg border border-error/20 bg-error-container/20 px-3 py-2 text-xs font-semibold text-on-error-container">
                      This employee is deactivated.
                    </p>
                  )}
                  <div className="flex flex-wrap gap-2 pt-2">
                    {selected.is_active ? (
                      <>
                        <PrimaryButton type="button" onClick={() => setReEnrollOpen(true)}>Re-enroll / reset</PrimaryButton>
                        <SecondaryButton type="button" onClick={() => void deactivate()}>Deactivate</SecondaryButton>
                      </>
                    ) : (
                      <PrimaryButton type="button" onClick={() => void reactivate()}>Reactivate</PrimaryButton>
                    )}
                  </div>
                </>
              ) : (
                <p className="text-sm text-on-surface-variant">Select an employee to manage enrollment and credentials.</p>
              )}
            </div>
          </div>
        </div>
      </div>

      <InviteStaffDialog open={inviteOpen} shops={shops} emailConfigured={emailConfigured} onClose={() => setInviteOpen(false)} onCreated={() => void refresh(showInactive)} />
      <ReEnrollDialog
        open={reEnrollOpen}
        employee={selected ? { id: selected.id, name: selected.name, email: selected.email, credential_type: selected.credential_type } : null}
        emailConfigured={emailConfigured}
        onClose={() => setReEnrollOpen(false)}
        onDone={() => void refresh(showInactive)}
      />
    </div>
  );
}

// ─── Operators Tab ────────────────────────────────────────────────────────────

function CreateOperatorModal({ open, onClose, roles, onCreated }: {
  open: boolean;
  onClose: () => void;
  roles: Role[];
  onCreated: () => void;
}) {
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [roleId, setRoleId] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (open) { setEmail(""); setDisplayName(""); setPassword(""); setRoleId(roles[0]?.id ?? ""); setErr(null); }
  }, [open, roles]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!roleId) { setErr("Select a role"); return; }
    setBusy(true);
    setErr(null);
    try {
      const r = await fetch("/api/ims/v1/admin/operators", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, display_name: displayName || null, role_id: roleId }),
      });
      if (!r.ok) {
        const d = (await r.json()) as { detail?: string };
        setErr(d.detail ?? `Error ${r.status}`);
        return;
      }
      onCreated();
      onClose();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Add operator">
      <form onSubmit={(e) => void submit(e)} className="space-y-4">
        <Field label="Email">
          <input className={inputCls} type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@example.com" autoComplete="off" />
        </Field>
        <Field label="Display name">
          <input className={inputCls} type="text" value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="Optional" />
        </Field>
        <Field label="Password">
          <input className={inputCls} type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Min 8 characters" autoComplete="new-password" />
        </Field>
        <Field label="Role">
          <select className={inputCls} required value={roleId} onChange={(e) => setRoleId(e.target.value)}>
            <option value="">Select a role…</option>
            {roles.map((r) => (
              <option key={r.id} value={r.id}>{r.display_name}</option>
            ))}
          </select>
        </Field>
        {err && <p className="rounded-lg border border-error/20 bg-error-container/20 px-3 py-2 text-xs text-on-error-container">{err}</p>}
        <div className="flex justify-end gap-3 pt-2">
          <SecondaryButton type="button" onClick={onClose}>Cancel</SecondaryButton>
          <PrimaryButton type="submit" disabled={busy}>{busy ? "Creating…" : "Create operator"}</PrimaryButton>
        </div>
      </form>
    </Modal>
  );
}

function EditOperatorModal({ open, onClose, operator, roles, onSaved }: {
  open: boolean;
  onClose: () => void;
  operator: Operator | null;
  roles: Role[];
  onSaved: () => void;
}) {
  const [roleId, setRoleId] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (open && operator) { setRoleId(operator.role_id ?? ""); setErr(null); }
  }, [open, operator]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!operator) return;
    setBusy(true);
    setErr(null);
    try {
      const r = await fetch(`/api/ims/v1/admin/operators/${operator.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role_id: roleId || null }),
      });
      if (!r.ok) {
        const d = (await r.json()) as { detail?: string };
        setErr(d.detail ?? `Error ${r.status}`);
        return;
      }
      onSaved();
      onClose();
    } finally {
      setBusy(false);
    }
  }

  async function toggleActive() {
    if (!operator) return;
    if (!confirm(`${operator.is_active ? "Deactivate" : "Reactivate"} ${operator.display_name ?? operator.email}?`)) return;
    const r = await fetch(`/api/ims/v1/admin/operators/${operator.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_active: !operator.is_active }),
    });
    if (r.ok) { onSaved(); onClose(); }
    else { const d = (await r.json()) as { detail?: string }; setErr(d.detail ?? "Failed"); }
  }

  if (!operator) return null;

  return (
    <Modal open={open} onClose={onClose} title={`Edit — ${operator.display_name ?? operator.email}`}>
      <form onSubmit={(e) => void save(e)} className="space-y-4">
        <Field label="Role">
          <select className={inputCls} value={roleId} onChange={(e) => setRoleId(e.target.value)}>
            {roles.map((r) => (
              <option key={r.id} value={r.id}>{r.display_name}</option>
            ))}
          </select>
        </Field>
        {err && <p className="rounded-lg border border-error/20 bg-error-container/20 px-3 py-2 text-xs text-on-error-container">{err}</p>}
        <div className="flex items-center justify-between pt-2">
          <button
            type="button"
            onClick={() => void toggleActive()}
            className={`text-sm font-semibold underline underline-offset-2 ${operator.is_active ? "text-error" : "text-primary"}`}
          >
            {operator.is_active ? "Deactivate operator" : "Reactivate operator"}
          </button>
          <div className="flex gap-3">
            <SecondaryButton type="button" onClick={onClose}>Cancel</SecondaryButton>
            <PrimaryButton type="submit" disabled={busy}>{busy ? "Saving…" : "Save changes"}</PrimaryButton>
          </div>
        </div>
      </form>
    </Modal>
  );
}

function OperatorsTab({ roles }: { roles: Role[] }) {
  const [rows, setRows] = useState<Operator[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<Operator | null>(null);
  const [q, setQ] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch("/api/ims/v1/admin/operators");
      if (!r.ok) throw new Error(`${r.status}`);
      setRows((await r.json()) as Operator[]);
    } catch {
      setError("Failed to load operators");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const filtered = useMemo(() => {
    const ql = q.toLowerCase();
    return rows.filter((o) => !ql || o.email.toLowerCase().includes(ql) || (o.display_name ?? "").toLowerCase().includes(ql) || (o.role ?? "").toLowerCase().includes(ql));
  }, [rows, q]);

  const roleDisplayName = (roleId: string | null) => {
    if (!roleId) return null;
    return roles.find((r) => r.id === roleId)?.display_name ?? null;
  };

  const stats = useMemo(() => ({
    total: rows.length,
    active: rows.filter((r) => r.is_active).length,
    byRole: roles.map((r) => ({ label: r.display_name, count: rows.filter((o) => o.role_id === r.id).length })).filter((x) => x.count > 0),
  }), [rows, roles]);

  return (
    <div className="space-y-6">
      {/* Stats */}
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Total operators</p>
          <p className="mt-4 font-headline text-3xl font-extrabold text-primary">{stats.total}</p>
        </div>
        <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Active</p>
          <p className="mt-4 font-headline text-3xl font-extrabold text-primary">{stats.active}</p>
        </div>
        <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">By role</p>
          <div className="mt-3 space-y-1">
            {stats.byRole.length === 0 ? <p className="text-sm text-on-surface-variant">—</p> : stats.byRole.map((b) => (
              <p key={b.label} className="text-xs text-on-surface-variant"><span className="font-semibold text-on-surface">{b.count}</span> {b.label}</p>
            ))}
          </div>
        </div>
      </div>

      {error && <ErrorState detail={error} />}

      <Panel
        title="Admin operators"
        subtitle="People who can access the admin dashboard"
        right={
          <div className="flex items-center gap-3">
            <SearchBar placeholder="Search operators…" value={q} onChange={(e) => setQ(e.target.value)} className="w-56" />
            <PrimaryButton type="button" onClick={() => setCreateOpen(true)}>
              <span className="material-symbols-outlined text-base">person_add</span>
              Add operator
            </PrimaryButton>
          </div>
        }
        noPad
      >
        {loading ? (
          <p className="px-6 py-8 text-sm text-on-surface-variant">Loading…</p>
        ) : filtered.length === 0 ? (
          <EmptyState title="No operators found" detail={q ? "Try a different search" : "Add your first operator"} />
        ) : (
          <table className="w-full">
            <thead>
              <tr className="border-b border-outline-variant/10">
                {["Operator", "Role", "Status", "Joined", ""].map((h) => (
                  <th key={h} className="px-6 py-3 text-left text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/10">
              {filtered.map((op) => (
                <tr key={op.id} className="transition hover:bg-surface-container-low/50">
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-3">
                      <Avatar name={op.display_name ?? op.email} className="h-9 w-9 text-xs" />
                      <div>
                        <p className="font-semibold text-on-surface">{op.display_name ?? op.email}</p>
                        {op.display_name && <p className="text-xs text-on-surface-variant">{op.email}</p>}
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <Badge tone={roleTone(op.role)}>{roleLabel(op.role, roleDisplayName(op.role_id))}</Badge>
                  </td>
                  <td className="px-6 py-4">
                    <Badge tone={op.is_active ? "good" : "danger"}>{op.is_active ? "Active" : "Inactive"}</Badge>
                  </td>
                  <td className="px-6 py-4 text-xs text-on-surface-variant">{op.created_at.slice(0, 10)}</td>
                  <td className="px-6 py-4 text-right">
                    <button
                      type="button"
                      onClick={() => setEditTarget(op)}
                      className="rounded-lg border border-outline-variant/30 px-3 py-1.5 text-xs font-semibold text-on-surface transition hover:bg-surface-container"
                    >
                      Edit
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      <CreateOperatorModal open={createOpen} onClose={() => setCreateOpen(false)} roles={roles} onCreated={() => void refresh()} />
      <EditOperatorModal open={!!editTarget} onClose={() => setEditTarget(null)} operator={editTarget} roles={roles} onSaved={() => void refresh()} />
    </div>
  );
}

// ─── Roles Tab ────────────────────────────────────────────────────────────────

const CATEGORY_ORDER = ["staff", "catalog", "inventory", "procurement", "sales", "analytics", "operations", "settings", "integrations", "operators", "roles", "audit", "reports", "notifications", "enrollment", "shops"];

function groupPermissions(perms: Permission[]) {
  const map = new Map<string, Permission[]>();
  for (const p of perms) {
    if (!map.has(p.category)) map.set(p.category, []);
    map.get(p.category)!.push(p);
  }
  return CATEGORY_ORDER.flatMap((cat) => {
    const items = map.get(cat);
    return items ? [{ category: cat, items }] : [];
  });
}

function RoleModal({ open, onClose, role, allPermissions, onSaved }: {
  open: boolean;
  onClose: () => void;
  role: Role | null; // null = create mode
  allPermissions: Permission[];
  onSaved: () => void;
}) {
  const isEdit = !!role;
  const [name, setName] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    if (role) {
      setName(role.name);
      setDisplayName(role.display_name);
      setSelected(new Set(role.permissions));
    } else {
      setName(""); setDisplayName(""); setSelected(new Set());
    }
    setErr(null);
  }, [open, role]);

  function toggle(codename: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(codename) ? next.delete(codename) : next.add(codename);
      return next;
    });
  }

  function selectCategory(cat: string, perms: Permission[], checked: boolean) {
    setSelected((prev) => {
      const next = new Set(prev);
      perms.forEach((p) => checked ? next.add(p.codename) : next.delete(p.codename));
      return next;
    });
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const body = isEdit
        ? { display_name: displayName, permissions: Array.from(selected) }
        : { name: name.trim().toLowerCase().replace(/\s+/g, "_"), display_name: displayName, permissions: Array.from(selected) };
      const r = await fetch(
        isEdit ? `/api/ims/v1/admin/roles/${role!.id}` : "/api/ims/v1/admin/roles",
        { method: isEdit ? "PATCH" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
      );
      if (!r.ok) {
        const d = (await r.json()) as { detail?: string };
        setErr(d.detail ?? `Error ${r.status}`);
        return;
      }
      onSaved();
      onClose();
    } finally {
      setBusy(false);
    }
  }

  const grouped = useMemo(() => groupPermissions(allPermissions), [allPermissions]);

  return (
    <Modal open={open} onClose={onClose} title={isEdit ? `Edit role — ${role?.display_name}` : "Create custom role"}>
      <form onSubmit={(e) => void submit(e)} className="space-y-4 max-h-[70vh] overflow-y-auto pr-1">
        {!isEdit && (
          <Field label="Role name (slug)">
            <input className={inputCls} required value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. warehouse_lead" pattern="[a-z0-9_]+" title="Lowercase letters, numbers, underscores" />
          </Field>
        )}
        <Field label="Display name">
          <input className={inputCls} required value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="e.g. Warehouse Lead" />
        </Field>

        <div className="space-y-3">
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Permissions ({selected.size} selected)</p>
          {grouped.map(({ category, items }) => {
            const allChecked = items.every((p) => selected.has(p.codename));
            const someChecked = items.some((p) => selected.has(p.codename));
            return (
              <div key={category} className="rounded-lg border border-outline-variant/15 bg-surface-container-lowest">
                <button
                  type="button"
                  onClick={() => selectCategory(category, items, !allChecked)}
                  className="flex w-full items-center gap-3 px-4 py-3 text-left"
                >
                  <span className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border text-[10px] font-bold ${allChecked ? "border-primary bg-primary text-on-primary" : someChecked ? "border-primary/60 bg-primary/20 text-primary" : "border-outline-variant/40 bg-surface"}`}>
                    {allChecked ? "✓" : someChecked ? "−" : ""}
                  </span>
                  <span className="flex-1 text-sm font-semibold capitalize text-on-surface">{category}</span>
                  <span className="text-xs text-on-surface-variant">{items.filter((p) => selected.has(p.codename)).length}/{items.length}</span>
                </button>
                <div className="border-t border-outline-variant/10 px-4 pb-3 pt-2 space-y-2">
                  {items.map((p) => (
                    <label key={p.codename} className="flex cursor-pointer items-start gap-3">
                      <input
                        type="checkbox"
                        checked={selected.has(p.codename)}
                        onChange={() => toggle(p.codename)}
                        className="mt-0.5 h-4 w-4 accent-primary"
                      />
                      <div>
                        <p className="text-xs font-semibold text-on-surface">{p.display_name}</p>
                        <p className="text-[10px] font-mono text-on-surface-variant/70">{p.codename}</p>
                      </div>
                    </label>
                  ))}
                </div>
              </div>
            );
          })}
        </div>

        {err && <p className="rounded-lg border border-error/20 bg-error-container/20 px-3 py-2 text-xs text-on-error-container">{err}</p>}
        <div className="flex justify-end gap-3 pt-2 sticky bottom-0 bg-surface py-3 -mx-1 px-1">
          <SecondaryButton type="button" onClick={onClose}>Cancel</SecondaryButton>
          <PrimaryButton type="submit" disabled={busy}>{busy ? "Saving…" : isEdit ? "Save changes" : "Create role"}</PrimaryButton>
        </div>
      </form>
    </Modal>
  );
}

function RolesTab() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [allPermissions, setAllPermissions] = useState<Permission[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modalTarget, setModalTarget] = useState<Role | null | "create">(null);
  const [selectedRole, setSelectedRole] = useState<Role | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [rolesR, permsR] = await Promise.all([
        fetch("/api/ims/v1/admin/roles"),
        fetch("/api/ims/v1/admin/roles/permissions"),
      ]);
      const roleList = (await rolesR.json()) as Role[];
      setRoles(roleList);
      setAllPermissions((await permsR.json()) as Permission[]);
      setSelectedRole((prev) => roleList.find((r) => r.id === prev?.id) ?? roleList[0] ?? null);
    } catch {
      setError("Failed to load roles");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  async function deleteRole(role: Role) {
    if (!confirm(`Delete role "${role.display_name}"? This cannot be undone.`)) return;
    const r = await fetch(`/api/ims/v1/admin/roles/${role.id}`, { method: "DELETE" });
    if (r.ok) {
      void refresh();
    } else {
      const d = (await r.json()) as { detail?: string };
      alert(d.detail ?? "Failed to delete role");
    }
  }

  const grouped = useMemo(() => groupPermissions(allPermissions), [allPermissions]);

  const editTarget = modalTarget !== null && modalTarget !== "create" ? modalTarget as Role : null;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-sm text-on-surface-variant">
          {roles.filter((r) => r.is_system).length} system roles · {roles.filter((r) => !r.is_system).length} custom roles
        </p>
        <PrimaryButton type="button" onClick={() => setModalTarget("create")}>
          <span className="material-symbols-outlined text-base">add</span>
          Create custom role
        </PrimaryButton>
      </div>

      {error && <ErrorState detail={error} />}

      <div className="grid grid-cols-12 gap-6">
        {/* Role list */}
        <div className="col-span-12 space-y-2 lg:col-span-5">
          {loading && <p className="text-sm text-on-surface-variant">Loading…</p>}
          {roles.map((role) => {
            const on = selectedRole?.id === role.id;
            return (
              <button
                key={role.id}
                type="button"
                onClick={() => setSelectedRole(role)}
                className={`w-full rounded-xl border p-4 text-left shadow-sm transition ${on ? "border-primary/40 bg-surface-container-low" : "border-outline-variant/10 bg-surface-container-lowest hover:border-outline-variant/20"}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="font-semibold text-on-surface">{role.display_name}</p>
                      {role.is_system && <Badge>System</Badge>}
                    </div>
                    <p className="mt-0.5 font-mono text-xs text-on-surface-variant">{role.name}</p>
                  </div>
                  <span className="shrink-0 rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-bold text-primary">
                    {role.permissions.length} perms
                  </span>
                </div>
              </button>
            );
          })}
        </div>

        {/* Role detail */}
        <div className="col-span-12 lg:col-span-7">
          {selectedRole ? (
            <div className="sticky top-6 overflow-hidden rounded-xl border border-outline-variant/10 bg-surface-container-lowest shadow-sm">
              <div className="ink-gradient flex items-start justify-between px-6 py-5">
                <div>
                  <p className="text-xs font-bold uppercase tracking-widest text-on-primary/80">Role detail</p>
                  <p className="mt-1 font-headline text-xl font-extrabold text-on-primary">{selectedRole.display_name}</p>
                  <p className="mt-1 font-mono text-sm text-on-primary/70">{selectedRole.name}</p>
                </div>
                {!selectedRole.is_system && (
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => setModalTarget(selectedRole)}
                      className="rounded-lg border border-on-primary/30 px-3 py-1.5 text-xs font-semibold text-on-primary transition hover:bg-on-primary/10"
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      onClick={() => void deleteRole(selectedRole)}
                      className="rounded-lg border border-error/40 bg-error-container/30 px-3 py-1.5 text-xs font-semibold text-on-error-container transition hover:bg-error-container/60"
                    >
                      Delete
                    </button>
                  </div>
                )}
              </div>
              <div className="max-h-[60vh] overflow-y-auto p-6 space-y-4">
                {grouped.map(({ category, items }) => {
                  const granted = items.filter((p) => selectedRole.permissions.includes(p.codename));
                  if (granted.length === 0) return null;
                  return (
                    <div key={category}>
                      <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">{category}</p>
                      <div className="space-y-1">
                        {granted.map((p) => (
                          <div key={p.codename} className="flex items-center gap-2">
                            <span className="material-symbols-outlined text-sm text-primary">check_circle</span>
                            <div>
                              <span className="text-xs font-semibold text-on-surface">{p.display_name}</span>
                              <span className="ml-2 font-mono text-[10px] text-on-surface-variant/60">{p.codename}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })}
                {selectedRole.permissions.length === 0 && (
                  <p className="text-sm text-on-surface-variant">No permissions assigned to this role.</p>
                )}
              </div>
            </div>
          ) : (
            <EmptyState title="Select a role" detail="Click a role to see its permissions" />
          )}
        </div>
      </div>

      <RoleModal
        open={modalTarget !== null}
        onClose={() => setModalTarget(null)}
        role={editTarget}
        allPermissions={allPermissions}
        onSaved={() => void refresh()}
      />
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

const TABS = [
  { id: "staff", label: "Staff" },
  { id: "operators", label: "Operators" },
  { id: "roles", label: "Roles & Permissions" },
];

export default function TeamPage() {
  const [tab, setTab] = useState("staff");
  // Roles are loaded once and shared between Operators tab (for the role picker)
  const [roles, setRoles] = useState<Role[]>([]);

  const refreshRoles = useCallback(async () => {
    try {
      const r = await fetch("/api/ims/v1/admin/roles");
      if (r.ok) setRoles((await r.json()) as Role[]);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { void refreshRoles(); }, [refreshRoles]);

  return (
    <div className="space-y-8">
      <PageHeader
        kicker="People management"
        title="Team"
        subtitle="Manage employees, admin operators, and access roles from one place."
      />

      <Tabs tabs={TABS} active={tab} onChange={setTab} />

      {tab === "staff" && <StaffTab />}
      {tab === "operators" && <OperatorsTab roles={roles} />}
      {tab === "roles" && <RolesTab />}
    </div>
  );
}
