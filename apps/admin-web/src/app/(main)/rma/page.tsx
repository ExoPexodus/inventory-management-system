"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { formatMoney } from "@/lib/format";
import { useCurrency } from "@/lib/currency-context";
import { Breadcrumbs, PageHeader } from "@/components/ui/primitives";

type RefundRequestItem = {
  id: string;
  customer_email: string | null;
  customer_name: string | null;
  refund_type: string;
  status: string;
  reason_code: string;
  total_refund_cents: number;
  currency_code: string;
  order_id: string | null;
  sale_transaction_id: string | null;
  created_at: string;
};

const STATUS_COLORS: Record<string, string> = {
  requested: "bg-amber-100 text-amber-800",
  approved: "bg-blue-100 text-blue-800",
  rejected: "bg-red-100 text-red-800",
  received: "bg-purple-100 text-purple-800",
  refunded: "bg-green-100 text-green-800",
  closed: "bg-gray-100 text-gray-600",
  cancelled: "bg-gray-100 text-gray-500",
};

const TYPE_COLORS: Record<string, string> = {
  refund_only: "bg-indigo-100 text-indigo-800",
  return_refund: "bg-cyan-100 text-cyan-800",
  exchange: "bg-orange-100 text-orange-800",
};

const ALL_STATUSES = ["requested", "approved", "rejected", "received", "refunded", "closed", "cancelled"];

export default function RMAInboxPage() {
  const currency = useCurrency();
  const [items, setItems] = useState<RefundRequestItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const perPage = 20;
  const [loading, setLoading] = useState(true);

  const [statusFilter, setStatusFilter] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");

  async function load() {
    setLoading(true);
    try {
      const qs = new URLSearchParams();
      statusFilter.forEach((s) => qs.append("status", s));
      if (search) qs.set("q", search);
      qs.set("page", String(page));
      qs.set("per_page", String(perPage));

      const res = await fetch(`/api/ims/v1/admin/rma?${qs.toString()}`);
      if (res.ok) {
        const data = await res.json() as { items: RefundRequestItem[]; total: number };
        setItems(data.items);
        setTotal(data.total);
      }
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, [statusFilter, search, page]);

  function toggleStatus(s: string) {
    setStatusFilter((prev) =>
      prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]
    );
    setPage(1);
  }

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    setSearch(searchInput);
    setPage(1);
  }

  const totalPages = Math.max(1, Math.ceil(total / perPage));

  return (
    <div className="space-y-8">
      <Breadcrumbs items={[{ label: "Refunds" }]} />
      <PageHeader
        kicker="Sales"
        title="Refund Requests"
        subtitle="Review and process customer return and refund requests."
      />

      {/* Filters */}
      <section className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-4 shadow-sm space-y-4">
        <div className="flex flex-wrap gap-2">
          {ALL_STATUSES.map((s) => (
            <button
              key={s}
              onClick={() => toggleStatus(s)}
              className={`rounded-full px-3 py-1 text-xs font-semibold capitalize border transition-all ${
                statusFilter.includes(s)
                  ? "border-primary bg-primary text-on-primary"
                  : "border-outline-variant/30 bg-surface text-on-surface-variant hover:bg-surface-container"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
        <form onSubmit={handleSearch} className="flex gap-2">
          <input
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search by customer name or email…"
            className="flex-1 rounded-lg border border-outline-variant/30 bg-surface px-3 py-2 text-sm text-on-surface placeholder-on-surface-variant/50 focus:outline-none focus:ring-2 focus:ring-primary/40"
          />
          <button
            type="submit"
            className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-on-primary hover:bg-primary/90"
          >
            Search
          </button>
        </form>
      </section>

      {/* Table */}
      <section className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest shadow-sm overflow-hidden">
        {loading ? (
          <p className="p-6 text-sm text-on-surface-variant">Loading refund requests…</p>
        ) : items.length === 0 ? (
          <p className="p-6 text-sm text-on-surface-variant">No refund requests found.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-outline-variant/10">
                <th className="p-4 text-left text-xs font-bold uppercase tracking-widest text-on-surface-variant">ID</th>
                <th className="p-4 text-left text-xs font-bold uppercase tracking-widest text-on-surface-variant">Customer</th>
                <th className="p-4 text-left text-xs font-bold uppercase tracking-widest text-on-surface-variant">Type</th>
                <th className="p-4 text-right text-xs font-bold uppercase tracking-widest text-on-surface-variant">Amount</th>
                <th className="p-4 text-left text-xs font-bold uppercase tracking-widest text-on-surface-variant">Status</th>
                <th className="p-4 text-left text-xs font-bold uppercase tracking-widest text-on-surface-variant">Created</th>
                <th className="p-4"></th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id} className="border-b border-outline-variant/5 hover:bg-surface-container/30">
                  <td className="p-4 font-mono text-xs text-on-surface-variant">
                    {item.id.slice(0, 8).toUpperCase()}
                  </td>
                  <td className="p-4">
                    <p className="font-medium text-on-surface">{item.customer_name ?? "—"}</p>
                    <p className="text-xs text-on-surface-variant">{item.customer_email ?? ""}</p>
                  </td>
                  <td className="p-4">
                    <span className={`rounded-full px-2 py-0.5 text-xs font-semibold capitalize ${TYPE_COLORS[item.refund_type] ?? "bg-gray-100 text-gray-700"}`}>
                      {item.refund_type.replace("_", " ")}
                    </span>
                  </td>
                  <td className="p-4 text-right font-medium text-on-surface">
                    {formatMoney(item.total_refund_cents, { code: item.currency_code, exponent: currency.exponent })}
                  </td>
                  <td className="p-4">
                    <span className={`rounded-full px-2 py-0.5 text-xs font-semibold capitalize ${STATUS_COLORS[item.status] ?? "bg-gray-100 text-gray-700"}`}>
                      {item.status}
                    </span>
                  </td>
                  <td className="p-4 text-xs text-on-surface-variant">
                    {new Date(item.created_at).toLocaleDateString()}
                  </td>
                  <td className="p-4">
                    <Link
                      href={`/rma/${item.id}`}
                      className="text-xs font-semibold text-primary hover:underline"
                    >
                      View
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm text-on-surface-variant">
          <span>Page {page} of {totalPages} ({total} total)</span>
          <div className="flex gap-2">
            <button
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
              className="rounded-lg border border-outline-variant/30 px-3 py-1.5 text-xs font-semibold disabled:opacity-40 hover:bg-surface-container"
            >
              Prev
            </button>
            <button
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
              className="rounded-lg border border-outline-variant/30 px-3 py-1.5 text-xs font-semibold disabled:opacity-40 hover:bg-surface-container"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
