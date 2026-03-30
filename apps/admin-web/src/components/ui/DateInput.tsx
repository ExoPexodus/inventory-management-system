"use client";

import { useEffect, useMemo, useRef, useState } from "react";

type DateInputProps = {
  value: string;
  onChange: (next: string) => void;
  className?: string;
  placeholder?: string;
  min?: string;
  max?: string;
  disabled?: boolean;
};

const WEEKDAY_HEADERS = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"];

function parseIsoDate(value: string): Date | null {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const [year, month, day] = value.split("-").map(Number);
  const candidate = new Date(year, month - 1, day, 12, 0, 0, 0);
  if (candidate.getFullYear() !== year || candidate.getMonth() !== month - 1 || candidate.getDate() !== day) return null;
  return candidate;
}

function toIsoDate(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function toDisplayDate(iso: string): string {
  const parsed = parseIsoDate(iso);
  if (!parsed) return "";
  const day = String(parsed.getDate()).padStart(2, "0");
  const month = String(parsed.getMonth() + 1).padStart(2, "0");
  const year = parsed.getFullYear();
  return `${day}-${month}-${year}`;
}

function isSameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

function monthLabel(viewDate: Date): string {
  return new Intl.DateTimeFormat(undefined, { month: "long", year: "numeric" }).format(viewDate);
}

function inBounds(day: Date, min?: string, max?: string): boolean {
  const iso = toIsoDate(day);
  if (min && iso < min) return false;
  if (max && iso > max) return false;
  return true;
}

function buildCalendar(viewDate: Date): Array<{ date: Date; inMonth: boolean }> {
  const firstOfMonth = new Date(viewDate.getFullYear(), viewDate.getMonth(), 1, 12);
  const start = new Date(firstOfMonth);
  start.setDate(firstOfMonth.getDate() - firstOfMonth.getDay());

  return Array.from({ length: 42 }).map((_, idx) => {
    const d = new Date(start);
    d.setDate(start.getDate() + idx);
    return { date: d, inMonth: d.getMonth() === viewDate.getMonth() };
  });
}

export function DateInput({
  value,
  onChange,
  className,
  placeholder = "dd-mm-yyyy",
  min,
  max,
  disabled,
}: DateInputProps) {
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const [open, setOpen] = useState(false);

  const parsedValue = useMemo(() => parseIsoDate(value), [value]);
  const today = useMemo(() => new Date(), []);
  const [viewDate, setViewDate] = useState<Date>(parsedValue ?? today);

  useEffect(() => {
    if (parsedValue) {
      setViewDate(parsedValue);
      return;
    }
    setViewDate(today);
  }, [parsedValue, today]);

  useEffect(() => {
    function handleOutsideClick(event: MouseEvent) {
      if (!wrapperRef.current) return;
      if (!wrapperRef.current.contains(event.target as Node)) setOpen(false);
    }

    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }

    document.addEventListener("mousedown", handleOutsideClick);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handleOutsideClick);
      document.removeEventListener("keydown", handleEscape);
    };
  }, []);

  const days = useMemo(() => buildCalendar(viewDate), [viewDate]);
  const displayValue = toDisplayDate(value);
  const monthTitle = monthLabel(viewDate);

  function selectDate(nextDate: Date) {
    if (!inBounds(nextDate, min, max)) return;
    onChange(toIsoDate(nextDate));
    setOpen(false);
  }

  function goToPreviousMonth() {
    setViewDate((prev) => new Date(prev.getFullYear(), prev.getMonth() - 1, 1, 12));
  }

  function goToNextMonth() {
    setViewDate((prev) => new Date(prev.getFullYear(), prev.getMonth() + 1, 1, 12));
  }

  function setToToday() {
    if (!inBounds(today, min, max)) return;
    onChange(toIsoDate(today));
    setViewDate(today);
    setOpen(false);
  }

  function clearValue() {
    onChange("");
    setOpen(false);
  }

  return (
    <div ref={wrapperRef} className={`relative ${className ?? ""}`}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((prev) => !prev)}
        className="ledger-input flex w-full items-center justify-between gap-2 rounded-lg border border-outline-variant/20 bg-surface-container-lowest px-3 py-2 text-left text-sm text-on-surface transition hover:border-outline-variant/40 disabled:cursor-not-allowed disabled:opacity-60"
      >
        <span className={displayValue ? "text-on-surface" : "text-on-surface-variant/70"}>{displayValue || placeholder}</span>
        <span className="material-symbols-outlined text-[18px] text-on-surface-variant">calendar_today</span>
      </button>

      {open ? (
        <div className="absolute left-0 z-30 mt-2 w-[17rem] rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-3 shadow-xl">
          <div className="mb-2 flex items-center justify-between">
            <button
              type="button"
              onClick={goToPreviousMonth}
              className="inline-flex h-8 w-8 items-center justify-center rounded-md text-on-surface-variant transition hover:bg-surface-container"
              aria-label="Previous month"
            >
              <span className="material-symbols-outlined text-base">chevron_left</span>
            </button>
            <p className="text-sm font-semibold text-on-surface">{monthTitle}</p>
            <button
              type="button"
              onClick={goToNextMonth}
              className="inline-flex h-8 w-8 items-center justify-center rounded-md text-on-surface-variant transition hover:bg-surface-container"
              aria-label="Next month"
            >
              <span className="material-symbols-outlined text-base">chevron_right</span>
            </button>
          </div>

          <div className="grid grid-cols-7 gap-1 text-center">
            {WEEKDAY_HEADERS.map((weekday) => (
              <span key={weekday} className="py-1 text-[11px] font-bold uppercase tracking-wide text-on-surface-variant">
                {weekday}
              </span>
            ))}
            {days.map(({ date, inMonth }) => {
              const iso = toIsoDate(date);
              const selected = parsedValue ? isSameDay(parsedValue, date) : false;
              const isToday = isSameDay(today, date);
              const enabled = inBounds(date, min, max);

              return (
                <button
                  key={iso}
                  type="button"
                  onClick={() => selectDate(date)}
                  disabled={!enabled}
                  className={`h-8 rounded-md text-sm transition ${
                    selected
                      ? "bg-primary text-on-primary"
                      : isToday
                        ? "border border-primary/40 text-primary"
                        : inMonth
                          ? "text-on-surface hover:bg-surface-container"
                          : "text-on-surface-variant/45 hover:bg-surface-container"
                  } disabled:cursor-not-allowed disabled:text-on-surface-variant/30 disabled:hover:bg-transparent`}
                >
                  {date.getDate()}
                </button>
              );
            })}
          </div>

          <div className="mt-3 flex items-center justify-between border-t border-outline-variant/20 pt-2 text-xs">
            <button type="button" onClick={clearValue} className="px-1 py-1 text-on-surface-variant transition hover:text-on-surface">
              Clear
            </button>
            <button type="button" onClick={setToToday} className="px-1 py-1 font-semibold text-primary transition hover:opacity-80">
              Today
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
