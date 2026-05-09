import Link from "next/link";

export interface ChecklistItem {
  key: string;
  label: string;
  detail: string;
  href: string;
  icon: string;
  done: boolean;
}

interface Props {
  items: ChecklistItem[];
  tenantPrefix: string;
}

export function SetupChecklist({ items, tenantPrefix }: Props) {
  const doneCount = items.filter((i) => i.done).length;
  const total = items.length;

  return (
    <div className="rounded-2xl border border-primary/20 bg-primary/5 p-6">
      <div className="mb-5 flex items-center justify-between">
        <div>
          <h2 className="font-headline text-lg font-bold text-on-surface">Get started</h2>
          <p className="mt-0.5 text-xs text-on-surface-variant">
            {doneCount} of {total} steps complete
          </p>
        </div>
        {/* Progress bar */}
        <div className="flex h-2 w-32 overflow-hidden rounded-full bg-outline-variant/20">
          <div
            className="h-full rounded-full bg-primary transition-all"
            style={{ width: `${(doneCount / total) * 100}%` }}
          />
        </div>
      </div>

      <div className="space-y-2">
        {items.map((item) => (
          <div
            key={item.key}
            className={`flex items-center gap-4 rounded-xl px-4 py-3 transition-colors ${
              item.done
                ? "opacity-50"
                : "bg-surface-container-lowest shadow-sm"
            }`}
          >
            {/* Icon */}
            <span
              className={`material-symbols-outlined text-[22px] shrink-0 ${
                item.done ? "text-on-surface-variant" : "text-primary"
              }`}
              aria-hidden="true"
            >
              {item.done ? "check_circle" : item.icon}
            </span>

            {/* Text */}
            <div className="min-w-0 flex-1">
              <p className={`text-sm font-semibold ${item.done ? "text-on-surface-variant line-through" : "text-on-surface"}`}>
                {item.label}
              </p>
              <p className="mt-0.5 text-xs text-on-surface-variant">{item.detail}</p>
            </div>

            {/* Action */}
            {!item.done && (
              <Link
                href={`${tenantPrefix}${item.href}`}
                className="shrink-0 rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-on-primary hover:opacity-90"
              >
                Start →
              </Link>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
