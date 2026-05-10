"use client";

import { ReactNode } from "react";
import { PrimaryButton, SecondaryButton } from "@/components/ui/primitives";

interface Props {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  submitLabel?: string;
  onSubmit: (e: React.FormEvent<HTMLFormElement>) => void | Promise<void>;
  saving?: boolean;
  error?: string | null;
  children: ReactNode;
  /** When true, disables the submit button (for client-side validation) */
  submitDisabled?: boolean;
  /** Override the modal width — defaults to max-w-lg */
  size?: "sm" | "md" | "lg" | "xl";
}

const SIZE_CLASS: Record<NonNullable<Props["size"]>, string> = {
  sm: "max-w-sm",
  md: "max-w-md",
  lg: "max-w-lg",
  xl: "max-w-2xl",
};

export function CreateModal({
  open, onClose,
  title, description,
  submitLabel = "Create",
  onSubmit, saving = false,
  error,
  children,
  submitDisabled = false,
  size = "lg",
}: Props) {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className={`w-full ${SIZE_CLASS[size]} max-h-[90vh] overflow-y-auto rounded-2xl bg-surface shadow-xl`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="border-b border-outline-variant/10 px-6 py-4">
          <h2 className="font-headline text-lg font-bold text-on-surface">{title}</h2>
          {description && (
            <p className="mt-0.5 text-sm text-on-surface-variant">{description}</p>
          )}
        </div>
        <form onSubmit={onSubmit} className="space-y-4 p-6">
          {children}
          {error && (
            <p className="rounded-lg border border-error/20 bg-error-container/20 px-3 py-2 text-sm text-on-error-container">
              {error}
            </p>
          )}
          <div className="flex justify-end gap-2 pt-2">
            <SecondaryButton type="button" onClick={onClose} disabled={saving}>
              Cancel
            </SecondaryButton>
            <PrimaryButton type="submit" disabled={saving || submitDisabled}>
              {saving ? "Saving…" : submitLabel}
            </PrimaryButton>
          </div>
        </form>
      </div>
    </div>
  );
}
