"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  Avatar,
  Badge,
  EmptyState,
  LoadingRow,
  PageHeader,
  Panel,
  SearchBar,
  SelectInput,
} from "@/components/ui/primitives";
import { formatMoneyUSD } from "@/lib/format";

type Product = {
  id: string;
  sku: string;
  name: string;
  status: string;
  category: string | null;
  unit_price_cents: number;
  reorder_point: number;
  variant_label?: string | null;
  group_title?: string | null;
};

function statusTone(s: string): "default" | "good" | "warn" | "danger" {
  const x = s.toLowerCase();
  if (x === "active") return "good";
  if (x === "draft") return "warn";
  if (x === "archived" || x === "discontinued") return "danger";
  return "default";
}

export default function ProductsPage() {
  const [rows, setRows] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [category, setCategory] = useState("");

  useEffect(() => {
    void (async () => {
      setLoading(true);
      const sp = new URLSearchParams();
      if (q.trim()) sp.set("q", q.trim());
      if (status) sp.set("status", status);
      if (category.trim()) sp.set("category", category.trim());
      const r = await fetch(`/api/ims/v1/admin/products?${sp.toString()}`);
      if (r.ok) setRows((await r.json()) as Product[]);
      else setRows([]);
      setLoading(false);
    })();
  }, [q, status, category]);

  const categories = useMemo(() => {
    const s = new Set<string>();
    for (const r of rows) {
      if (r.category) s.add(r.category);
    }
    return [...s].sort();
  }, [rows]);

  return (
    <div className="space-y-8">
      <PageHeader
        kicker="Catalog"
        title="Product library"
        subtitle="SKU truth with variant context — edit actions open the catalog tools."
        action={
          <Link
            href="/entries"
            className="ink-gradient inline-flex items-center gap-2 rounded-lg px-6 py-2.5 text-sm font-semibold text-on-primary shadow-sm transition hover:opacity-90"
          >
            <span className="material-symbols-outlined text-lg">add</span>
            New product
          </Link>
        }
      />

      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-outline-variant/10 bg-surface-container-low p-4 shadow-sm">
        <SearchBar className="min-w-[14rem] flex-1" placeholder="Search name or SKU" value={q} onChange={(e) => setQ(e.target.value)} />
        <SelectInput className="min-w-[9rem]" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All statuses</option>
          <option value="active">active</option>
          <option value="draft">draft</option>
          <option value="archived">archived</option>
          <option value="discontinued">discontinued</option>
        </SelectInput>
        <SelectInput className="min-w-[11rem]" value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">All categories</option>
          {categories.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </SelectInput>
      </div>

      <Panel title="Products" subtitle={`${rows.length} rows`} noPad>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-outline-variant/10">
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Product</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">SKU</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Category</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Status</th>
                <th className="px-6 py-3 text-right text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Unit price</th>
                <th className="px-6 py-3 text-center text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/10">
              {loading ? (
                <LoadingRow colSpan={6} label="Loading products…" />
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan={6} className="p-0">
                    <EmptyState title="No products match filters" detail="Adjust filters or create a SKU from the entry hub." />
                  </td>
                </tr>
              ) : (
                rows.map((row) => (
                <tr key={row.id} className="group hover:bg-surface-container-low/50">
                  <td className="px-6 py-3">
                    <div className="flex items-center gap-3">
                      <Avatar name={row.name} className="h-10 w-10 text-xs" />
                      <div>
                        <p className="font-headline font-bold text-on-surface">{row.name}</p>
                        <p className="text-xs text-on-surface-variant">
                          {row.variant_label || row.group_title || "Standard variant"}
                        </p>
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-3 font-mono text-xs text-on-surface">{row.sku}</td>
                  <td className="px-6 py-3 text-on-surface-variant">{row.category ?? "—"}</td>
                  <td className="px-6 py-3">
                    <Badge tone={statusTone(row.status)}>{row.status}</Badge>
                  </td>
                  <td className="px-6 py-3 text-right tabular-nums font-semibold text-on-surface">{formatMoneyUSD(row.unit_price_cents)}</td>
                  <td className="px-6 py-3 text-center">
                    <Link
                      href="/entries"
                      className="inline-flex rounded-lg p-2 text-on-surface-variant opacity-0 transition group-hover:opacity-100 hover:bg-surface-container"
                      aria-label="Edit"
                    >
                      <span className="material-symbols-outlined text-xl">edit</span>
                    </Link>
                  </td>
                </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Panel>

      <div className="rounded-xl border border-outline-variant/10 bg-surface-container-low p-6 shadow-sm">
        <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Need a new SKU?</p>
        <p className="mt-2 font-headline text-xl font-bold text-on-surface">Use the entry hub for structured creates</p>
        <p className="mt-2 text-sm text-on-surface-variant">Shops, groups, and variants stay consistent when you originate them together.</p>
        <Link
          href="/entries"
          className="mt-4 inline-flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-primary hover:underline"
        >
          Open entry hub
          <span className="material-symbols-outlined text-base">arrow_forward</span>
        </Link>
      </div>
    </div>
  );
}
