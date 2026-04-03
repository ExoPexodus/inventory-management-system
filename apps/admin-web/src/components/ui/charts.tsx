"use client";

import { useState } from "react";

// ---------------------------------------------------------------------------
// InteractiveAreaChart
// ---------------------------------------------------------------------------

interface InteractiveAreaChartProps {
  values: number[];
  /** One label per value — shown in tooltip (e.g. ISO date, "W1", "Jan") */
  labels?: string[];
  /** Format the numeric value for display. Defaults to two-decimal string. */
  formatValue?: (v: number) => string;
  className?: string;
}

export function InteractiveAreaChart({
  values,
  labels,
  formatValue,
  className,
}: InteractiveAreaChartProps) {
  const [hover, setHover] = useState<{ index: number; xPct: number } | null>(null);

  if (values.length === 0) {
    return <div className={`h-64 rounded-lg bg-surface-container ${className ?? ""}`} />;
  }

  const w = 1000;
  const h = 200;
  const max = Math.max(...values, 1);
  const step = values.length > 1 ? w / (values.length - 1) : w;

  const pts = values.map((v, i) => ({
    x: i * step,
    y: h - (v / max) * (h - 20) - 10,
    v,
  }));

  const polylinePts = pts.map((p) => `${p.x},${p.y}`).join(" ");
  const fillPts = `0,${h} ${polylinePts} ${w},${h}`;

  const hp = hover !== null ? pts[hover.index] : null;

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const xPct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const index = Math.round(xPct * (values.length - 1));
    const snappedXPct = index / Math.max(values.length - 1, 1);
    setHover({ index, xPct: snappedXPct });
  };

  const fmtVal = hover !== null
    ? ((formatValue ?? ((v) => `$${v.toFixed(2)}`))(values[hover.index]))
    : "";

  const tooltipLabel = hover !== null ? (labels?.[hover.index] ?? null) : null;

  // Tooltip shifts left when near right edge to stay in bounds
  const tooltipTranslate =
    hover !== null && hover.xPct > 0.75
      ? "-100%"
      : hover !== null && hover.xPct < 0.2
      ? "0%"
      : "-50%";

  return (
    <div
      className={`relative h-64 w-full cursor-crosshair select-none ${className ?? ""}`}
      onMouseMove={handleMouseMove}
      onMouseLeave={() => setHover(null)}
    >
      {/* Grid lines */}
      <div className="pointer-events-none absolute inset-0 flex items-end justify-between px-2 opacity-10">
        {Array.from({ length: 7 }).map((_, i) => (
          <div key={i} className="h-full w-px bg-outline" />
        ))}
      </div>

      {/* SVG chart */}
      <svg
        viewBox={`0 0 ${w} ${h}`}
        className="pointer-events-none h-full w-full overflow-visible"
        preserveAspectRatio="none"
      >
        <defs>
          <linearGradient id="iareaGradient" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#06274d" stopOpacity="0.15" />
            <stop offset="100%" stopColor="#06274d" stopOpacity="0" />
          </linearGradient>
        </defs>
        <polygon points={fillPts} fill="url(#iareaGradient)" />
        <polyline
          points={polylinePts}
          fill="none"
          stroke="#06274d"
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {hp ? (
          <>
            {/* Vertical crosshair */}
            <line
              x1={hp.x}
              y1={0}
              x2={hp.x}
              y2={h}
              stroke="#06274d"
              strokeWidth="1.5"
              strokeDasharray="5 3"
              opacity="0.35"
            />
            {/* Outer glow */}
            <circle cx={hp.x} cy={hp.y} r={10} fill="#06274d" opacity="0.12" />
            {/* Dot */}
            <circle cx={hp.x} cy={hp.y} r={5} fill="#06274d" />
          </>
        ) : null}
      </svg>

      {/* Tooltip */}
      {hover !== null ? (
        <div
          className="pointer-events-none absolute z-20 min-w-[7rem] rounded-xl border border-outline-variant/20 bg-surface-container-lowest px-3 py-2 text-xs shadow-lg"
          style={{
            left: `${hover.xPct * 100}%`,
            top: 0,
            transform: `translateX(${tooltipTranslate}) translateY(-110%)`,
          }}
        >
          <p className="whitespace-nowrap font-mono font-bold text-primary">{fmtVal}</p>
          {tooltipLabel ? (
            <p className="mt-0.5 whitespace-nowrap text-on-surface-variant">{tooltipLabel}</p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// HourlyHeatmap
// ---------------------------------------------------------------------------

interface HourBucket {
  hour: number;
  avg_gross_cents: number;
  avg_tx_count: number;
}

interface HourlyHeatmapProps {
  buckets: HourBucket[];
  formatValue?: (cents: number) => string;
}

function fmt12h(hour: number): string {
  if (hour === 0) return "12 AM";
  if (hour === 12) return "12 PM";
  return hour < 12 ? `${hour} AM` : `${hour - 12} PM`;
}

export function HourlyHeatmap({ buckets, formatValue }: HourlyHeatmapProps) {
  const [hoveredHour, setHoveredHour] = useState<number | null>(null);

  if (buckets.length === 0) {
    return <p className="text-sm text-on-surface-variant">No hourly data yet.</p>;
  }

  const maxGross = Math.max(...buckets.map((b) => b.avg_gross_cents), 1);
  const fmtGross = formatValue ?? ((c) => `$${(c / 100).toFixed(2)}`);

  return (
    <div className="space-y-2">
      <div className="flex items-end gap-0.5" style={{ height: "10rem" }}>
        {buckets.map((b) => {
          const pct = (b.avg_gross_cents / maxGross) * 100;
          const heightPct = Math.max(pct, 2);
          const opacity = b.avg_gross_cents > 0 ? 0.25 + (pct / 100) * 0.75 : 0.08;
          const isHovered = hoveredHour === b.hour;

          return (
            <div
              key={b.hour}
              className="group relative flex-1"
              onMouseEnter={() => setHoveredHour(b.hour)}
              onMouseLeave={() => setHoveredHour(null)}
            >
              {/* Tooltip */}
              {isHovered ? (
                <div
                  className="pointer-events-none absolute bottom-full left-1/2 z-20 mb-2 w-max -translate-x-1/2 rounded-xl border border-outline-variant/20 bg-surface-container-lowest px-3 py-2 text-xs shadow-lg"
                >
                  <p className="font-bold text-on-surface">{fmt12h(b.hour)}</p>
                  <p className="mt-0.5 text-on-surface-variant">
                    Avg revenue: <span className="font-mono font-semibold text-primary">{fmtGross(b.avg_gross_cents)}</span>
                  </p>
                  <p className="text-on-surface-variant">
                    Avg transactions: <span className="font-semibold text-on-surface">{b.avg_tx_count.toFixed(1)}</span>
                  </p>
                </div>
              ) : null}

              {/* Bar */}
              <div
                className="w-full rounded-t-sm bg-primary transition-all duration-150"
                style={{
                  height: `${heightPct}%`,
                  minHeight: "3px",
                  opacity: isHovered ? Math.min(opacity + 0.2, 1) : opacity,
                }}
              />
            </div>
          );
        })}
      </div>

      {/* Hour axis labels */}
      <div className="flex justify-between text-[10px] font-bold text-on-surface-variant">
        <span>12am</span>
        <span>6am</span>
        <span>12pm</span>
        <span>6pm</span>
        <span>11pm</span>
      </div>
    </div>
  );
}
