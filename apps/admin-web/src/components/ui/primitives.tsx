import { ReactNode } from "react";
import Image from "next/image";

// ─── Page Header ─────────────────────────────────────────────────────────────

export function PageHeader({
  kicker,
  title,
  subtitle,
  action,
}: {
  kicker?: string;
  title: string;
  subtitle?: string;
  action?: ReactNode;
}) {
  return (
    <div className="mb-10 flex items-end justify-between">
      <div>
        {kicker ? <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">{kicker}</p> : null}
        <h2 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface">{title}</h2>
        {subtitle ? <p className="mt-2 font-light text-on-surface-variant">{subtitle}</p> : null}
      </div>
      {action ? <div className="flex shrink-0 items-center gap-3">{action}</div> : null}
    </div>
  );
}

// ─── Panel ───────────────────────────────────────────────────────────────────

export function Panel({
  title,
  subtitle,
  children,
  right,
  noPad,
}: {
  title?: string;
  subtitle?: string;
  children: ReactNode;
  right?: ReactNode;
  noPad?: boolean;
}) {
  return (
    <section className="overflow-hidden rounded-xl border border-outline-variant/10 bg-surface-container-lowest shadow-sm">
      {title || right ? (
        <div className="flex items-center justify-between border-b border-outline-variant/10 px-6 py-4">
          <div>
            {title ? <h3 className="font-headline text-lg font-bold text-on-surface">{title}</h3> : null}
            {subtitle ? <p className="mt-0.5 text-sm text-on-surface-variant">{subtitle}</p> : null}
          </div>
          {right ? <div>{right}</div> : null}
        </div>
      ) : null}
      <div className={noPad ? "" : "p-6"}>{children}</div>
    </section>
  );
}

// ─── Stat Tile ────────────────────────────────────────────────────────────────

export function StatTile({ label, value, tone = "default" }: { label: string; value: string; tone?: "default" | "warn" }) {
  return (
    <div className={`rounded-xl border p-6 ${tone === "warn" ? "border-error/10 bg-error-container/40" : "border-outline-variant/10 bg-surface-container-lowest"}`}>
      <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">{label}</p>
      <h3 className="mt-4 font-headline text-4xl font-extrabold tracking-tighter text-primary">{value}</h3>
    </div>
  );
}

// ─── Stat Tile with Delta ────────────────────────────────────────────────────

export function StatTileDelta({
  label,
  value,
  delta,
  tone = "default",
  icon,
}: {
  label: string;
  value: string;
  delta: string;
  tone?: "default" | "good" | "warn";
  icon?: string;
}) {
  const deltaColor =
    tone === "good" ? "text-primary" : tone === "warn" ? "text-error" : "text-primary";
  const deltaIcon =
    tone === "good" ? "trending_up" : tone === "warn" ? "trending_down" : (icon ?? "trending_up");

  return (
    <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6">
      <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">{label}</p>
      <h3 className="mt-4 font-headline text-3xl font-bold text-primary">{value}</h3>
      <div className={`mt-2 flex items-center gap-1 text-xs font-bold ${deltaColor}`}>
        <span className="material-symbols-outlined text-sm">{deltaIcon}</span>
        <span>{delta}</span>
      </div>
    </div>
  );
}

// ─── Badge ───────────────────────────────────────────────────────────────────

export function Badge({
  children,
  tone = "default",
}: {
  children: ReactNode;
  tone?: "default" | "good" | "warn" | "danger";
}) {
  const cls =
    tone === "good"
      ? "bg-tertiary-fixed text-on-tertiary-fixed-variant"
      : tone === "warn"
        ? "bg-secondary-container text-on-secondary-container"
        : tone === "danger"
          ? "bg-error-container text-on-error-container"
          : "bg-surface-container-high text-on-surface-variant";
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[10px] font-bold uppercase ${cls}`}>
      {children}
    </span>
  );
}

// ─── Text Input ───────────────────────────────────────────────────────────────

export function TextInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={`ledger-input w-full py-2 text-base font-headline text-on-surface placeholder:text-outline-variant/50 ${props.className ?? ""}`}
    />
  );
}

// ─── Select Input ─────────────────────────────────────────────────────────────

export function SelectInput(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={`ledger-input w-full py-2 text-sm text-on-surface ${props.className ?? ""}`}
    />
  );
}

// ─── Primary Button ───────────────────────────────────────────────────────────

export function PrimaryButton(props: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className={`ink-gradient inline-flex items-center gap-2 rounded-lg px-6 py-2.5 text-sm font-semibold text-on-primary shadow-sm transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60 ${props.className ?? ""}`}
    />
  );
}

// ─── Secondary Button ─────────────────────────────────────────────────────────

export function SecondaryButton(props: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className={`inline-flex items-center gap-2 rounded-lg border border-outline-variant/40 px-6 py-2.5 text-sm font-semibold text-on-surface transition hover:bg-surface-container disabled:cursor-not-allowed disabled:opacity-60 ${props.className ?? ""}`}
    />
  );
}

// ─── Empty State ──────────────────────────────────────────────────────────────

export function EmptyState({ title, detail }: { title: string; detail?: string }) {
  return (
    <div className="px-4 py-12 text-center">
      <p className="font-headline text-base font-bold text-on-surface">{title}</p>
      {detail ? <p className="mt-1 text-sm text-on-surface-variant">{detail}</p> : null}
    </div>
  );
}

// ─── Error State ──────────────────────────────────────────────────────────────

export function ErrorState({ detail }: { detail: string }) {
  return (
    <div className="rounded-xl border border-error/20 bg-error-container/30 px-4 py-3 text-sm text-on-error-container">
      {detail}
    </div>
  );
}

// ─── Loading Row ──────────────────────────────────────────────────────────────

export function LoadingRow({ colSpan = 5, label = "Loading…" }: { colSpan?: number; label?: string }) {
  return (
    <tr>
      <td colSpan={colSpan} className="px-6 py-8 text-sm text-on-surface-variant">
        {label}
      </td>
    </tr>
  );
}

// ─── Segmented Control ────────────────────────────────────────────────────────

export function SegmentedControl({
  options,
  value,
  onChange,
}: {
  options: Array<{ value: string; label: string }>;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="inline-flex rounded-lg bg-surface-container p-1">
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            className={`rounded-md px-4 py-1.5 text-xs font-semibold transition ${
              active ? "bg-surface-container-lowest text-on-surface shadow-sm" : "text-on-surface-variant"
            }`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

// ─── Mini Bar Chart ───────────────────────────────────────────────────────────

export function MiniBarChart({ points, max }: { points: number[]; max?: number }) {
  const peak = max ?? Math.max(...points, 1);
  return (
    <div className="flex h-16 items-end gap-0.5">
      {points.map((point, idx) => (
        <div
          key={idx}
          className="flex-1 rounded-sm bg-primary/80"
          style={{ height: `${Math.max(6, (point / peak) * 100)}%` }}
        />
      ))}
    </div>
  );
}

// ─── Area Chart ───────────────────────────────────────────────────────────────

export function AreaChart({ values, className }: { values: number[]; className?: string }) {
  if (values.length === 0) {
    return <div className={`h-64 rounded-lg bg-surface-container ${className ?? ""}`} />;
  }
  const w = 1000;
  const h = 200;
  const max = Math.max(...values, 1);
  const step = values.length > 1 ? w / (values.length - 1) : w;
  const pts = values
    .map((v, i) => {
      const x = i * step;
      const y = h - (v / max) * (h - 20) - 10;
      return `${x},${y}`;
    })
    .join(" ");
  const fillPts = `0,${h} ${pts} ${w},${h}`;

  return (
    <div className={`relative h-64 w-full ${className ?? ""}`}>
      <div className="absolute inset-0 flex items-end justify-between px-2 opacity-10">
        {Array.from({ length: 7 }).map((_, i) => (
          <div key={i} className="h-full w-px bg-outline" />
        ))}
      </div>
      <svg viewBox={`0 0 ${w} ${h}`} className="h-full w-full overflow-visible" preserveAspectRatio="none">
        <defs>
          <linearGradient id="areaGradient" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#06274d" stopOpacity="0.15" />
            <stop offset="100%" stopColor="#06274d" stopOpacity="0" />
          </linearGradient>
        </defs>
        <polygon points={fillPts} fill="url(#areaGradient)" />
        <polyline points={pts} fill="none" stroke="#06274d" strokeWidth="3" strokeLinecap="round" />
      </svg>
    </div>
  );
}

// ─── Progress Bar ─────────────────────────────────────────────────────────────

export function ProgressBar({ label, value, max = 100 }: { label: string; value: number; max?: number }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-sm font-semibold">
        <span className="text-on-surface">{label}</span>
        <span className="text-primary">{Math.round(pct)}%</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-container">
        <div className="ink-gradient h-full rounded-full" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

// ─── Donut Chart ──────────────────────────────────────────────────────────────

export function DonutChart({ value, label }: { value: number; label?: string }) {
  const clamped = Math.max(0, Math.min(100, value));
  const r = 40;
  const c = 2 * Math.PI * r;
  const offset = c - (clamped / 100) * c;
  return (
    <div className="relative h-28 w-28">
      <svg viewBox="0 0 100 100" className="h-28 w-28 -rotate-90">
        <circle cx="50" cy="50" r={r} className="fill-none stroke-surface-container stroke-[10]" />
        <circle cx="50" cy="50" r={r} className="fill-none stroke-primary stroke-[10]" strokeDasharray={c} strokeDashoffset={offset} />
      </svg>
      <div className="absolute inset-0 grid place-items-center text-center">
        <div>
          <span className="font-headline text-lg font-bold text-on-surface">{Math.round(clamped)}%</span>
          {label ? <p className="text-[10px] text-on-surface-variant">{label}</p> : null}
        </div>
      </div>
    </div>
  );
}

// ─── Avatar ───────────────────────────────────────────────────────────────────

export function Avatar({ name, src, className }: { name: string; src?: string | null; className?: string }) {
  const initials = name
    .split(" ")
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
  if (src) {
    return <Image src={src} alt={name} width={40} height={40} className={`rounded-full object-cover ${className ?? ""}`} />;
  }
  return (
    <div className={`grid place-items-center rounded-full bg-secondary-container text-xs font-bold text-on-secondary-container ${className ?? "h-10 w-10"}`}>
      {initials}
    </div>
  );
}

// ─── Toggle ───────────────────────────────────────────────────────────────────

export function Toggle({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative h-6 w-11 rounded-full transition ${checked ? "bg-primary" : "bg-surface-container"} ${disabled ? "cursor-not-allowed opacity-60" : ""}`}
    >
      <span
        className={`absolute top-0.5 h-5 w-5 rounded-full bg-surface-container-lowest shadow-sm transition-all ${checked ? "left-[22px]" : "left-0.5"}`}
      />
    </button>
  );
}

// ─── Tabs ─────────────────────────────────────────────────────────────────────

export function Tabs({
  tabs,
  active,
  onChange,
}: {
  tabs: Array<{ id: string; label: string }>;
  active: string;
  onChange: (id: string) => void;
}) {
  return (
    <div className="flex gap-8 border-b border-outline-variant/20">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          onClick={() => onChange(tab.id)}
          className={`pb-4 text-sm font-bold uppercase tracking-widest transition-colors ${
            active === tab.id
              ? "border-b-2 border-primary text-primary"
              : "border-b-2 border-transparent text-on-surface-variant hover:text-on-surface"
          }`}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

// ─── Tooltip ─────────────────────────────────────────────────────────────────

export function Tooltip({ label, children }: { label: string; children: ReactNode }) {
  return (
    <span className="group relative inline-flex">
      {children}
      <span className="pointer-events-none absolute -top-8 left-1/2 z-20 -translate-x-1/2 whitespace-nowrap rounded bg-on-surface px-2 py-1 text-xs text-surface-container-lowest opacity-0 transition group-hover:opacity-100">
        {label}
      </span>
    </span>
  );
}

// ─── Pagination ───────────────────────────────────────────────────────────────

export function Pagination({
  page,
  totalPages,
  onChange,
  total,
  pageSize,
}: {
  page: number;
  totalPages: number;
  onChange: (page: number) => void;
  total?: number;
  pageSize?: number;
}) {
  const visiblePages: Array<number | "..."> = [];
  if (totalPages <= 7) {
    for (let i = 1; i <= totalPages; i++) visiblePages.push(i);
  } else {
    visiblePages.push(1);
    if (page > 3) visiblePages.push("...");
    for (let i = Math.max(2, page - 1); i <= Math.min(totalPages - 1, page + 1); i++) visiblePages.push(i);
    if (page < totalPages - 2) visiblePages.push("...");
    visiblePages.push(totalPages);
  }

  return (
    <div className="flex items-center justify-between px-6 py-4 text-xs font-medium text-on-surface-variant">
      {total != null && pageSize != null ? (
        <p>Showing {Math.min((page - 1) * pageSize + 1, total)}–{Math.min(page * pageSize, total)} of {total}</p>
      ) : (
        <span />
      )}
      <div className="flex items-center gap-1">
        <button
          type="button"
          disabled={page <= 1}
          onClick={() => onChange(page - 1)}
          className="flex h-8 w-8 items-center justify-center rounded hover:bg-surface-container disabled:opacity-30"
        >
          <span className="material-symbols-outlined text-sm">chevron_left</span>
        </button>
        {visiblePages.map((p, i) =>
          p === "..." ? (
            <span key={`ellipsis-${i}`} className="px-1 text-on-surface-variant/30">...</span>
          ) : (
            <button
              key={p}
              type="button"
              onClick={() => onChange(p as number)}
              className={`flex h-8 w-8 items-center justify-center rounded text-xs font-bold transition ${
                p === page ? "bg-primary text-on-primary shadow-sm" : "text-on-surface-variant hover:bg-surface-container"
              }`}
            >
              {p}
            </button>
          )
        )}
        <button
          type="button"
          disabled={page >= totalPages}
          onClick={() => onChange(page + 1)}
          className="flex h-8 w-8 items-center justify-center rounded hover:bg-surface-container disabled:opacity-30"
        >
          <span className="material-symbols-outlined text-sm">chevron_right</span>
        </button>
      </div>
    </div>
  );
}

// ─── Timeline ─────────────────────────────────────────────────────────────────

export function Timeline({ items }: { items: Array<{ title: string; detail?: string; tone?: "default" | "warn" | "danger" }> }) {
  return (
    <ul className="space-y-6">
      {items.map((item, idx) => {
        const dotCls =
          item.tone === "warn" ? "bg-secondary" : item.tone === "danger" ? "bg-error" : "bg-primary";
        return (
          <li key={`${item.title}-${idx}`} className="flex items-start gap-4">
            <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${dotCls}`} />
            <div>
              <p className="text-sm font-bold text-on-surface">{item.title}</p>
              {item.detail ? <p className="mt-0.5 text-xs text-on-surface-variant">{item.detail}</p> : null}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

// ─── Drop Zone ────────────────────────────────────────────────────────────────

export function DropZone({
  label = "Drop high-resolution asset here",
  sublabel = "Recommended: 2000 x 2000px JPG or PNG",
  onChange,
}: {
  label?: string;
  sublabel?: string;
  onChange?: React.ChangeEventHandler<HTMLInputElement>;
}) {
  return (
    <label className="flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-outline-variant/30 bg-surface-container-lowest/40 p-12 text-center transition hover:bg-surface-container-lowest/80">
      <span className="material-symbols-outlined mb-3 text-4xl text-on-surface-variant">add_a_photo</span>
      <p className="text-sm font-medium text-on-surface">{label}</p>
      <p className="mt-1 text-xs text-on-surface-variant">{sublabel}</p>
      <input type="file" className="hidden" onChange={onChange} />
    </label>
  );
}

// ─── Breadcrumbs ──────────────────────────────────────────────────────────────

export function Breadcrumbs({ items }: { items: Array<{ label: string; href?: string }> }) {
  return (
    <nav className="mb-2 flex items-center gap-1 text-sm text-on-surface-variant">
      {items.map((item, idx) => (
        <span key={`${item.label}-${idx}`} className="inline-flex items-center gap-1">
          {item.href ? (
            <a href={item.href} className="hover:text-on-surface">{item.label}</a>
          ) : (
            <span className="font-semibold text-primary">{item.label}</span>
          )}
          {idx < items.length - 1 ? (
            <span className="material-symbols-outlined text-xs text-on-surface-variant">chevron_right</span>
          ) : null}
        </span>
      ))}
    </nav>
  );
}

// ─── Icon Button ──────────────────────────────────────────────────────────────

export function IconButton({
  icon,
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { icon: ReactNode }) {
  return (
    <button
      {...props}
      className={`inline-flex items-center gap-1 rounded-lg border border-outline-variant/40 px-3 py-2 text-xs font-medium text-on-surface transition hover:bg-surface-container ${props.className ?? ""}`}
    >
      {icon}
      {children}
    </button>
  );
}

// ─── FAB ──────────────────────────────────────────────────────────────────────

export function FAB({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className={`fixed bottom-8 right-8 flex h-16 w-16 items-center justify-center rounded-full shadow-xl transition-all hover:scale-105 ink-gradient text-on-primary ${props.className ?? ""}`}
    >
      {children}
    </button>
  );
}

// ─── Search Bar ───────────────────────────────────────────────────────────────

export function SearchBar(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <div className="relative">
      <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-lg text-on-surface-variant" aria-hidden="true">search</span>
      <input
        {...props}
        placeholder={props.placeholder ?? "Search"}
        className={`w-full rounded-full border-none bg-surface-container-low py-2 pl-10 pr-4 text-sm text-on-surface outline-none placeholder:text-on-surface-variant focus:ring-1 focus:ring-primary ${props.className ?? ""}`}
      />
    </div>
  );
}
