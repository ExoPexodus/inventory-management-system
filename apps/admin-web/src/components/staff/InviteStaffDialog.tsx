"use client";

import { useMemo, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { PrimaryButton, SecondaryButton, SelectInput, TextInput } from "@/components/ui/primitives";

type Shop = { id: string; name: string };

type EmployeeRecord = {
  id: string;
  name: string;
  email: string;
  phone: string | null;
  position: string;
  credential_type: "pin" | "password";
  shop_id: string;
};

type InviteResponse = {
  employee_id: string;
  method: "qr" | "email";
  expires_at: string;
  enrollment_token?: string | null;
  qr_payload?: Record<string, unknown> | null;
  email_sent: boolean;
};

type Props = {
  open: boolean;
  shops: Shop[];
  emailConfigured: boolean;
  onClose: () => void;
  onCreated: () => Promise<void> | void;
};

const POSITION_OPTIONS = [
  { value: "cashier", label: "Cashier" },
  { value: "floor_manager", label: "Floor manager" },
  { value: "stock_clerk", label: "Stock clerk" },
  { value: "supervisor", label: "Supervisor" },
];

export function InviteStaffDialog({ open, shops, emailConfigured, onClose, onCreated }: Props) {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [position, setPosition] = useState("cashier");
  const [credentialType, setCredentialType] = useState<"pin" | "password">("pin");
  const [credential, setCredential] = useState("");
  const [shopId, setShopId] = useState("");
  const [inviteMethod, setInviteMethod] = useState<"qr" | "email">("qr");

  const [employee, setEmployee] = useState<EmployeeRecord | null>(null);
  const [invite, setInvite] = useState<InviteResponse | null>(null);

  const canSkipShopStep = shops.length === 1;
  const selectedShopId = useMemo(() => {
    if (canSkipShopStep) return shops[0]?.id ?? "";
    return shopId;
  }, [canSkipShopStep, shopId, shops]);

  function resetDialog() {
    setStep(1);
    setBusy(false);
    setError(null);
    setName("");
    setEmail("");
    setPhone("");
    setPosition("cashier");
    setCredentialType("pin");
    setCredential("");
    setShopId("");
    setInviteMethod("qr");
    setEmployee(null);
    setInvite(null);
  }

  function close() {
    resetDialog();
    onClose();
  }

  async function createEmployee() {
    setBusy(true);
    setError(null);
    try {
      const payload = {
        name,
        email,
        phone: phone.trim() || null,
        position,
        credential_type: credentialType,
        initial_credential: credential,
        shop_id: selectedShopId || undefined,
      };
      const res = await fetch("/api/ims/v1/admin/employees", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const body = await res.text();
        throw new Error(body || "Failed to create employee");
      }
      const created = (await res.json()) as EmployeeRecord;
      setEmployee(created);
      await onCreated();
      setStep(3);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create employee");
    } finally {
      setBusy(false);
    }
  }

  async function sendInvite() {
    if (!employee) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/ims/v1/admin/employees/${employee.id}/invite`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ method: inviteMethod }),
      });
      if (!res.ok) {
        const body = await res.text();
        throw new Error(body || "Failed to send invite");
      }
      const data = (await res.json()) as InviteResponse;
      setInvite(data);
      await onCreated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to send invite");
    } finally {
      setBusy(false);
    }
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4">
      <div className="w-full max-w-2xl rounded-xl border border-outline-variant/20 bg-surface-container-lowest shadow-2xl">
        <div className="border-b border-outline-variant/15 px-6 py-4">
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Invite staff</p>
          <h3 className="mt-1 font-headline text-xl font-bold text-on-surface">Employee onboarding</h3>
        </div>

        <div className="space-y-4 p-6">
          {step === 1 ? (
            <>
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <label className="mb-1 block text-xs font-semibold uppercase tracking-widest text-on-surface-variant">Name</label>
                  <TextInput value={name} onChange={(e) => setName(e.target.value)} placeholder="Full name" />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-semibold uppercase tracking-widest text-on-surface-variant">Email</label>
                  <TextInput value={email} onChange={(e) => setEmail(e.target.value)} type="email" placeholder="name@shop.com" />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-semibold uppercase tracking-widest text-on-surface-variant">Phone</label>
                  <TextInput value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+1 000 000 0000" />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-semibold uppercase tracking-widest text-on-surface-variant">Position</label>
                  <SelectInput options={POSITION_OPTIONS} value={position} onChange={setPosition} />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-semibold uppercase tracking-widest text-on-surface-variant">Credential type</label>
                  <SelectInput
                    options={[
                      { value: "pin", label: "PIN" },
                      { value: "password", label: "Password" },
                    ]}
                    value={credentialType}
                    onChange={(value) => setCredentialType(value as "pin" | "password")}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-semibold uppercase tracking-widest text-on-surface-variant">
                    Initial {credentialType === "pin" ? "PIN" : "password"}
                  </label>
                  <TextInput
                    value={credential}
                    onChange={(e) => setCredential(e.target.value)}
                    type={credentialType === "pin" ? "password" : "text"}
                    placeholder={credentialType === "pin" ? "4-6 digits" : "Temporary password"}
                  />
                </div>
              </div>
              <div className="flex justify-end">
                <PrimaryButton
                  type="button"
                  disabled={!name.trim() || !email.trim() || !credential.trim()}
                  onClick={() => setStep(canSkipShopStep ? 3 : 2)}
                >
                  Continue
                </PrimaryButton>
              </div>
            </>
          ) : null}

          {step === 2 ? (
            <>
              <label className="mb-1 block text-xs font-semibold uppercase tracking-widest text-on-surface-variant">Assign shop</label>
              <SelectInput
                options={shops.map((shop) => ({ value: shop.id, label: shop.name }))}
                value={shopId}
                onChange={setShopId}
                placeholder="Select shop"
              />
              <div className="flex justify-between">
                <SecondaryButton type="button" onClick={() => setStep(1)}>
                  Back
                </SecondaryButton>
                <PrimaryButton type="button" disabled={!shopId} onClick={() => void createEmployee()}>
                  {busy ? "Creating..." : "Create employee"}
                </PrimaryButton>
              </div>
            </>
          ) : null}

          {step === 3 ? (
            <>
              {!employee ? (
                <div className="flex justify-between">
                  <SecondaryButton type="button" onClick={() => setStep(canSkipShopStep ? 1 : 2)}>
                    Back
                  </SecondaryButton>
                  <PrimaryButton type="button" disabled={busy} onClick={() => void createEmployee()}>
                    {busy ? "Creating..." : "Create employee"}
                  </PrimaryButton>
                </div>
              ) : (
                <>
                  <p className="text-sm text-on-surface-variant">
                    Choose how to send onboarding for <span className="font-semibold text-on-surface">{employee.name}</span>.
                  </p>
                  <SelectInput
                    options={[
                      { value: "qr", label: "Show QR code now" },
                      { value: "email", label: "Send by email" },
                    ]}
                    value={inviteMethod}
                    onChange={(value) => setInviteMethod(value as "qr" | "email")}
                  />
                  {inviteMethod === "email" && !emailConfigured ? (
                    <p className="rounded-lg border border-error/20 bg-error-container/20 px-3 py-2 text-sm text-on-error-container">
                      Email is not configured in tenant settings yet.
                    </p>
                  ) : null}
                  <div className="flex justify-between">
                    <SecondaryButton type="button" onClick={close}>
                      Close
                    </SecondaryButton>
                    <PrimaryButton
                      type="button"
                      disabled={busy || (inviteMethod === "email" && !emailConfigured)}
                      onClick={() => void sendInvite()}
                    >
                      {busy ? "Sending..." : inviteMethod === "qr" ? "Generate QR" : "Send invite email"}
                    </PrimaryButton>
                  </div>
                </>
              )}

              {invite?.qr_payload ? (
                <div className="rounded-xl border border-outline-variant/15 bg-surface-container p-4">
                  <p className="text-sm font-semibold text-on-surface">Scan this from cashier app</p>
                  <div className="mt-3 flex items-center gap-4">
                    <div className="rounded-lg bg-white p-2">
                      <QRCodeSVG value={JSON.stringify(invite.qr_payload)} size={168} />
                    </div>
                    <div className="space-y-2 text-xs text-on-surface-variant">
                      <p>
                        Token expires at <span className="font-semibold text-on-surface">{new Date(invite.expires_at).toLocaleString()}</span>
                      </p>
                      {invite.enrollment_token ? <p className="break-all">Token: {invite.enrollment_token}</p> : null}
                    </div>
                  </div>
                </div>
              ) : null}
              {invite?.email_sent ? (
                <p className="rounded-lg border border-primary/20 bg-primary/5 px-3 py-2 text-sm text-primary">Invite email sent successfully.</p>
              ) : null}
            </>
          ) : null}

          {error ? <p className="rounded-lg border border-error/20 bg-error-container/20 px-3 py-2 text-sm text-on-error-container">{error}</p> : null}
        </div>

        <div className="flex justify-end border-t border-outline-variant/15 px-6 py-4">
          <SecondaryButton type="button" onClick={close}>
            Cancel
          </SecondaryButton>
        </div>
      </div>
    </div>
  );
}
