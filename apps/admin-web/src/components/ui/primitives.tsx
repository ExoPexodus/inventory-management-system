import { ReactNode } from "react";

export function PageHeader({
  kicker,
  title,
  subtitle,
  action,
}: {
  kicker: string;
  title: string;
  subtitle?: string;
  action?: ReactNode;
}) {
  return (
    <header className="flex items-end justify-between gap-4">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary/45">{kicker}</p>
        <h1 className="font-display text-3xl font-semibold tracking-tight text-primary">{title}</h1>
        {subtitle ? <p className="mt-1 text-sm text-primary/70">{subtitle}</p> : null}
      </div>
      {action ? <div>{action}</div> : null}
    </header>
  );
}

export function Panel({
  title,
  subtitle,
  children,
  right,
}: {
  title?: string;
  subtitle?: string;
  children: ReactNode;
  right?: ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-primary/10 bg-white/90 shadow-sm">
      {title || right ? (
        <div className="flex items-center justify-between gap-3 border-b border-primary/10 px-5 py-3">
          <div>
            {title ? <h2 className="font-display text-sm font-semibold text-primary">{title}</h2> : null}
            {subtitle ? <p className="mt-0.5 text-xs text-primary/60">{subtitle}</p> : null}
          </div>
          {right ? <div>{right}</div> : null}
        </div>
      ) : null}
      <div className="px-5 py-4">{children}</div>
    </section>
  );
}

export function StatTile({ label, value, tone = "default" }: { label: string; value: string; tone?: "default" | "warn" }) {
  return (
    <div className={`rounded-2xl border p-5 shadow-sm ${tone === "warn" ? "border-amber-300/40 bg-amber-50/70" : "border-primary/10 bg-white/90"}`}>
      <p className="text-xs font-medium uppercase tracking-wider text-primary/55">{label}</p>
      <p className="mt-2 font-display text-2xl font-semibold tabular-nums text-primary">{value}</p>
    </div>
  );
}

export function Badge({ children, tone = "default" }: { children: ReactNode; tone?: "default" | "good" | "warn" | "danger" }) {
  const cls =
    tone === "good"
      ? "bg-emerald-500/15 text-emerald-900"
      : tone === "warn"
        ? "bg-amber-500/15 text-amber-900"
        : tone === "danger"
          ? "bg-red-500/15 text-red-900"
          : "bg-primary/10 text-primary/85";
  return <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${cls}`}>{children}</span>;
}

export function TextInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`rounded-lg border border-primary/15 bg-white px-3 py-2 text-sm outline-none ring-primary/15 focus:ring-2 ${props.className ?? ""}`} />;
}

export function SelectInput(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={`rounded-lg border border-primary/15 bg-white px-3 py-2 text-sm outline-none ring-primary/15 focus:ring-2 ${props.className ?? ""}`} />;
}

export function PrimaryButton(props: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button {...props} className={`rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white transition hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-60 ${props.className ?? ""}`} />;
}

export function SecondaryButton(props: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button {...props} className={`rounded-lg border border-primary/20 px-4 py-2 text-sm font-medium text-primary transition hover:bg-primary/5 disabled:cursor-not-allowed disabled:opacity-60 ${props.className ?? ""}`} />;
}

export function EmptyState({ title, detail }: { title: string; detail?: string }) {
  return (
    <div className="rounded-xl border border-dashed border-primary/20 bg-primary/[0.02] px-4 py-8 text-center">
      <p className="font-display text-base font-semibold text-primary/80">{title}</p>
      {detail ? <p className="mt-1 text-sm text-primary/60">{detail}</p> : null}
    </div>
  );
}

export function ErrorState({ detail }: { detail: string }) {
  return (
    <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-900">{detail}</div>
  );
}

export function LoadingRow({ colSpan = 5, label = "Loading…" }: { colSpan?: number; label?: string }) {
  return (
    <tr>
      <td colSpan={colSpan} className="px-4 py-5 text-sm text-primary/60">
        {label}
      </td>
    </tr>
  );
}
