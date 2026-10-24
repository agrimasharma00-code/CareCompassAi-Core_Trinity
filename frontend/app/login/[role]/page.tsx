"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { API_BASE_URL } from "../../../lib/api";

const roles = {
  patient: { title: "Patient sign in", eyebrow: "Patient portal", target: "/patient", action: "Continue to care" },
  hospital: { title: "Hospital or clinic sign in", eyebrow: "Provider portal", target: "/hospital", action: "Open provider dashboard" },
  ambulance: { title: "Ambulance partner sign in", eyebrow: "Emergency mobility", target: "/ambulance", action: "Open fleet dashboard" },
} as const;

export default function LoginPage() {
  const router = useRouter();
  const params = useParams<{ role: string }>();
  const role = roles[params.role as keyof typeof roles] ?? roles.patient;
  const [identifier, setIdentifier] = useState(""); const [notice, setNotice] = useState(""); const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) { event.preventDefault(); setBusy(true); setNotice(""); try { const response = await fetch(`${API_BASE_URL}/api/v1/auth/demo-login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ role: params.role in roles ? params.role : "patient", identifier }) }); if (!response.ok) throw new Error("Sign-in could not be completed."); const session = await response.json(); sessionStorage.setItem("carecompass_demo_token", session.access_token); sessionStorage.setItem("carecompass_demo_role", session.role); router.push(role.target); } catch (error) { setNotice(error instanceof Error ? error.message : "Sign-in could not be completed."); } finally { setBusy(false); } }
  return <main className="container" style={{ maxWidth: 520, padding: "54px 0" }}>
    <Link href="/" style={{ color: "var(--teal)", textDecoration: "none", fontWeight: 700 }}>← Back to CareCompass</Link>
    <section className="card" style={{ marginTop: 28, padding: 28 }}>
      <span className="eyebrow">{role.eyebrow}</span><h1 style={{ fontSize: 36, margin: "10px 0" }}>{role.title}</h1>
      <p className="muted" style={{ lineHeight: 1.6 }}>Use your registered mobile number or work email to enter the right dashboard.</p>
      <form onSubmit={submit} style={{ display: "grid", gap: 14, marginTop: 24 }}>
        <label style={{ fontWeight: 700 }}>Email or mobile number<input required value={identifier} onChange={(event) => setIdentifier(event.target.value)} placeholder="name@example.com or +91…" style={{ display: "block", width: "100%", marginTop: 7, padding: 13, border: "1px solid #dce7e4", borderRadius: 12, font: "inherit" }} /></label>
        <label style={{ fontWeight: 700 }}>Password or OTP<input required type="password" placeholder="Enter password or OTP" style={{ display: "block", width: "100%", marginTop: 7, padding: 13, border: "1px solid #dce7e4", borderRadius: 12, font: "inherit" }} /></label>
        <button className="button" disabled={busy} style={{ marginTop: 5 }}>{busy ? "Signing in…" : `${role.action} →`}</button>
      </form>
      {notice && <p role="alert" style={{ color: "#a91e2a" }}>{notice}</p>}
      <p className="muted" style={{ marginBottom: 0, fontSize: 13 }}>Prototype sign-in: any non-empty credentials open the selected dashboard.</p>
    </section>
  </main>;
}
