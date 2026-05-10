"use client";

import { useCallback, useEffect, useState } from "react";
import {
  EmptyState,
  PageHeader,
  Panel,
  PrimaryButton,
  SecondaryButton,
  SelectInput,
  TextInput,
} from "@/components/ui/primitives";

type Category = {
  id: string;
  slug: string;
  name: string;
  parent_id: string | null;
  description: string | null;
  sort_order: number;
  created_at: string;
  updated_at: string;
};

type CategoryNode = Category & { children: CategoryNode[] };

function buildTree(flat: Category[]): CategoryNode[] {
  const map = new Map<string, CategoryNode>();
  for (const c of flat) {
    map.set(c.id, { ...c, children: [] });
  }
  const roots: CategoryNode[] = [];
  for (const node of map.values()) {
    if (node.parent_id && map.has(node.parent_id)) {
      map.get(node.parent_id)!.children.push(node);
    } else {
      roots.push(node);
    }
  }
  function sortNodes(nodes: CategoryNode[]) {
    nodes.sort((a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name));
    for (const n of nodes) sortNodes(n.children);
  }
  sortNodes(roots);
  return roots;
}

// ─── CategoryRow ──────────────────────────────────────────────────────────────

function CategoryRow({
  node,
  depth,
  allFlat,
  onEdit,
  onAddChild,
  onDelete,
  onMoveUp,
  onMoveDown,
  isFirst,
  isLast,
}: {
  node: CategoryNode;
  depth: number;
  allFlat: Category[];
  onEdit: (cat: Category) => void;
  onAddChild: (parentId: string) => void;
  onDelete: (cat: Category) => void;
  onMoveUp: (cat: Category) => void;
  onMoveDown: (cat: Category) => void;
  isFirst: boolean;
  isLast: boolean;
}) {
  const [expanded, setExpanded] = useState(true);
  const hasChildren = node.children.length > 0;

  return (
    <>
      <tr className="group hover:bg-surface-container-low/50">
        <td className="px-4 py-2.5">
          <div className="flex items-center" style={{ paddingLeft: `${depth * 24}px` }}>
            {hasChildren ? (
              <button
                type="button"
                onClick={() => setExpanded((p) => !p)}
                className="mr-1.5 flex h-5 w-5 items-center justify-center rounded text-on-surface-variant hover:bg-surface-container"
                aria-label={expanded ? "Collapse" : "Expand"}
              >
                <span className="material-symbols-outlined text-base leading-none">
                  {expanded ? "expand_more" : "chevron_right"}
                </span>
              </button>
            ) : (
              <span className="mr-1.5 h-5 w-5 shrink-0" />
            )}
            <div>
              <p className="text-sm font-medium text-on-surface">{node.name}</p>
              <p className="text-[11px] text-on-surface-variant">{node.slug}</p>
            </div>
          </div>
        </td>
        <td className="px-4 py-2.5 text-sm text-on-surface-variant">
          {node.description ? (
            <span className="max-w-xs truncate block">{node.description}</span>
          ) : (
            <span className="text-on-surface-variant/40">—</span>
          )}
        </td>
        <td className="px-4 py-2.5 text-center">
          <span className="inline-flex items-center rounded-full bg-surface-container px-2 py-0.5 text-xs font-bold text-on-surface-variant">
            {node.sort_order}
          </span>
        </td>
        <td className="px-4 py-2.5 text-center">
          <div className="flex items-center justify-center gap-0.5 opacity-0 transition group-hover:opacity-100">
            <button
              type="button"
              disabled={isFirst}
              onClick={() => onMoveUp(node)}
              className="inline-flex rounded p-1.5 text-on-surface-variant hover:bg-surface-container disabled:opacity-30"
              aria-label="Move up"
              title="Move up"
            >
              <span className="material-symbols-outlined text-base leading-none">arrow_upward</span>
            </button>
            <button
              type="button"
              disabled={isLast}
              onClick={() => onMoveDown(node)}
              className="inline-flex rounded p-1.5 text-on-surface-variant hover:bg-surface-container disabled:opacity-30"
              aria-label="Move down"
              title="Move down"
            >
              <span className="material-symbols-outlined text-base leading-none">arrow_downward</span>
            </button>
            <button
              type="button"
              onClick={() => onAddChild(node.id)}
              className="inline-flex rounded p-1.5 text-on-surface-variant hover:bg-surface-container"
              aria-label="Add child"
              title="Add child"
            >
              <span className="material-symbols-outlined text-base leading-none">add</span>
            </button>
            <button
              type="button"
              onClick={() => onEdit(node)}
              className="inline-flex rounded p-1.5 text-on-surface-variant hover:bg-surface-container"
              aria-label="Edit"
              title="Edit"
            >
              <span className="material-symbols-outlined text-base leading-none">edit</span>
            </button>
            <button
              type="button"
              onClick={() => onDelete(node)}
              className="inline-flex rounded p-1.5 text-error hover:bg-error/10"
              aria-label="Delete"
              title="Delete"
            >
              <span className="material-symbols-outlined text-base leading-none">delete</span>
            </button>
          </div>
        </td>
      </tr>
      {expanded &&
        node.children.map((child, idx) => (
          <CategoryRow
            key={child.id}
            node={child}
            depth={depth + 1}
            allFlat={allFlat}
            onEdit={onEdit}
            onAddChild={onAddChild}
            onDelete={onDelete}
            onMoveUp={onMoveUp}
            onMoveDown={onMoveDown}
            isFirst={idx === 0}
            isLast={idx === node.children.length - 1}
          />
        ))}
    </>
  );
}

// ─── CategoryFormModal ────────────────────────────────────────────────────────

function CategoryFormModal({
  mode,
  initial,
  allFlat,
  onClose,
  onSaved,
}: {
  mode: "create" | "edit";
  initial: Partial<Category> & { parent_id?: string | null };
  allFlat: Category[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(initial.name ?? "");
  const [slug, setSlug] = useState(initial.slug ?? "");
  const [description, setDescription] = useState(initial.description ?? "");
  const [parentId, setParentId] = useState<string>(initial.parent_id ?? "");
  const [sortOrder, setSortOrder] = useState(String(initial.sort_order ?? 0));
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const parentOptions = [
    { value: "", label: "— None (root) —" },
    ...allFlat
      .filter((c) => c.id !== initial.id)
      .map((c) => ({ value: c.id, label: c.name })),
  ];

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setErr(null);
    const body: Record<string, unknown> = {
      name: name.trim(),
      description: description.trim() || null,
      parent_id: parentId || null,
      sort_order: parseInt(sortOrder, 10) || 0,
    };
    if (slug.trim()) body.slug = slug.trim();

    const url =
      mode === "create"
        ? "/api/ims/v1/admin/categories"
        : `/api/ims/v1/admin/categories/${initial.id}`;
    const method = mode === "create" ? "POST" : "PATCH";
    try {
      const r = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (r.ok) {
        onSaved();
      } else {
        const d = await r.json().catch(() => ({})) as { detail?: string };
        setErr(d.detail ?? `Failed (${r.status})`);
      }
    } catch {
      setErr("Network error. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-2xl bg-surface shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="ink-gradient rounded-t-2xl px-6 py-5">
          <p className="text-xs font-bold uppercase tracking-widest text-on-primary/80">
            {mode === "create" ? "New category" : "Edit category"}
          </p>
          <p className="mt-1 font-headline text-xl font-extrabold text-on-primary">
            {mode === "create" ? "Create category" : initial.name ?? ""}
          </p>
        </div>
        <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4 p-6">
          <label className="block text-sm font-medium text-on-surface">
            Name
            <TextInput
              required
              className="mt-1"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Stickers"
            />
          </label>
          <label className="block text-sm font-medium text-on-surface">
            Slug
            <TextInput
              className="mt-1"
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              placeholder="auto-generated if blank"
            />
          </label>
          <label className="block text-sm font-medium text-on-surface">
            Description
            <TextInput
              className="mt-1"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional short description"
            />
          </label>
          <label className="block text-sm font-medium text-on-surface">
            Parent category
            <SelectInput
              className="mt-1"
              value={parentId}
              onChange={setParentId}
              options={parentOptions}
            />
          </label>
          <label className="block text-sm font-medium text-on-surface">
            Sort order
            <TextInput
              type="number"
              min="0"
              step="1"
              className="mt-1"
              value={sortOrder}
              onChange={(e) => setSortOrder(e.target.value)}
            />
          </label>
          {err && <p className="text-sm text-error">{err}</p>}
          <div className="flex gap-2 pt-2">
            <PrimaryButton type="submit" disabled={saving}>
              {saving ? "Saving…" : mode === "create" ? "Create" : "Save changes"}
            </PrimaryButton>
            <SecondaryButton type="button" onClick={onClose}>
              Cancel
            </SecondaryButton>
          </div>
        </form>
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function CategoriesPage() {
  const [flat, setFlat] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  // Modal state
  const [formModal, setFormModal] = useState<{
    mode: "create" | "edit";
    initial: Partial<Category> & { parent_id?: string | null };
  } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const r = await fetch("/api/ims/v1/admin/categories");
      if (r.ok) {
        setFlat((await r.json()) as Category[]);
      } else {
        setErr(`Failed to load categories (${r.status})`);
      }
    } catch {
      setErr("Network error. Could not load categories.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleDelete(cat: Category) {
    if (
      !confirm(
        `Delete "${cat.name}"? Child categories will become root-level categories.`
      )
    )
      return;
    try {
      const r = await fetch(`/api/ims/v1/admin/categories/${cat.id}`, {
        method: "DELETE",
      });
      if (r.ok) {
        void load();
      } else {
        const d = await r.json().catch(() => ({})) as { detail?: string };
        alert(d.detail ?? `Delete failed (${r.status})`);
      }
    } catch {
      alert("Network error. Could not delete category.");
    }
  }

  async function handleMoveUp(cat: Category) {
    const siblings = flat
      .filter((c) => c.parent_id === cat.parent_id)
      .sort((a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name));
    const idx = siblings.findIndex((s) => s.id === cat.id);
    if (idx <= 0) return;
    const prev = siblings[idx - 1];
    await reorder([
      { id: cat.id, sort_order: prev.sort_order },
      { id: prev.id, sort_order: cat.sort_order },
    ]);
  }

  async function handleMoveDown(cat: Category) {
    const siblings = flat
      .filter((c) => c.parent_id === cat.parent_id)
      .sort((a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name));
    const idx = siblings.findIndex((s) => s.id === cat.id);
    if (idx < 0 || idx >= siblings.length - 1) return;
    const next = siblings[idx + 1];
    await reorder([
      { id: cat.id, sort_order: next.sort_order },
      { id: next.id, sort_order: cat.sort_order },
    ]);
  }

  async function reorder(items: { id: string; sort_order: number }[]) {
    try {
      const r = await fetch("/api/ims/v1/admin/categories/reorder", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items }),
      });
      if (r.ok) {
        void load();
      } else {
        alert("Reorder failed.");
      }
    } catch {
      alert("Network error. Could not reorder.");
    }
  }

  const tree = buildTree(flat);

  // Flatten tree in order so we know first/last per sibling group
  function renderTree(nodes: CategoryNode[], depth: number) {
    return nodes.map((node, idx) => (
      <CategoryRow
        key={node.id}
        node={node}
        depth={depth}
        allFlat={flat}
        onEdit={(cat) => setFormModal({ mode: "edit", initial: cat })}
        onAddChild={(parentId) =>
          setFormModal({
            mode: "create",
            initial: { parent_id: parentId, sort_order: 0 },
          })
        }
        onDelete={handleDelete}
        onMoveUp={handleMoveUp}
        onMoveDown={handleMoveDown}
        isFirst={idx === 0}
        isLast={idx === nodes.length - 1}
      />
    ));
  }

  return (
    <div className="space-y-8">
      <PageHeader
        kicker="Catalog"
        title="Categories"
        subtitle="Organise products into a hierarchy. Each product can belong to multiple categories."
        action={
          <PrimaryButton
            type="button"
            onClick={() =>
              setFormModal({ mode: "create", initial: { parent_id: null, sort_order: 0 } })
            }
          >
            <span className="material-symbols-outlined text-lg">add</span>
            Add root category
          </PrimaryButton>
        }
      />

      <Panel
        title="Category tree"
        subtitle={`${flat.length} ${flat.length === 1 ? "category" : "categories"}`}
        noPad
      >
        {loading ? (
          <div className="px-6 py-8 text-sm text-on-surface-variant">Loading categories…</div>
        ) : err ? (
          <div className="px-6 py-4 text-sm text-error">{err}</div>
        ) : flat.length === 0 ? (
          <EmptyState
            title="No categories yet"
            detail="Create your first category using the button above."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead>
                <tr className="border-b border-outline-variant/10">
                  <th className="px-4 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">
                    Name / Slug
                  </th>
                  <th className="px-4 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">
                    Description
                  </th>
                  <th className="px-4 py-3 text-center text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">
                    Order
                  </th>
                  <th className="px-4 py-3 text-center text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant/10">
                {renderTree(tree, 0)}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      {formModal && (
        <CategoryFormModal
          mode={formModal.mode}
          initial={formModal.initial}
          allFlat={flat}
          onClose={() => setFormModal(null)}
          onSaved={() => {
            setFormModal(null);
            void load();
          }}
        />
      )}
    </div>
  );
}
