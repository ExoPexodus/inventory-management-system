"use client";

import { type FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { Badge, PageHeader, Panel, PrimaryButton, SecondaryButton, TextInput } from "@/components/ui/primitives";

export default function NewShopPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setMsg(null);
    setSaving(true);
    try {
      const r = await fetch("/api/ims/v1/admin/shops", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim() }),
      });
      if (r.ok) {
        router.push("/shops");
        return;
      }
      if (r.status === 409) {
        setMsg("A shop with this name already exists.");
      } else {
        setMsg(`Failed to create shop (${r.status})`);
      }
    } catch {
      setMsg("Network error. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto max-w-xl space-y-6 px-4 py-8">
      <PageHeader title="Create Shop" />

      <Panel>
        <form onSubmit={handleSubmit} className="space-y-5 p-6">
          {msg ? <Badge tone="danger">{msg}</Badge> : null}

          <div>
            <label className="mb-1.5 block text-sm font-medium text-on-surface">
              Shop name
            </label>
            <TextInput
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Main Street Branch"
              required
              maxLength={255}
            />
          </div>

          <div className="flex gap-3 pt-2">
            <PrimaryButton type="submit" disabled={saving}>
              {saving ? "Creating…" : "Create Shop"}
            </PrimaryButton>
            <SecondaryButton type="button" onClick={() => router.push("/shops")}>
              Cancel
            </SecondaryButton>
          </div>
        </form>
      </Panel>
    </div>
  );
}
