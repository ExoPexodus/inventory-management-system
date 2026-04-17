"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Avatar,
  Badge,
  EmptyState,
  ErrorState,
  PageHeader,
  PrimaryButton,
  SearchBar,
  SecondaryButton,
  Tabs,
} from "@/components/ui/primitives";

// ─── Types ────────────────────────────────────────────────────────────────────

type TeamUser = {
  id: string;
  email: string;
  name: string;
  phone: string | null;
  role_id: string | null;
  role_name: string | null;
  role_display_name: string | null;
  shop_id: string | null;
  device_id: string | null;
  access: ("cashier_app" | "admin_web" | "admin_mobile")[];
  has_password: boolean;
  has_pin: boolean;
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

// ─── Modal shell ───────────────────────────────────────────────────────────────

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
        <div className="p-6 max-h-[75vh] overflow-y-auto">{children}</div>
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

// ─── Access badges ─────────────────────────────────────────────────────────────

function AccessBadges({ access }: { access: TeamUser["access"] }) {
  const labels: Record<string, { text: string; icon: string; tone: "default" | "good" | "warn" }> = {
    cashier_app: { text: "Cashier", icon: "point_of_sale", tone: "default" },
    admin_web: { text: "Web", icon: "desktop_windows", tone: "good" },
    admin_mobile: { text: "Mobile", icon: "phone_android", tone: "warn" },
  };
  if (access.length === 0) return <Badge tone="danger">No access</Badge>;
  return (
    <div className="flex flex-wrap gap-1">
      {access.map((a) => {
        const label = labels[a];
        return (
          <Badge key={a} tone={label.tone}>
            <span className="material-symbols-outlined text-[11px] mr-0.5">{label.icon}</span>
            {label.text}
          </Badge>
        );
      })}
    </div>
  );
}

// ─── Invite dialog — single flow for any role ─────────────────────────────────

function InviteUserDialog({
  open,
  onClose,
  onCreated,
  roles,
  permissionsByRole,
  shops,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (newUser: TeamUser) => void;
  roles: Role[];
  permissionsByRole: Record<string, string[]>;
  shops: Shop[];
}) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [roleId, setRoleId] = useState("");
  const [shopId, setShopId] = useState("");
  const [password, setPassword] = useState("");
  const [pin, setPin] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [createdUser, setCreatedUser] = useState<TeamUser | null>(null);
  const [qrToken, setQrToken] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setName(""); setEmail(""); setPhone("");
      setRoleId(roles[0]?.id ?? "");
      setShopId("");
      setPassword(""); setPin(""); setErr(null); setBusy(false);
      setCreatedUser(null); setQrToken(null);
    }
  }, [open, roles]);

  const rolePerms = roleId ? (permissionsByRole[roleId] ?? []) : [];
  const needsWeb = rolePerms.includes("admin_web:access") || rolePerms.includes("admin_mobile:access");
  const needsCashier = rolePerms.includes("cashier_app:access");
  const needsPassword = needsWeb; // admin-web/mobile users need password
  const needsPin = needsCashier; // cashier users need PIN (admin_mobile quick-unlock can be set later)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!roleId) { setErr("Select a role"); return; }
    if (needsPassword && !password) { setErr("This role requires a password"); return; }
    if (needsPin && !pin) { setErr("This role requires a PIN"); return; }
    if (pin && !/^\d+$/.test(pin)) { setErr("PIN must be numeric"); return; }

    setBusy(true);
    setErr(null);
    try {
      const body: Record<string, string | null> = {
        email,
        name,
        phone: phone || null,
        role_id: roleId,
        shop_id: shopId || null,
      };
      if (password) body.password = password;
      if (pin) body.pin = pin;

      const r = await fetch("/api/ims/v1/admin/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        const d = (await r.json()) as { detail?: string };
        setErr(d.detail ?? `Error ${r.status}`);
        setBusy(false);
        return;
      }
      const created = (await r.json()) as TeamUser;
      setCreatedUser(created);

      // If user has any device-based access, generate enrollment QR
      if (needsCashier || rolePerms.includes("admin_mobile:access")) {
        const appTarget = needsCashier ? "cashier" : "admin_mobile";
        const enrollR = await fetch(`/api/ims/v1/admin/employees/${created.id}/invite`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ method: "qr", ttl_hours: 168, app_target: appTarget }),
        });
        if (enrollR.ok) {
          const enrollData = await enrollR.json() as { enrollment_token?: string };
          if (enrollData.enrollment_token) setQrToken(enrollData.enrollment_token);
        }
      }

      onCreated(created);
    } finally {
      setBusy(false);
    }
  }

  if (createdUser) {
    return (
      <Modal open={open} onClose={onClose} title={`Invited — ${createdUser.name}`}>
        <div className="space-y-4">
          <div className="rounded-lg border border-primary/20 bg-primary/5 p-4">
            <p className="text-sm font-semibold text-on-surface">User created successfully</p>
            <p className="mt-1 text-xs text-on-surface-variant">
              {createdUser.email} · {createdUser.role_display_name}
            </p>
          </div>

          {qrToken && (
            <div className="rounded-lg border border-outline-variant/15 bg-surface-container-lowest p-4">
              <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Enrollment token</p>
              <p className="mt-2 break-all font-mono text-xs text-on-surface">{qrToken}</p>
              <p className="mt-2 text-xs text-on-surface-variant">
                Share this token with the user — they can scan the QR or paste it into the app to enroll their device.
              </p>
            </div>
          )}

          <div className="flex justify-end">
            <PrimaryButton type="button" onClick={onClose}>Done</PrimaryButton>
          </div>
        </div>
      </Modal>
    );
  }

  return (
    <Modal open={open} onClose={onClose} title="Invite team member">
      <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4">
        <Field label="Full name">
          <input className={inputCls} required value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Priya Sharma" />
        </Field>
        <Field label="Email">
          <input className={inputCls} type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@example.com" />
        </Field>
        <Field label="Phone (optional)">
          <input className={inputCls} value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+91..." />
        </Field>
        <Field label="Role">
          <select className={inputCls} required value={roleId} onChange={(e) => setRoleId(e.target.value)}>
            <option value="">Select a role…</option>
            {roles.map((r) => (
              <option key={r.id} value={r.id}>{r.display_name}</option>
            ))}
          </select>
          {roleId && (
            <p className="mt-1.5 text-xs text-on-surface-variant">
              This role grants access to:{" "}
              {rolePerms.includes("admin_web:access") && <Badge tone="good">Admin Web</Badge>}{" "}
              {rolePerms.includes("admin_mobile:access") && <Badge tone="warn">Admin Mobile</Badge>}{" "}
              {rolePerms.includes("cashier_app:access") && <Badge>Cashier App</Badge>}{" "}
              {!needsWeb && !needsCashier && <span className="text-on-surface-variant">(no app access — role only)</span>}
            </p>
          )}
        </Field>
        {shops.length > 1 && (
          <Field label="Shop (optional)">
            <select className={inputCls} value={shopId} onChange={(e) => setShopId(e.target.value)}>
              <option value="">— tenant-wide —</option>
              {shops.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          </Field>
        )}
        {needsPassword && (
          <Field label="Password (for admin web/mobile login)">
            <input className={inputCls} type="password" minLength={8} required={needsPassword} value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Min 8 characters" autoComplete="new-password" />
          </Field>
        )}
        {needsPin && (
          <Field label="PIN (for cashier device login)">
            <input className={inputCls} type="text" pattern="\d*" minLength={4} maxLength={8} required={needsPin} value={pin} onChange={(e) => setPin(e.target.value)} placeholder="4-8 digits" />
          </Field>
        )}

        {err && <p className="rounded-lg border border-error/20 bg-error-container/20 px-3 py-2 text-xs text-on-error-container">{err}</p>}

        <div className="flex justify-end gap-3 pt-2">
          <SecondaryButton type="button" onClick={onClose}>Cancel</SecondaryButton>
          <PrimaryButton type="submit" disabled={busy}>{busy ? "Inviting…" : "Invite"}</PrimaryButton>
        </div>
      </form>
    </Modal>
  );
}

// ─── Edit user modal ───────────────────────────────────────────────────────────

function EditUserModal({ open, onClose, user, roles, onSaved }: {
  open: boolean;
  onClose: () => void;
  user: TeamUser | null;
  roles: Role[];
  onSaved: () => void;
}) {
  const [roleId, setRoleId] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (open && user) { setRoleId(user.role_id ?? ""); setErr(null); }
  }, [open, user]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!user) return;
    setBusy(true);
    setErr(null);
    try {
      const r = await fetch(`/api/ims/v1/admin/users/${user.id}`, {
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
    if (!user) return;
    if (!confirm(`${user.is_active ? "Deactivate" : "Reactivate"} ${user.name}?`)) return;
    const r = await fetch(`/api/ims/v1/admin/users/${user.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_active: !user.is_active }),
    });
    if (r.ok) { onSaved(); onClose(); }
    else { const d = (await r.json()) as { detail?: string }; setErr(d.detail ?? "Failed"); }
  }

  if (!user) return null;

  return (
    <Modal open={open} onClose={onClose} title={`Edit — ${user.name}`}>
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
            className={`text-sm font-semibold underline underline-offset-2 ${user.is_active ? "text-error" : "text-primary"}`}
          >
            {user.is_active ? "Deactivate user" : "Reactivate user"}
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

// ─── Team Tab (unified list) ───────────────────────────────────────────────────

function TeamTab({ roles, permissionsByRole }: { roles: Role[]; permissionsByRole: Record<string, string[]> }) {
  const [users, setUsers] = useState<TeamUser[]>([]);
  const [shops, setShops] = useState<Shop[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [filterAccess, setFilterAccess] = useState<"all" | "cashier_app" | "admin_web" | "admin_mobile">("all");
  const [showInactive, setShowInactive] = useState(false);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [editUser, setEditUser] = useState<TeamUser | null>(null);

  const refresh = useCallback(async (includeInactive = false) => {
    setLoading(true);
    setError(null);
    try {
      const url = includeInactive ? "/api/ims/v1/admin/users?include_inactive=true" : "/api/ims/v1/admin/users";
      const [uR, sR] = await Promise.all([
        fetch(url),
        fetch("/api/ims/v1/admin/shops"),
      ]);
      if (!uR.ok) throw new Error("Failed to load");
      setUsers((await uR.json()) as TeamUser[]);
      if (sR.ok) setShops((await sR.json()) as Shop[]);
    } catch {
      setError("Failed to load team data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const shopLabel = (id: string | null) => id ? (shops.find((s) => s.id === id)?.name ?? "—") : "Tenant-wide";

  const filtered = useMemo(() => {
    const ql = q.toLowerCase();
    return users.filter((u) => {
      if (ql && !u.name.toLowerCase().includes(ql) && !u.email.toLowerCase().includes(ql) && !(u.role_display_name ?? "").toLowerCase().includes(ql)) return false;
      if (filterAccess !== "all" && !u.access.includes(filterAccess as "cashier_app" | "admin_web" | "admin_mobile")) return false;
      return true;
    });
  }, [users, q, filterAccess]);

  const stats = useMemo(() => ({
    total: users.length,
    active: users.filter((u) => u.is_active).length,
    cashier: users.filter((u) => u.access.includes("cashier_app")).length,
    admin: users.filter((u) => u.access.includes("admin_web") || u.access.includes("admin_mobile")).length,
  }), [users]);

  return (
    <div className="space-y-6">
      {/* Stats */}
      <div className="grid gap-4 sm:grid-cols-4">
        {[
          { label: "Total members", value: stats.total, icon: "group" },
          { label: "Active", value: stats.active, icon: "check_circle" },
          { label: "Cashier access", value: stats.cashier, icon: "point_of_sale" },
          { label: "Admin access", value: stats.admin, icon: "admin_panel_settings" },
        ].map((s) => (
          <div key={s.label} className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-5 shadow-sm">
            <div className="flex items-center gap-2">
              <span className="material-symbols-outlined text-lg text-on-surface-variant">{s.icon}</span>
              <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">{s.label}</p>
            </div>
            <p className="mt-3 font-headline text-3xl font-extrabold text-primary">{s.value}</p>
          </div>
        ))}
      </div>

      {error && <ErrorState detail={error} />}

      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex-1 min-w-[200px]">
          <SearchBar placeholder="Search by name, email, role…" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <select className={inputCls + " w-44"} value={filterAccess} onChange={(e) => setFilterAccess(e.target.value as typeof filterAccess)}>
          <option value="all">All access</option>
          <option value="cashier_app">Cashier App</option>
          <option value="admin_web">Admin Web</option>
          <option value="admin_mobile">Admin Mobile</option>
        </select>
        <button
          type="button"
          onClick={() => { const next = !showInactive; setShowInactive(next); void refresh(next); }}
          className={`rounded-lg border px-3 py-2 text-xs font-semibold transition ${showInactive ? "border-primary/30 bg-primary/10 text-primary" : "border-outline-variant/20 text-on-surface-variant hover:bg-surface-container"}`}
        >
          {showInactive ? "Showing inactive" : "Show inactive"}
        </button>
        <PrimaryButton type="button" onClick={() => setInviteOpen(true)}>
          <span className="material-symbols-outlined text-base">person_add</span>
          Invite
        </PrimaryButton>
      </div>

      {/* Users table */}
      <div className="overflow-hidden rounded-xl border border-outline-variant/10 bg-surface-container-lowest shadow-sm">
        {loading ? (
          <p className="px-6 py-8 text-sm text-on-surface-variant">Loading…</p>
        ) : filtered.length === 0 ? (
          <EmptyState title="No team members found" detail={q || filterAccess !== "all" ? "Try a different filter" : "Invite your first team member"} />
        ) : (
          <table className="w-full">
            <thead>
              <tr className="border-b border-outline-variant/10">
                {["Name", "Email", "Role", "Access", "Shop", "Status", ""].map((h) => (
                  <th key={h} className="px-6 py-3 text-left text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/10">
              {filtered.map((u) => (
                <tr key={u.id} className={`transition hover:bg-surface-container-low/50 ${!u.is_active ? "opacity-50" : ""}`}>
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-3">
                      <Avatar name={u.name} className="h-9 w-9 text-xs" />
                      <div>
                        <p className="font-semibold text-on-surface">{u.name}</p>
                        {u.device_id && <p className="text-[10px] text-primary"><span className="material-symbols-outlined text-[11px] align-middle">smartphone</span> Device linked</p>}
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4 text-sm text-on-surface-variant">{u.email}</td>
                  <td className="px-6 py-4">
                    <Badge tone={u.role_name === "owner" ? "warn" : u.role_name === "manager" ? "good" : "default"}>
                      {u.role_display_name ?? "No role"}
                    </Badge>
                  </td>
                  <td className="px-6 py-4">
                    <AccessBadges access={u.access} />
                  </td>
                  <td className="px-6 py-4 text-xs text-on-surface-variant">{shopLabel(u.shop_id)}</td>
                  <td className="px-6 py-4">
                    <Badge tone={u.is_active ? "good" : "danger"}>{u.is_active ? "Active" : "Inactive"}</Badge>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <button
                      type="button"
                      onClick={() => setEditUser(u)}
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
      </div>

      <InviteUserDialog
        open={inviteOpen}
        onClose={() => setInviteOpen(false)}
        onCreated={() => void refresh(showInactive)}
        roles={roles}
        permissionsByRole={permissionsByRole}
        shops={shops}
      />
      <EditUserModal
        open={!!editUser}
        onClose={() => setEditUser(null)}
        user={editUser}
        roles={roles}
        onSaved={() => void refresh(showInactive)}
      />
    </div>
  );
}

// ─── Roles Tab (unchanged except Access category) ─────────────────────────────

const CATEGORY_ORDER = ["access", "staff", "catalog", "inventory", "procurement", "sales", "analytics", "operations", "settings", "integrations", "operators", "roles", "audit", "reports", "notifications", "enrollment", "shops"];

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
  role: Role | null;
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
      if (next.has(codename)) next.delete(codename); else next.add(codename);
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
      <form onSubmit={(e) => void submit(e)} className="space-y-4">
        {!isEdit && (
          <Field label="Role name (slug)">
            <input className={inputCls} required value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. warehouse_lead" pattern="[a-z0-9_]+" />
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
            const isAccess = category === "access";
            return (
              <div key={category} className={`rounded-lg border ${isAccess ? "border-primary/30 bg-primary/5" : "border-outline-variant/15 bg-surface-container-lowest"}`}>
                <button
                  type="button"
                  onClick={() => selectCategory(category, items, !allChecked)}
                  className="flex w-full items-center gap-3 px-4 py-3 text-left"
                >
                  <span className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border text-[10px] font-bold ${allChecked ? "border-primary bg-primary text-on-primary" : someChecked ? "border-primary/60 bg-primary/20 text-primary" : "border-outline-variant/40 bg-surface"}`}>
                    {allChecked ? "✓" : someChecked ? "−" : ""}
                  </span>
                  <span className="flex-1 text-sm font-semibold capitalize text-on-surface">
                    {isAccess ? "App Access" : category}
                  </span>
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
    if (r.ok) void refresh();
    else { const d = (await r.json()) as { detail?: string }; alert(d.detail ?? "Failed to delete"); }
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
        <div className="col-span-12 space-y-2 lg:col-span-5">
          {loading && <p className="text-sm text-on-surface-variant">Loading…</p>}
          {roles.map((role) => {
            const on = selectedRole?.id === role.id;
            const accessPerms = role.permissions.filter((p) => p.endsWith(":access"));
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
                    {accessPerms.length > 0 && (
                      <div className="mt-1.5 flex flex-wrap gap-1">
                        {accessPerms.includes("cashier_app:access") && <Badge>Cashier</Badge>}
                        {accessPerms.includes("admin_web:access") && <Badge tone="good">Web</Badge>}
                        {accessPerms.includes("admin_mobile:access") && <Badge tone="warn">Mobile</Badge>}
                      </div>
                    )}
                  </div>
                  <span className="shrink-0 rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-bold text-primary">
                    {role.permissions.length} perms
                  </span>
                </div>
              </button>
            );
          })}
        </div>

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
                  const isAccess = category === "access";
                  return (
                    <div key={category} className={isAccess ? "rounded-lg border border-primary/20 bg-primary/5 p-3" : ""}>
                      <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">
                        {isAccess ? "App Access" : category}
                      </p>
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
  { id: "team", label: "Team" },
  { id: "roles", label: "Roles & Permissions" },
];

export default function TeamPage() {
  const [tab, setTab] = useState("team");
  const [roles, setRoles] = useState<Role[]>([]);
  const [permissionsByRole, setPermissionsByRole] = useState<Record<string, string[]>>({});

  const refreshRoles = useCallback(async () => {
    try {
      const r = await fetch("/api/ims/v1/admin/roles");
      if (r.ok) {
        const list = (await r.json()) as Role[];
        setRoles(list);
        const map: Record<string, string[]> = {};
        list.forEach((ro) => { map[ro.id] = ro.permissions; });
        setPermissionsByRole(map);
      }
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { void refreshRoles(); }, [refreshRoles]);

  return (
    <div className="space-y-8">
      <PageHeader
        kicker="People management"
        title="Team"
        subtitle="One place to manage everyone — cashiers, managers, and admins. Access is driven by their role."
      />

      <Tabs tabs={TABS} active={tab} onChange={setTab} />

      {tab === "team" && <TeamTab roles={roles} permissionsByRole={permissionsByRole} />}
      {tab === "roles" && <RolesTab />}
    </div>
  );
}
