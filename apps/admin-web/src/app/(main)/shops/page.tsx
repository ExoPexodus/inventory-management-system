"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ErrorState, PageHeader, Panel, PrimaryButton } from "@/components/ui/primitives";

type Shop = {
  id: string;
  tenant_id: string;
  name: string;
  created_at: string;
};

export default function ShopsPage() {
  const [shops, setShops] = useState<Shop[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const r = await fetch("/api/ims/v1/admin/shops");
        if (r.ok) {
          setShops((await r.json()) as Shop[]);
        } else {
          setErr(`Failed to load shops (${r.status})`);
        }
      } catch {
        setErr("Network error loading shops.");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <div className="mx-auto max-w-3xl space-y-6 px-4 py-8">
      <div className="flex items-center justify-between">
        <PageHeader title="Shops" />
        <Link href="/shops/new">
          <PrimaryButton>New Shop</PrimaryButton>
        </Link>
      </div>

      <Panel>
        {loading ? (
          <div className="px-6 py-8 text-center text-sm text-on-surface-variant">Loading shops…</div>
        ) : err ? (
          <div className="px-6 py-4">
            <ErrorState detail={err} />
          </div>
        ) : shops.length === 0 ? (
          <div className="px-6 py-10 text-center">
            <p className="text-sm text-on-surface-variant">No shops yet.</p>
            <p className="mt-1 text-sm text-on-surface-variant">
              <Link href="/shops/new" className="text-primary underline">
                Create your first shop
              </Link>
            </p>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-outline-variant/20">
                <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wide text-on-surface-variant">Name</th>
                <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wide text-on-surface-variant">Created</th>
              </tr>
            </thead>
            <tbody>
              {shops.map((shop) => (
                <tr key={shop.id} className="border-b border-outline-variant/10 last:border-0">
                  <td className="px-6 py-4 font-medium text-on-surface">{shop.name}</td>
                  <td className="px-6 py-4 text-on-surface-variant">
                    {new Date(shop.created_at).toLocaleDateString(undefined, {
                      year: "numeric",
                      month: "short",
                      day: "numeric",
                    })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}
