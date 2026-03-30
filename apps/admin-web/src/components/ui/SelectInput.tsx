"use client";

import { KeyboardEvent as ReactKeyboardEvent, useEffect, useId, useRef, useState } from "react";

export type SelectOption = { value: string; label: string };

export type SelectInputProps = {
  options: SelectOption[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  disabled?: boolean;
  required?: boolean;
};

export function SelectInput({
  options,
  value,
  onChange,
  placeholder = "Select option",
  className,
  disabled,
}: SelectInputProps) {
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const listboxId = useId();
  const [open, setOpen] = useState(false);
  const selectedIndex = options.findIndex((option) => option.value === value);
  const [activeIndex, setActiveIndex] = useState(selectedIndex >= 0 ? selectedIndex : 0);

  useEffect(() => {
    if (selectedIndex >= 0) setActiveIndex(selectedIndex);
  }, [selectedIndex]);

  useEffect(() => {
    function handleOutsideClick(event: MouseEvent) {
      if (!wrapperRef.current) return;
      if (!wrapperRef.current.contains(event.target as Node)) setOpen(false);
    }

    function handleEscape(event: globalThis.KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }

    document.addEventListener("mousedown", handleOutsideClick);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handleOutsideClick);
      document.removeEventListener("keydown", handleEscape);
    };
  }, []);

  const selectedLabel = selectedIndex >= 0 ? options[selectedIndex]?.label : "";

  function moveActive(delta: number) {
    if (options.length === 0) return;
    setActiveIndex((prev) => {
      const next = prev + delta;
      if (next < 0) return options.length - 1;
      if (next >= options.length) return 0;
      return next;
    });
  }

  function selectAt(index: number) {
    const option = options[index];
    if (!option) return;
    onChange(option.value);
    setOpen(false);
  }

  function handleTriggerKeyDown(event: ReactKeyboardEvent<HTMLButtonElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (!open) setOpen(true);
      moveActive(1);
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) setOpen(true);
      moveActive(-1);
      return;
    }
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      setOpen((prev) => !prev);
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
      return;
    }
    if (event.key === "Tab") {
      setOpen(false);
    }
  }

  function handleListboxKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      moveActive(1);
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      moveActive(-1);
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      selectAt(activeIndex);
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
      return;
    }
    if (event.key === "Tab") {
      setOpen(false);
    }
  }

  return (
    <div ref={wrapperRef} className={`relative ${className ?? ""}`}>
      <button
        type="button"
        disabled={disabled}
        role="combobox"
        aria-expanded={open}
        aria-controls={listboxId}
        aria-haspopup="listbox"
        onClick={() => setOpen((prev) => !prev)}
        onKeyDown={handleTriggerKeyDown}
        className="ledger-input flex w-full items-center justify-between gap-2 rounded-lg border border-outline-variant/20 bg-surface-container-lowest px-3 py-2 text-left text-sm text-on-surface transition hover:border-outline-variant/40 focus:border-primary disabled:cursor-not-allowed disabled:opacity-60"
      >
        <span className={selectedLabel ? "text-on-surface" : "text-on-surface-variant/70"}>
          {selectedLabel || placeholder}
        </span>
        <span className="material-symbols-outlined text-base text-on-surface-variant" aria-hidden="true">
          expand_more
        </span>
      </button>

      {open ? (
        <div
          id={listboxId}
          role="listbox"
          tabIndex={-1}
          onKeyDown={handleListboxKeyDown}
          className="absolute left-0 z-30 mt-2 max-h-64 w-full overflow-auto rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-1 shadow-xl"
        >
          {options.length === 0 ? (
            <div className="px-3 py-2 text-sm text-on-surface-variant">No options</div>
          ) : (
            options.map((option, idx) => {
              const isSelected = option.value === value;
              const isActive = idx === activeIndex;
              return (
                <button
                  key={`${option.value}-${idx}`}
                  type="button"
                  role="option"
                  aria-selected={isSelected}
                  onMouseEnter={() => setActiveIndex(idx)}
                  onClick={() => selectAt(idx)}
                  className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm transition ${
                    isSelected
                      ? "bg-primary text-on-primary"
                      : isActive
                        ? "bg-surface-container text-on-surface"
                        : "text-on-surface hover:bg-surface-container"
                  }`}
                >
                  <span>{option.label}</span>
                  {isSelected ? (
                    <span className="material-symbols-outlined text-base" aria-hidden="true">
                      check
                    </span>
                  ) : null}
                </button>
              );
            })
          )}
        </div>
      ) : null}
    </div>
  );
}
