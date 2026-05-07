"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Badge,
  PageHeader,
  Panel,
  PrimaryButton,
  TextInput,
} from "@/components/ui/primitives";

type TaxComponent = { label: string; rate_bps: number };

type TaxRegion = {
  id: string;
  name: string;
  country_code: string;
  state_code: string | null;
  created_at: string;
};

type TaxRule = {
  id: string;
  region_id: string;
  tax_class: string;
  label: string;
  components: TaxComponent[];
  created_at: string;
};

export default function TaxPage() {
  const [regions, setRegions] = useState<TaxRegion[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [expandedRegionId, setExpandedRegionId] = useState<string | null>(null);
  const [rulesCache, setRulesCache] = useState<Record<string, TaxRule[]>>({});
  const [rulesLoading, setRulesLoading] = useState(false);

  // Create region form
  const [showRegionForm, setShowRegionForm] = useState(false);
  const [regionName, setRegionName] = useState("");
  const [regionCountry, setRegionCountry] = useState("");
  const [regionState, setRegionState] = useState("");
  const [regionSaving, setRegionSaving] = useState(false);
  const [regionErr, setRegionErr] = useState<string | null>(null);

  // Create rule form
  const [ruleRegionId, setRuleRegionId] = useState<string | null>(null);
  const [ruleTaxClass, setRuleTaxClass] = useState("standard");
  const [ruleLabel, setRuleLabel] = useState("");
  const [ruleComponents, setRuleComponents] = useState<TaxComponent[]>([{ label: "Tax", rate_bps: 0 }]);
  const [ruleSaving, setRuleSaving] = useState(false);
  const [ruleErr, setRuleErr] = useState<string | null>(null);

  const loadRegions = useCallback(async () => {
    setLoading(true);
    setLoadErr(null);
    try {
      const r = await fetch("/api/ims/v1/admin/tax/regions");
      if (!r.ok) throw new Error(`Failed to load regions (${r.status})`);
      setRegions((await r.json()) as TaxRegion[]);
    } catch (e) {
      setLoadErr(e instanceof Error ? e.message : "Failed to load tax regions.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadRegions();
  }, [loadRegions]);

  async function loadRules(regionId: string) {
    if (rulesCache[regionId]) return;
    setRulesLoading(true);
    try {
      const r = await fetch(`/api/ims/v1/admin/tax/regions/${regionId}/rules`);
      if (r.ok) setRulesCache((prev) => ({ ...prev, [regionId]: (await r.json()) as TaxRule[] }));
    } finally {
      setRulesLoading(false);
    }
  }

  function toggleRegion(id: string) {
    if (expandedRegionId === id) {
      setExpandedRegionId(null);
    } else {
      setExpandedRegionId(id);
      setRuleRegionId(null);
      void loadRules(id);
    }
  }

  async function handleCreateRegion(e: React.FormEvent) {
    e.preventDefault();
    setRegionSaving(true);
    setRegionErr(null);
    try {
      const r = await fetch("/api/ims/v1/admin/tax/regions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: regionName.trim(),
          country_code: regionCountry.trim().toUpperCase(),
          state_code: regionState.trim().toUpperCase() || null,
        }),
      });
      if (r.ok) {
        setShowRegionForm(false);
        setRegionName(""); setRegionCountry(""); setRegionState("");
        void loadRegions();
      } else {
        const d = await r.json().catch(() => ({})) as { detail?: string };
        setRegionErr(d.detail ?? `Failed (${r.status})`);
      }
    } catch {
      setRegionErr("Network error. Please try again.");
    } finally {
      setRegionSaving(false);
    }
  }

  async function handleDeleteRegion(id: string) {
    if (!confirm("Delete this tax region and all its rules?")) return;
    try {
      const r = await fetch(`/api/ims/v1/admin/tax/regions/${id}`, { method: "DELETE" });
      if (r.ok) {
        setRulesCache((prev) => { const n = { ...prev }; delete n[id]; return n; });
        void loadRegions();
      } else {
        alert(`Failed to delete region (${r.status})`);
      }
    } catch {
      alert("Network error. Could not delete region.");
    }
  }

  function updateComponent(index: number, field: keyof TaxComponent, value: string | number) {
    setRuleComponents((prev) =>
      prev.map((c, i) => (i === index ? { ...c, [field]: value } : c))
    );
  }

  function addComponent() {
    setRuleComponents((prev) => [...prev, { label: "", rate_bps: 0 }]);
  }

  function removeComponent(index: number) {
    setRuleComponents((prev) => prev.filter((_, i) => i !== index));
  }

  async function handleCreateRule(e: React.FormEvent) {
    e.preventDefault();
    if (!ruleRegionId) return;
    setRuleSaving(true);
    setRuleErr(null);
    try {
      const r = await fetch(`/api/ims/v1/admin/tax/regions/${ruleRegionId}/rules`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tax_class: ruleTaxClass.trim() || "standard",
          label: ruleLabel.trim(),
          components: ruleComponents.map((c) => ({
            label: c.label,
            rate_bps: Number(c.rate_bps),
          })),
        }),
      });
      if (r.ok) {
        const savedRegionId = ruleRegionId;
        setRuleRegionId(null);
        setRuleTaxClass("standard");
        setRuleLabel("");
        setRuleComponents([{ label: "Tax", rate_bps: 0 }]);
        setRuleErr(null);
        // Inline fetch to avoid stale-closure early-return in loadRules
        try {
          const rulesRes = await fetch(`/api/ims/v1/admin/tax/regions/${savedRegionId}/rules`);
          if (rulesRes.ok) {
            setRulesCache((prev) => ({ ...prev, [savedRegionId]: (await rulesRes.json()) as TaxRule[] }));
          }
        } catch {
          // non-critical — rules will reload on next expand
        }
      } else {
        const d = await r.json().catch(() => ({})) as { detail?: string };
        setRuleErr(d.detail ?? `Failed (${r.status})`);
      }
    } catch {
      setRuleErr("Network error. Please try again.");
    } finally {
      setRuleSaving(false);
    }
  }

  async function handleDeleteRule(regionId: string, ruleId: string) {
    if (!confirm("Delete this tax rule?")) return;
    try {
      const r = await fetch(`/api/ims/v1/admin/tax/regions/${regionId}/rules/${ruleId}`, { method: "DELETE" });
      if (r.ok) {
        setRulesCache((prev) => ({
          ...prev,
          [regionId]: (prev[regionId] ?? []).filter((ru) => ru.id !== ruleId),
        }));
      } else {
        alert(`Failed to delete rule (${r.status})`);
      }
    } catch {
      alert("Network error. Could not delete rule.");
    }
  }

  return (
    <div className="space-y-8">
      <PageHeader
        kicker="Commerce"
        title="Tax"
        subtitle="Define tax regions and rules applied at checkout."
        action={
          <PrimaryButton type="button" onClick={() => { setShowRegionForm((p) => !p); setRegionErr(null); }}>
            <span className="material-symbols-outlined text-lg">{showRegionForm ? "close" : "add"}</span>
            {showRegionForm ? "Cancel" : "New region"}
          </PrimaryButton>
        }
      />

      {showRegionForm && (
        <form
          onSubmit={(e) => void handleCreateRegion(e)}
          className="rounded-xl border border-outline-variant/10 bg-surface-container-low p-5 space-y-4"
        >
          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <label className="block text-sm font-medium text-on-surface mb-1">Region name</label>
              <TextInput value={regionName} onChange={(e) => setRegionName(e.target.value)} placeholder="e.g. India" required />
            </div>
            <div>
              <label className="block text-sm font-medium text-on-surface mb-1">Country code (ISO 2)</label>
              <TextInput value={regionCountry} onChange={(e) => setRegionCountry(e.target.value)} placeholder="IN" maxLength={2} required />
            </div>
            <div>
              <label className="block text-sm font-medium text-on-surface mb-1">State code (optional)</label>
              <TextInput value={regionState} onChange={(e) => setRegionState(e.target.value)} placeholder="MH" maxLength={4} />
            </div>
          </div>
          {regionErr && <p className="text-sm text-error">{regionErr}</p>}
          <PrimaryButton type="submit" disabled={regionSaving}>
            {regionSaving ? "Creating…" : "Create region"}
          </PrimaryButton>
        </form>
      )}

      <Panel title="Tax regions" subtitle={`${regions.length} region${regions.length === 1 ? "" : "s"}`} noPad>
        {loading ? (
          <p className="px-6 py-8 text-sm text-on-surface-variant">Loading…</p>
        ) : loadErr ? (
          <p className="px-6 py-8 text-center text-sm text-error">{loadErr}</p>
        ) : regions.length === 0 ? (
          <p className="px-6 py-8 text-center text-sm text-on-surface-variant">No tax regions configured.</p>
        ) : (
          <div className="divide-y divide-outline-variant/10">
            {regions.map((region) => (
              <div key={region.id}>
                <div className="flex items-center justify-between px-6 py-4 hover:bg-surface-container-low/50">
                  <div className="flex items-center gap-4">
                    <button
                      type="button"
                      onClick={() => toggleRegion(region.id)}
                      className="flex items-center gap-2 text-left"
                    >
                      <span className="material-symbols-outlined text-base text-on-surface-variant">
                        {expandedRegionId === region.id ? "expand_less" : "expand_more"}
                      </span>
                      <span className="font-medium text-on-surface text-sm">{region.name}</span>
                    </button>
                    <Badge tone="default">
                      {region.country_code}{region.state_code ? `-${region.state_code}` : ""}
                    </Badge>
                  </div>
                  <button
                    type="button"
                    onClick={() => void handleDeleteRegion(region.id)}
                    className="inline-flex items-center gap-1 rounded-lg border border-error/30 bg-error-container/10 px-3 py-1.5 text-xs font-semibold text-error transition hover:bg-error-container/30"
                  >
                    <span className="material-symbols-outlined text-sm">delete</span>
                    Delete
                  </button>
                </div>

                {expandedRegionId === region.id && (
                  <div className="border-t border-outline-variant/10 bg-surface-container-lowest px-6 py-4 space-y-4">
                    <div className="flex items-center justify-between">
                      <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Tax rules</p>
                      <button
                        type="button"
                        onClick={() => setRuleRegionId(ruleRegionId === region.id ? null : region.id)}
                        className="text-xs font-semibold text-primary hover:underline"
                      >
                        {ruleRegionId === region.id ? "Cancel" : "+ Add rule"}
                      </button>
                    </div>

                    {ruleRegionId === region.id && (
                      <form onSubmit={(e) => void handleCreateRule(e)} className="rounded-xl border border-outline-variant/10 bg-surface-container-low p-4 space-y-3">
                        <div className="grid gap-3 sm:grid-cols-2">
                          <div>
                            <label className="block text-xs font-medium text-on-surface mb-1">Tax class</label>
                            <TextInput
                              value={ruleTaxClass}
                              onChange={(e) => setRuleTaxClass(e.target.value)}
                              placeholder="standard"
                            />
                            <p className="mt-1 text-[11px] text-on-surface-variant">e.g. standard, reduced, zero</p>
                          </div>
                          <div>
                            <label className="block text-xs font-medium text-on-surface mb-1">Rule label</label>
                            <TextInput
                              value={ruleLabel}
                              onChange={(e) => setRuleLabel(e.target.value)}
                              placeholder="GST 18%"
                              required
                            />
                          </div>
                        </div>

                        <div>
                          <p className="text-xs font-medium text-on-surface mb-2">Components</p>
                          {ruleComponents.map((comp, idx) => (
                            <div key={idx} className="flex gap-2 mb-2 items-center">
                              <TextInput
                                value={comp.label}
                                onChange={(e) => updateComponent(idx, "label", e.target.value)}
                                placeholder="CGST"
                                className="flex-1"
                              />
                              <TextInput
                                type="number"
                                value={String(comp.rate_bps)}
                                onChange={(e) => updateComponent(idx, "rate_bps", parseInt(e.target.value, 10) || 0)}
                                placeholder="900"
                                className="w-28"
                              />
                              <span className="text-xs text-on-surface-variant whitespace-nowrap">
                                bps ({(Number(comp.rate_bps) / 100).toFixed(1)}%)
                              </span>
                              {ruleComponents.length > 1 && (
                                <button type="button" onClick={() => removeComponent(idx)}
                                  className="text-xs text-error hover:underline">Remove</button>
                              )}
                            </div>
                          ))}
                          <button type="button" onClick={addComponent}
                            className="text-xs font-semibold text-primary hover:underline">
                            + Add component
                          </button>
                        </div>

                        {ruleErr && <p className="text-xs text-error">{ruleErr}</p>}
                        <PrimaryButton type="submit" disabled={ruleSaving}>
                          {ruleSaving ? "Saving…" : "Add rule"}
                        </PrimaryButton>
                      </form>
                    )}

                    {rulesLoading ? (
                      <p className="text-xs text-on-surface-variant">Loading rules…</p>
                    ) : (rulesCache[region.id] ?? []).length === 0 ? (
                      <p className="text-xs text-on-surface-variant">No rules yet.</p>
                    ) : (
                      <table className="min-w-full text-left text-xs">
                        <thead>
                          <tr className="border-b border-outline-variant/10">
                            <th className="py-2 pr-4 font-bold uppercase tracking-wider text-on-surface-variant">Class</th>
                            <th className="py-2 pr-4 font-bold uppercase tracking-wider text-on-surface-variant">Label</th>
                            <th className="py-2 pr-4 font-bold uppercase tracking-wider text-on-surface-variant">Components</th>
                            <th className="py-2 font-bold uppercase tracking-wider text-on-surface-variant">Actions</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-outline-variant/10">
                          {(rulesCache[region.id] ?? []).map((rule) => (
                            <tr key={rule.id}>
                              <td className="py-2 pr-4 font-mono text-on-surface">{rule.tax_class}</td>
                              <td className="py-2 pr-4 text-on-surface">{rule.label}</td>
                              <td className="py-2 pr-4">
                                <div className="flex flex-wrap gap-1">
                                  {rule.components.map((c, i) => (
                                    <span key={i} className="rounded-full bg-surface-container px-2 py-0.5 text-[10px] text-on-surface-variant">
                                      {c.label}: {(c.rate_bps / 100).toFixed(1)}%
                                    </span>
                                  ))}
                                </div>
                              </td>
                              <td className="py-2">
                                <button
                                  type="button"
                                  onClick={() => void handleDeleteRule(region.id, rule.id)}
                                  className="text-error hover:underline text-xs"
                                >
                                  Delete
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
