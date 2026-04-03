"use client";

import { useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { PrimaryButton, SecondaryButton, SelectInput, TextInput } from "@/components/ui/primitives";

type Employee = {
  id: string;
  name: string;
  email: string;
  credential_type: "pin" | "password";
};

type InviteResponse = {
  expires_at: string;
  enrollment_token?: string | null;
  qr_payload?: Record<string, unknown> | null;
  email_sent?: boolean;
};

type Props = {
  open: boolean;
  employee: Employee | null;
  emailConfigured: boolean;
  onClose: () => void;
  onDone: () => Promise<void> | void;
};

export function ReEnrollDialog({ open, employee, emailConfigured, onClose, onDone }: Props) {
  const [mode, setMode] = useState<"re_enroll" | "reset_credential">("re_enroll");
  const [inviteMethod, setInviteMethod] = useState<"qr" | "email">("qr");
  const [credentialType, setCredentialType] = useState<"pin" | "password">(employee?.credential_type ?? "pin");
  const [credential, setCredential] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [invite, setInvite] = useState<InviteResponse | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  function close() {
    setMode("re_enroll");
    setInviteMethod("qr");
    setCredential(employee?.credential_type ?? "pin");
    setCredentialType(employee?.credential_type ?? "pin");
    setBusy(false);
    setError(null);
    setInvite(null);
    setOk(null);
    onClose();
  }

  async function runAction() {
    if (!employee) return;
    setBusy(true);
    setError(null);
    setOk(null);
    try {
      if (mode === "re_enroll") {
        const res = await fetch(`/api/ims/v1/admin/employees/${employee.id}/re-enroll`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ method: inviteMethod }),
        });
        if (!res.ok) {
          const body = await res.text();
          throw new Error(body || "Failed to re-enroll employee");
        }
        const data = (await res.json()) as InviteResponse;
        setInvite(data);
        if (data.email_sent) setOk("Re-enrollment invite email sent.");
      } else {
        const res = await fetch(`/api/ims/v1/admin/employees/${employee.id}/reset-credentials`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ credential_type: credentialType, credential }),
        });
        if (!res.ok) {
          const body = await res.text();
          throw new Error(body || "Failed to reset credentials");
        }
        setOk("Credentials reset successfully.");
      }
      await onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy(false);
    }
  }

  if (!open || !employee) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4">
      <div className="w-full max-w-xl rounded-xl border border-outline-variant/20 bg-surface-container-lowest shadow-2xl">
        <div className="border-b border-outline-variant/15 px-6 py-4">
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Employee recovery</p>
          <h3 className="mt-1 font-headline text-xl font-bold text-on-surface">{employee.name}</h3>
        </div>

        <div className="space-y-4 p-6">
          <SelectInput
            options={[
              { value: "re_enroll", label: "Re-enroll device" },
              { value: "reset_credential", label: "Reset credentials" },
            ]}
            value={mode}
            onChange={(value) => setMode(value as "re_enroll" | "reset_credential")}
          />

          {mode === "re_enroll" ? (
            <>
              <SelectInput
                options={[
                  { value: "qr", label: "Show QR code" },
                  { value: "email", label: "Send by email" },
                ]}
                value={inviteMethod}
                onChange={(value) => setInviteMethod(value as "qr" | "email")}
              />
              {inviteMethod === "email" && !emailConfigured ? (
                <p className="rounded-lg border border-error/20 bg-error-container/20 px-3 py-2 text-sm text-on-error-container">
                  Email is not configured in tenant settings.
                </p>
              ) : null}
            </>
          ) : (
            <div className="grid gap-3">
              <SelectInput
                options={[
                  { value: "pin", label: "PIN" },
                  { value: "password", label: "Password" },
                ]}
                value={credentialType}
                onChange={(value) => setCredentialType(value as "pin" | "password")}
              />
              <TextInput
                value={credential}
                onChange={(e) => setCredential(e.target.value)}
                type={credentialType === "pin" ? "password" : "text"}
                placeholder={credentialType === "pin" ? "New numeric PIN" : "New password"}
              />
            </div>
          )}

          <div className="flex justify-between">
            <SecondaryButton type="button" onClick={close}>
              Close
            </SecondaryButton>
            <PrimaryButton
              type="button"
              disabled={
                busy ||
                (mode === "re_enroll" && inviteMethod === "email" && !emailConfigured) ||
                (mode === "reset_credential" && !credential.trim())
              }
              onClick={() => void runAction()}
            >
              {busy ? "Working..." : mode === "re_enroll" ? "Send re-enrollment" : "Reset credentials"}
            </PrimaryButton>
          </div>

          {invite?.qr_payload ? (
            <div className="rounded-xl border border-outline-variant/15 bg-surface-container p-4">
              <p className="text-sm font-semibold text-on-surface">Re-enrollment QR</p>
              <div className="mt-3 flex items-center gap-4">
                <div className="rounded-lg bg-white p-2">
                  <QRCodeSVG value={JSON.stringify(invite.qr_payload)} size={168} />
                </div>
                <div className="space-y-2 text-xs text-on-surface-variant">
                  <p>
                    Expires <span className="font-semibold text-on-surface">{new Date(invite.expires_at).toLocaleString()}</span>
                  </p>
                  {invite.enrollment_token ? <p className="break-all">Token: {invite.enrollment_token}</p> : null}
                </div>
              </div>
            </div>
          ) : null}
          {ok ? <p className="rounded-lg border border-primary/20 bg-primary/5 px-3 py-2 text-sm text-primary">{ok}</p> : null}
          {error ? <p className="rounded-lg border border-error/20 bg-error-container/20 px-3 py-2 text-sm text-on-error-container">{error}</p> : null}
        </div>
      </div>
    </div>
  );
}
