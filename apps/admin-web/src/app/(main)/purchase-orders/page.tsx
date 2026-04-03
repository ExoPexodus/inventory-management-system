"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Avatar,
  Badge,
  ErrorState,
  LoadingRow,
  PageHeader,
  PrimaryButton,
  SecondaryButton,
  SelectInput,
  TextInput,
} from "@/components/ui/primitives";
import { DateInput } from "@/components/ui/DateInput";
import { formatMoney } from "@/lib/format";
import { useCurrency } from "@/lib/currency-context";

type Supplier = { id: string; name: string; status: string };
type Product = { id: string; sku: string; name: string; unit_price_cents: number };

type POLine = {
  id: string;
  product_id: string;
  product_name: string;
  product_sku: string;
  quantity_ordered: number;
  quantity_received: number;
  unit_cost_cents: number;
};

type PO = {
  id: string;
  supplier_id: string;
  supplier_name: string;
  status: string;
  notes: string | null;
  expected_delivery_date: string | null;
  created_at: string;
  updated_at: string;
  lines: POLine[];
};

function poStatusClass(s: string): string {
  const x = s.toLowerCase();
  if (x === "draft") return "bg-surface-container-high text-on-surface-variant";
  if (x === "ordered") return "bg-secondary-container text-on-secondary-container";
  if (x === "received") return "bg-tertiary-fixed text-on-tertiary-fixed-variant";
  return "bg-error-container text-on-error-container";
}

export default function PurchaseOrdersPage() {
  const currency = useCurrency();
  const [pos, setPos] = useState<PO[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [products, setProducts] = useState<Product[]>([]);

  // create form
  const [showCreate, setShowCreate] = useState(false);
  const [supplierId, setSupplierId] = useState("");
  const [createNotes, setCreateNotes] = useState("");
  const [createDelivery, setCreateDelivery] = useState("");
  const [creating, setCreating] = useState(false);

  const selected = useMemo(() => pos.find((p) => p.id === selectedId) ?? null, [pos, selectedId]);

  async function refresh() {
    setLoading(true);
    setErr(null);
    const r = await fetch("/api/ims/v1/admin/purchase-orders/");
    if (r.ok) {
      setPos((await r.json()) as PO[]);
    } else {
      setErr(`Failed to load purchase orders (${r.status})`);
    }
    setLoading(false);
  }

  useEffect(() => {
    void refresh();
    void (async () => {
      const [sr, pr] = await Promise.all([
        fetch("/api/ims/v1/admin/suppliers"),
        fetch("/api/ims/v1/admin/products"),
      ]);
      if (sr.ok) {
        const list = (await sr.json()) as Supplier[];
        setSuppliers(list);
        setSupplierId((p) => p || list[0]?.id || "");
      }
      if (pr.ok) setProducts((await pr.json()) as Product[]);
    })();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const stats = useMemo(() => ({
    draft: pos.filter((p) => p.status === "draft").length,
    ordered: pos.filter((p) => p.status === "ordered").length,
    received: pos.filter((p) => p.status === "received").length,
  }), [pos]);

  async function onCreate(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setCreating(true);
    const r = await fetch("/api/ims/v1/admin/purchase-orders/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        supplier_id: supplierId,
        notes: createNotes.trim() || null,
        expected_delivery_date: createDelivery || null,
      }),
    });
    if (r.ok) {
      const po = (await r.json()) as PO;
      setPos((prev) => [po, ...prev]);
      setSelectedId(po.id);
      setCreateNotes("");
      setCreateDelivery("");
      setShowCreate(false);
    } else {
      setErr(`Create failed (${r.status})`);
    }
    setCreating(false);
  }

  async function transition(poId: string, newStatus: string) {
    const r = await fetch(`/api/ims/v1/admin/purchase-orders/${poId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: newStatus }),
    });
    if (r.ok) {
      const updated = (await r.json()) as PO;
      setPos((prev) => prev.map((p) => (p.id === poId ? updated : p)));
    } else {
      const body = await r.json().catch(() => ({})) as { detail?: string };
      setErr(body.detail ?? `Action failed (${r.status})`);
    }
  }

  async function deleteDraft(poId: string) {
    const r = await fetch(`/api/ims/v1/admin/purchase-orders/${poId}`, { method: "DELETE" });
    if (r.ok || r.status === 204) {
      setPos((prev) => prev.filter((p) => p.id !== poId));
      if (selectedId === poId) setSelectedId(null);
    } else {
      setErr(`Delete failed (${r.status})`);
    }
  }

  async function addLine(poId: string, productId: string, qty: number, costCents: number) {
    const r = await fetch(`/api/ims/v1/admin/purchase-orders/${poId}/lines`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ product_id: productId, quantity_ordered: qty, unit_cost_cents: costCents }),
    });
    if (r.ok) {
      const updated = (await r.json()) as PO;
      setPos((prev) => prev.map((p) => (p.id === poId ? updated : p)));
    } else {
      const body = await r.json().catch(() => ({})) as { detail?: string };
      setErr(body.detail ?? `Add line failed (${r.status})`);
    }
  }

  async function removeLine(poId: string, lineId: string) {
    const r = await fetch(`/api/ims/v1/admin/purchase-orders/${poId}/lines/${lineId}`, { method: "DELETE" });
    if (r.ok) {
      const updated = (await r.json()) as PO;
      setPos((prev) => prev.map((p) => (p.id === poId ? updated : p)));
    } else {
      setErr(`Remove line failed (${r.status})`);
    }
  }

  return (
    <div className="space-y-8">
      <PageHeader
        kicker="Procurement"
        title="Purchase orders"
        subtitle="Manage vendor orders — submit to lock them in, mark received to update stock."
        action={
          <button
            type="button"
            onClick={() => setShowCreate((v) => !v)}
            className="ink-gradient inline-flex items-center gap-2 rounded-lg px-6 py-2.5 text-sm font-semibold text-on-primary shadow-sm transition hover:opacity-90"
          >
            <span className="material-symbols-outlined text-lg">post_add</span>
            New draft PO
          </button>
        }
      />

      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Draft</p>
          <p className="mt-4 font-headline text-3xl font-extrabold text-primary">{stats.draft}</p>
        </div>
        <div className="rounded-xl border border-secondary/25 bg-secondary-container/25 p-6 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Ordered</p>
          <p className="mt-4 font-headline text-3xl font-extrabold text-secondary">{stats.ordered}</p>
          <p className="mt-1 text-xs font-semibold text-secondary">Awaiting vendor delivery</p>
        </div>
        <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Received</p>
          <p className="mt-4 font-headline text-3xl font-extrabold text-primary">{stats.received}</p>
        </div>
      </div>

      {showCreate ? (
        <form
          onSubmit={onCreate}
          className="space-y-4 rounded-xl border border-outline-variant/10 bg-surface-container-low p-6 shadow-sm"
        >
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">New purchase order</p>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block text-sm font-medium text-on-surface">
              Supplier
              <SelectInput
                className="mt-1"
                value={supplierId}
                onChange={setSupplierId}
                placeholder="Select supplier"
                options={suppliers.map((s) => ({ value: s.id, label: s.name }))}
              />
            </label>
            <label className="block text-sm font-medium text-on-surface">
              Expected delivery
              <DateInput className="mt-1" value={createDelivery} onChange={setCreateDelivery} placeholder="Select date" />
            </label>
            <label className="block text-sm font-medium text-on-surface sm:col-span-2">
              Notes
              <TextInput className="mt-1" value={createNotes} onChange={(e) => setCreateNotes(e.target.value)} placeholder="Internal memo" />
            </label>
          </div>
          <div className="flex gap-2">
            <PrimaryButton type="submit" disabled={creating || !supplierId}>{creating ? "Creating…" : "Save draft"}</PrimaryButton>
            <SecondaryButton type="button" onClick={() => setShowCreate(false)}>Cancel</SecondaryButton>
          </div>
        </form>
      ) : null}

      {err ? <ErrorState detail={err} /> : null}

      <div className="grid gap-6 lg:grid-cols-12">
        {/* PO list */}
        <section className="overflow-hidden rounded-xl border border-outline-variant/10 bg-surface-container-lowest shadow-sm lg:col-span-5">
          <div className="border-b border-outline-variant/10 px-6 py-4">
            <h3 className="font-headline text-lg font-bold text-on-surface">All purchase orders</h3>
            <p className="text-sm text-on-surface-variant">Click a row to view or edit details</p>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead>
                <tr className="border-b border-outline-variant/10">
                  <th className="px-4 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Supplier</th>
                  <th className="px-4 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Status</th>
                  <th className="px-4 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Lines</th>
                  <th className="px-4 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Created</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant/10">
                {loading ? (
                  <LoadingRow colSpan={4} />
                ) : pos.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-6 py-12 text-center text-sm text-on-surface-variant">
                      No purchase orders yet — create one above.
                    </td>
                  </tr>
                ) : (
                  pos.map((p) => (
                    <tr
                      key={p.id}
                      onClick={() => setSelectedId(p.id === selectedId ? null : p.id)}
                      className={`cursor-pointer hover:bg-surface-container-low/60 ${p.id === selectedId ? "bg-primary/5" : ""}`}
                    >
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <Avatar name={p.supplier_name} className="h-8 w-8 text-[10px]" />
                          <span className="font-medium text-on-surface">{p.supplier_name}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex rounded-full px-2.5 py-1 text-[10px] font-bold uppercase ${poStatusClass(p.status)}`}>
                          {p.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 tabular-nums text-on-surface-variant">{p.lines.length}</td>
                      <td className="px-4 py-3 font-mono text-xs text-on-surface-variant">{p.created_at.slice(0, 10)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>

        {/* Detail panel */}
        <section className="lg:col-span-7">
          {selected ? (
            <PODetailPanel
              po={selected}
              products={products}
              onTransition={transition}
              onDelete={deleteDraft}
              onAddLine={addLine}
              onRemoveLine={removeLine}
            />
          ) : (
            <div className="flex h-full min-h-[20rem] items-center justify-center rounded-xl border border-dashed border-outline-variant/30 bg-surface-container-lowest">
              <p className="text-sm text-on-surface-variant">Select a purchase order to view details</p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function PODetailPanel({
  po,
  products,
  onTransition,
  onDelete,
  onAddLine,
  onRemoveLine,
}: {
  po: PO;
  products: Product[];
  onTransition: (id: string, status: string) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  onAddLine: (poId: string, productId: string, qty: number, costCents: number) => Promise<void>;
  onRemoveLine: (poId: string, lineId: string) => Promise<void>;
}) {
  const currency = useCurrency();
  const [lineProductId, setLineProductId] = useState(products[0]?.id ?? "");
  const [lineQty, setLineQty] = useState("1");
  const [lineCostUsd, setLineCostUsd] = useState("");
  const [addingLine, setAddingLine] = useState(false);
  const [lineErr, setLineErr] = useState<string | null>(null);
  const [actioning, setActioning] = useState(false);

  // Pre-fill cost from product's unit price when product changes
  const selectedProduct = products.find((p) => p.id === lineProductId);
  const prevProductId = useRef(lineProductId);
  if (prevProductId.current !== lineProductId) {
    prevProductId.current = lineProductId;
    if (selectedProduct) {
      setLineCostUsd((selectedProduct.unit_price_cents / 100).toFixed(2));
    }
  }

  const isDraft = po.status === "draft";
  const isOrdered = po.status === "ordered";
  const isTerminal = po.status === "received" || po.status === "cancelled";

  const lineTotal = po.lines.reduce((acc, l) => acc + l.quantity_ordered * l.unit_cost_cents, 0);

  async function handleAddLine(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const qty = parseInt(lineQty, 10);
    const costCents = Math.round(parseFloat(lineCostUsd) * 100);
    if (!lineProductId || isNaN(qty) || qty <= 0 || isNaN(costCents) || costCents < 0) {
      setLineErr("Enter valid product, quantity, and cost");
      return;
    }
    setAddingLine(true);
    setLineErr(null);
    await onAddLine(po.id, lineProductId, qty, costCents);
    setLineQty("1");
    setLineCostUsd(selectedProduct ? (selectedProduct.unit_price_cents / 100).toFixed(2) : "");
    setAddingLine(false);
  }

  return (
    <div className="space-y-4 rounded-xl border border-outline-variant/10 bg-surface-container-lowest shadow-sm">
      {/* Header */}
      <div className="ink-gradient rounded-t-xl px-6 py-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-bold uppercase tracking-widest text-on-primary/80">Purchase order</p>
            <p className="mt-1 font-headline text-xl font-extrabold text-on-primary">{po.supplier_name}</p>
            <p className="mt-0.5 font-mono text-xs text-on-primary/70">{po.id}</p>
          </div>
          <span className={`mt-1 rounded-full px-2.5 py-1 text-[10px] font-bold uppercase ${poStatusClass(po.status)}`}>
            {po.status}
          </span>
        </div>
        {po.notes ? <p className="mt-2 text-xs text-on-primary/80">{po.notes}</p> : null}
        {po.expected_delivery_date ? (
          <p className="mt-1 text-xs text-on-primary/70">
            Expected: {po.expected_delivery_date.slice(0, 10)}
          </p>
        ) : null}
      </div>

      {/* Lines table */}
      <div className="px-6">
        <p className="mb-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Line items</p>
        {po.lines.length === 0 ? (
          <p className="rounded-lg border border-dashed border-outline-variant/30 py-6 text-center text-sm text-on-surface-variant">
            No lines — add products below.
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-outline-variant/10 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">
                <th className="pb-2 text-left">Product</th>
                <th className="pb-2 text-center">Qty ord.</th>
                <th className="pb-2 text-center">Qty recv.</th>
                <th className="pb-2 text-right">Unit cost</th>
                <th className="pb-2 text-right">Total</th>
                {isDraft ? <th className="pb-2" /> : null}
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/10">
              {po.lines.map((l) => (
                <tr key={l.id}>
                  <td className="py-2">
                    <p className="font-medium text-on-surface">{l.product_name}</p>
                    <p className="font-mono text-[11px] text-on-surface-variant">{l.product_sku}</p>
                  </td>
                  <td className="py-2 text-center tabular-nums text-on-surface">{l.quantity_ordered}</td>
                  <td className="py-2 text-center tabular-nums text-on-surface-variant">{l.quantity_received}</td>
                  <td className="py-2 text-right tabular-nums text-on-surface-variant">{formatMoney(l.unit_cost_cents, currency)}</td>
                  <td className="py-2 text-right tabular-nums font-semibold text-on-surface">{formatMoney(l.quantity_ordered * l.unit_cost_cents, currency)}</td>
                  {isDraft ? (
                    <td className="py-2 pl-2">
                      <button
                        type="button"
                        onClick={() => void onRemoveLine(po.id, l.id)}
                        className="rounded p-1 text-on-surface-variant transition hover:bg-error-container hover:text-on-error-container"
                        aria-label="Remove line"
                      >
                        <span className="material-symbols-outlined text-base">close</span>
                      </button>
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t border-outline-variant/10">
                <td colSpan={isDraft ? 4 : 3} className="pt-2 text-xs font-bold uppercase tracking-widest text-on-surface-variant">Total</td>
                <td className="pt-2 text-right tabular-nums font-bold text-on-surface">{formatMoney(lineTotal, currency)}</td>
                {isDraft ? <td /> : null}
              </tr>
            </tfoot>
          </table>
        )}
      </div>

      {/* Add line form (draft only) */}
      {isDraft ? (
        <form onSubmit={handleAddLine} className="border-t border-outline-variant/10 px-6 pb-2 pt-4">
          <p className="mb-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Add line</p>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="sm:col-span-3">
              <label className="block text-xs font-medium text-on-surface-variant">Product</label>
              <SelectInput
                className="mt-1"
                value={lineProductId}
                onChange={setLineProductId}
                options={products.map((p) => ({ value: p.id, label: `${p.sku} — ${p.name}` }))}
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-on-surface-variant">Qty</label>
              <TextInput
                type="number"
                min="1"
                className="mt-1"
                value={lineQty}
                onChange={(e) => setLineQty(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-on-surface-variant">Unit cost (USD)</label>
              <TextInput
                type="number"
                min="0"
                step="0.01"
                className="mt-1"
                value={lineCostUsd}
                onChange={(e) => setLineCostUsd(e.target.value)}
              />
            </div>
            <div className="flex items-end">
              <PrimaryButton type="submit" disabled={addingLine} className="w-full">
                {addingLine ? "Adding…" : "Add line"}
              </PrimaryButton>
            </div>
          </div>
          {lineErr ? <p className="mt-2 text-xs text-error">{lineErr}</p> : null}
        </form>
      ) : null}

      {/* Action buttons */}
      {!isTerminal ? (
        <div className="flex flex-wrap gap-2 border-t border-outline-variant/10 px-6 pb-6 pt-4">
          {isDraft ? (
            <>
              <PrimaryButton
                disabled={actioning || po.lines.length === 0}
                onClick={async () => { setActioning(true); await onTransition(po.id, "ordered"); setActioning(false); }}
              >
                <span className="material-symbols-outlined mr-1.5 text-base">send</span>
                Submit to vendor
              </PrimaryButton>
              <SecondaryButton
                disabled={actioning}
                onClick={async () => { setActioning(true); await onDelete(po.id); setActioning(false); }}
              >
                <span className="material-symbols-outlined mr-1.5 text-base">delete</span>
                Delete draft
              </SecondaryButton>
            </>
          ) : isOrdered ? (
            <>
              <PrimaryButton
                disabled={actioning}
                onClick={async () => { setActioning(true); await onTransition(po.id, "received"); setActioning(false); }}
              >
                <span className="material-symbols-outlined mr-1.5 text-base">inventory_2</span>
                Mark received
              </PrimaryButton>
              <SecondaryButton
                disabled={actioning}
                onClick={async () => { setActioning(true); await onTransition(po.id, "cancelled"); setActioning(false); }}
              >
                Cancel order
              </SecondaryButton>
            </>
          ) : null}
        </div>
      ) : (
        <div className="px-6 pb-6 pt-2">
          <Badge tone={po.status === "received" ? "good" : "danger"}>
            {po.status === "received" ? "Stock updated — order complete" : "Order cancelled"}
          </Badge>
        </div>
      )}
    </div>
  );
}
