"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Badge,
  Breadcrumbs,
  EmptyState,
  LoadingRow,
  PageHeader,
  Pagination,
  Panel,
  PrimaryButton,
  SecondaryButton,
  SelectInput,
  TextInput,
} from "@/components/ui/primitives";
import { Typeahead } from "@/components/ui/Typeahead";
import { formatMoney } from "@/lib/format";
import { useCurrency } from "@/lib/currency-context";
import { useHasPermission } from "@/lib/auth/user-context";

type Shop = { id: string; name: string };

type LineOut = {
  id: string;
  product_id: string;
  product_sku: string | null;
  product_name: string | null;
  quantity_requested: number;
  quantity_shipped: number;
  quantity_received: number;
  unit_cost_at_transfer_cents: number | null;
  line_notes: string | null;
};

type TransferOut = {
  id: string;
  tenant_id: string;
  from_shop_id: string;
  from_shop_name: string | null;
  to_shop_id: string;
  to_shop_name: string | null;
  status: string;
  created_by_user_id: string | null;
  approved_by_user_id: string | null;
  approved_at: string | null;
  rejected_at: string | null;
  rejection_reason: string | null;
  shipped_at: string | null;
  received_at: string | null;
  cancelled_at: string | null;
  notes: string | null;
  lines: LineOut[];
  created_at: string;
};

type TransferListResponse = {
  items: TransferOut[];
  total: number;
  page: number;
  per_page: number;
};

const ALL_STATUSES = [
  "draft",
  "pending_approval",
  "approved",
  "in_transit",
  "completed",
  "rejected",
  "cancelled",
];

function statusTone(s: string): "default" | "good" | "warn" | "danger" {
  switch (s) {
    case "completed": return "good";
    case "approved": return "good";
    case "in_transit": return "warn";
    case "pending_approval": return "warn";
    case "rejected": return "danger";
    case "cancelled": return "danger";
    default: return "default";
  }
}

function statusLabel(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function totalCost(transfer: TransferOut): number {
  return transfer.lines.reduce((sum, l) => {
    if (l.unit_cost_at_transfer_cents != null) {
      return sum + l.unit_cost_at_transfer_cents * l.quantity_requested;
    }
    return sum;
  }, 0);
}

// ── Create Transfer Modal ──────────────────────────────────────────────────

type ProductOption = { id: string; sku: string; name: string };
type LineInput = { product_id: string; quantity_requested: number; line_notes: string };

// ── Shared transfer form lines editor ─────────────────────────────────────

function TransferLinesEditor({
  lines,
  products,
  onLinesChange,
}: {
  lines: LineInput[];
  products: ProductOption[];
  onLinesChange: (lines: LineInput[]) => void;
}) {
  const productOptions = products.map((p) => ({ value: p.id, label: `${p.sku} — ${p.name}` }));

  const addLine = () =>
    onLinesChange([...lines, { product_id: "", quantity_requested: 1, line_notes: "" }]);

  const updateLine = (idx: number, field: keyof LineInput, value: string | number) =>
    onLinesChange(lines.map((l, i) => (i === idx ? { ...l, [field]: value } : l)));

  const removeLine = (idx: number) => onLinesChange(lines.filter((_, i) => i !== idx));

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-on-surface">Lines</p>
        <button onClick={addLine} type="button" className="text-xs font-semibold text-primary hover:underline">
          + Add line
        </button>
      </div>
      {lines.map((line, idx) => (
        <div key={idx} className="grid grid-cols-12 gap-2 rounded-lg border border-outline-variant/20 bg-surface-container-low p-3">
          <div className="col-span-6">
            <label className="mb-0.5 block text-xs text-on-surface-variant">Product</label>
            <Typeahead
              value={line.product_id}
              onChange={(v) => updateLine(idx, "product_id", v)}
              options={productOptions}
              placeholder="Search products…"
            />
          </div>
          <div className="col-span-2">
            <label className="mb-0.5 block text-xs text-on-surface-variant">Qty</label>
            <TextInput
              type="number"
              min="1"
              value={String(line.quantity_requested)}
              onChange={(e) => updateLine(idx, "quantity_requested", parseInt(e.target.value, 10) || 1)}
            />
          </div>
          <div className="col-span-3">
            <label className="mb-0.5 block text-xs text-on-surface-variant">Notes</label>
            <TextInput
              value={line.line_notes}
              onChange={(e) => updateLine(idx, "line_notes", e.target.value)}
              placeholder=""
            />
          </div>
          <div className="col-span-1 flex items-end pb-1">
            {lines.length > 1 && (
              <button
                type="button"
                onClick={() => removeLine(idx)}
                className="text-error hover:text-error/70"
                title="Remove line"
              >
                <span className="material-symbols-outlined text-lg">delete</span>
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Create Transfer Modal ──────────────────────────────────────────────────

function CreateTransferModal({
  shops,
  products,
  onClose,
  onCreated,
}: {
  shops: Shop[];
  products: ProductOption[];
  onClose: () => void;
  onCreated: (t: TransferOut) => void;
}) {
  const [fromShop, setFromShop] = useState(shops[0]?.id ?? "");
  const [toShop, setToShop] = useState("");
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState<LineInput[]>([
    { product_id: "", quantity_requested: 1, line_notes: "" },
  ]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    setError(null);
    setSaving(true);
    try {
      const body = {
        from_shop_id: fromShop,
        to_shop_id: toShop,
        notes: notes || null,
        lines: lines.map((l) => ({
          product_id: l.product_id,
          quantity_requested: Number(l.quantity_requested),
          line_notes: l.line_notes || null,
        })),
      };
      const res = await fetch("/api/ims/v1/admin/transfer-orders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const d = (await res.json()) as { detail?: string };
        throw new Error(d.detail ?? res.statusText);
      }
      const created = (await res.json()) as TransferOut;
      onCreated(created);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create transfer");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-2xl bg-surface p-6 shadow-xl">
        <h2 className="font-headline text-xl font-bold text-on-surface">New Transfer Order</h2>
        <p className="mt-1 text-sm text-on-surface-variant">Create a draft transfer between two shops.</p>

        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">From shop</label>
            <SelectInput
              value={fromShop}
              onChange={(v) => setFromShop(v)}
              options={shops.map((s) => ({ value: s.id, label: s.name }))}
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">To shop</label>
            <SelectInput
              value={toShop}
              onChange={(v) => setToShop(v)}
              options={[{ value: "", label: "Select…" }, ...shops.filter((s) => s.id !== fromShop).map((s) => ({ value: s.id, label: s.name }))]}
            />
          </div>
        </div>

        <div className="mt-4">
          <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">Notes</label>
          <TextInput value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Optional notes" />
        </div>

        <div className="mt-5">
          <TransferLinesEditor lines={lines} products={products} onLinesChange={setLines} />
        </div>

        {error && (
          <p className="mt-3 rounded-lg border border-error/20 bg-error-container/20 px-3 py-2 text-sm text-on-error-container">
            {error}
          </p>
        )}

        <div className="mt-6 flex justify-end gap-3">
          <SecondaryButton type="button" onClick={onClose} disabled={saving}>
            Cancel
          </SecondaryButton>
          <PrimaryButton type="button" onClick={() => void handleSubmit()} disabled={saving || !toShop}>
            {saving ? "Creating…" : "Create draft"}
          </PrimaryButton>
        </div>
      </div>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────

export default function TransferOrdersPage() {
  return (
    <Suspense>
      <TransferOrdersPageInner />
    </Suspense>
  );
}

const PER_PAGE = 20;

function TransferOrdersPageInner() {
  const currency = useCurrency();
  const router = useRouter();
  const canWrite = useHasPermission("operations:write");

  const [shops, setShops] = useState<Shop[]>([]);
  const [products, setProducts] = useState<ProductOption[]>([]);
  const [transfers, setTransfers] = useState<TransferOut[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  // Filters
  const [selectedStatuses, setSelectedStatuses] = useState<string[]>([]);
  const [fromShopFilter, setFromShopFilter] = useState("");
  const [toShopFilter, setToShopFilter] = useState("");
  const [q, setQ] = useState("");

  const [showCreate, setShowCreate] = useState(false);

  useEffect(() => {
    void (async () => {
      const [shopsRes, productsRes] = await Promise.all([
        fetch("/api/ims/v1/admin/shops"),
        fetch("/api/ims/v1/admin/products"),
      ]);
      if (shopsRes.ok) setShops((await shopsRes.json()) as Shop[]);
      if (productsRes.ok) setProducts((await productsRes.json()) as ProductOption[]);
    })();
  }, []);

  const fetchTransfers = useCallback(async (p: number) => {
    setLoading(true);
    try {
      const sp = new URLSearchParams();
      selectedStatuses.forEach((s) => sp.append("status", s));
      if (fromShopFilter) sp.set("from_shop_id", fromShopFilter);
      if (toShopFilter) sp.set("to_shop_id", toShopFilter);
      if (q.trim()) sp.set("q", q.trim());
      sp.set("page", String(p));
      sp.set("per_page", String(PER_PAGE));
      const r = await fetch(`/api/ims/v1/admin/transfer-orders?${sp.toString()}`);
      if (r.ok) {
        const data = (await r.json()) as TransferListResponse;
        setTransfers(data.items);
        setTotal(data.total);
        setPage(data.page);
      }
    } finally {
      setLoading(false);
    }
  }, [selectedStatuses, fromShopFilter, toShopFilter, q]);

  useEffect(() => {
    void fetchTransfers(1);
  }, [fetchTransfers]);

  const toggleStatus = (s: string) => {
    setSelectedStatuses((prev) =>
      prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]
    );
  };

  const totalPages = Math.max(1, Math.ceil(total / PER_PAGE));

  return (
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: "Transfer Orders" }]} />
      <PageHeader
        kicker="Stock"
        title="Transfer Orders"
        subtitle="Move inventory between shops with an approval trail."
        action={
          canWrite ? (
            <PrimaryButton type="button" onClick={() => setShowCreate(true)}>
              <span className="material-symbols-outlined text-base">add</span>
              New transfer
            </PrimaryButton>
          ) : undefined
        }
      />

      {/* Status filter chips */}
      <div className="flex flex-wrap gap-2">
        {ALL_STATUSES.map((s) => {
          const active = selectedStatuses.includes(s);
          return (
            <button
              key={s}
              type="button"
              onClick={() => toggleStatus(s)}
              className={`rounded-full border px-3 py-1 text-xs font-semibold transition ${
                active
                  ? "border-primary bg-primary text-on-primary"
                  : "border-outline-variant/40 bg-surface-container-low text-on-surface-variant hover:border-primary/40"
              }`}
            >
              {statusLabel(s)}
            </button>
          );
        })}
        {selectedStatuses.length > 0 && (
          <button
            type="button"
            onClick={() => setSelectedStatuses([])}
            className="text-xs text-on-surface-variant hover:text-on-surface underline"
          >
            Clear
          </button>
        )}
      </div>

      {/* Additional filters */}
      <div className="grid gap-3 sm:grid-cols-3">
        <SelectInput
          value={fromShopFilter}
          onChange={(v) => setFromShopFilter(v)}
          options={[{ value: "", label: "From shop: all" }, ...shops.map((s) => ({ value: s.id, label: s.name }))]}
        />
        <SelectInput
          value={toShopFilter}
          onChange={(v) => setToShopFilter(v)}
          options={[{ value: "", label: "To shop: all" }, ...shops.map((s) => ({ value: s.id, label: s.name }))]}
        />
        <TextInput
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search by ID or notes…"
        />
      </div>

      <Panel title="Transfers" noPad>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-outline-variant/20 text-left text-xs font-bold uppercase tracking-widest text-on-surface-variant">
                <th className="px-4 py-3">ID</th>
                <th className="px-4 py-3">From → To</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Lines</th>
                <th className="px-4 py-3 text-right">Total Cost</th>
                <th className="px-4 py-3">Created</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <LoadingRow colSpan={6} />
              ) : transfers.length === 0 ? (
                <tr>
                  <td colSpan={6}>
                    <EmptyState title="No transfers" detail="Create a transfer order to move stock between shops." />
                  </td>
                </tr>
              ) : (
                transfers.map((t) => {
                  const cost = totalCost(t);
                  return (
                    <tr
                      key={t.id}
                      className="border-b border-outline-variant/10 hover:bg-surface-container-low cursor-pointer"
                      onClick={() => router.push(`/transfer-orders/${t.id}`)}
                    >
                      <td className="px-4 py-3 font-mono text-xs text-on-surface-variant">
                        {t.id.slice(0, 8)}…
                      </td>
                      <td className="px-4 py-3">
                        <span className="text-on-surface">{t.from_shop_name ?? "—"}</span>
                        <span className="mx-1 text-on-surface-variant">→</span>
                        <span className="text-on-surface">{t.to_shop_name ?? "—"}</span>
                      </td>
                      <td className="px-4 py-3">
                        <Badge tone={statusTone(t.status)}>{statusLabel(t.status)}</Badge>
                      </td>
                      <td className="px-4 py-3 text-right text-on-surface">{t.lines.length}</td>
                      <td className="px-4 py-3 text-right text-on-surface">
                        {cost > 0 ? formatMoney(cost, currency) : "—"}
                      </td>
                      <td className="px-4 py-3 text-xs text-on-surface-variant">
                        {new Date(t.created_at).toLocaleDateString()}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {!loading && total > PER_PAGE && (
          <div className="border-t border-outline-variant/10">
            <Pagination
              page={page}
              totalPages={totalPages}
              onChange={(p) => void fetchTransfers(p)}
              total={total}
              pageSize={PER_PAGE}
            />
          </div>
        )}
      </Panel>

      {showCreate && (
        <CreateTransferModal
          shops={shops}
          products={products}
          onClose={() => setShowCreate(false)}
          onCreated={(t) => {
            setShowCreate(false);
            router.push(`/transfer-orders/${t.id}`);
          }}
        />
      )}
    </div>
  );
}
