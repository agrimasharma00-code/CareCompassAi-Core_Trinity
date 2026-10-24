"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { API_BASE_URL } from "../../../lib/api";

const roles = {
  patient: { title: "Patient sign in", eyebrow: "Patient portal", target: "/patient", action: "Continue to care" },
  hospital: { title: "Hospital or clinic sign in", eyebrow: "Provider portal", target: "/hospital", action: "Open provider dashboard" },
  ambulance: { title: "Ambulance partner sign in", eyebrow: "Emergency mobility", target: "/ambulance", action: "Open fleet dashboard" },
} as const;
type ProviderAccount = { caregiver_id: string; role: string; languages: string[]; skills: string[] };

export default function LoginPage() {
  const router = useRouter();
  const params = useParams<{ role: string }>();
  const role = roles[params.role as keyof typeof roles] ?? roles.patient;
  const selectedRole = params.role in roles ? params.role : "patient";
  const [identifier, setIdentifier] = useState(""); const [notice, setNotice] = useState(""); const [busy, setBusy] = useState(false); const [providers, setProviders] = useState<ProviderAccount[]>([]);
  useEffect(() => { if (selectedRole !== "hospital") return; void fetch(`${API_BASE_URL}/api/v1/auth/provider-accounts`).then((response) => response.ok ? response.json() : []).then((accounts: ProviderAccount[]) => { setProviders(accounts); if (!identifier && accounts[0]) setIdentifier(accounts[0].caregiver_id); }).catch(() => setNotice("Could not load the provider profiles.")); }, [selectedRole, identifier]);
  async function submit(event: FormEvent) { event.preventDefault(); setBusy(true); setNotice(""); try { const response = await fetch(`${API_BASE_URL}/api/v1/auth/demo-login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ role: params.role in roles ? params.role : "patient", identifier }) }); if (!response.ok) throw new Error("Sign-in could not be completed."); const session = await response.json(); sessionStorage.setItem("niramaya_demo_token", session.access_token); sessionStorage.setItem("niramaya_demo_role", session.role); router.push(role.target); } catch (error) { setNotice(error instanceof Error ? error.message : "Sign-in could not be completed."); } finally { setBusy(false); } }
  return <main className="container" style={{ maxWidth: 520, padding: "54px 0" }}>
    <Link href="/" style={{ color: "var(--teal)", textDecoration: "none", fontWeight: 700 }}>← Back to Niramaya</Link>
    <section className="card" style={{ marginTop: 28, padding: 28 }}>
      <span className="eyebrow">{role.eyebrow}</span><h1 style={{ fontSize: 36, margin: "10px 0" }}>{role.title}</h1>
      <p className="muted" style={{ lineHeight: 1.6 }}>{selectedRole === "hospital" ? "Choose a supplied caregiver profile to open the provider dashboard." : "Use a demo email or mobile number to enter the selected dashboard."}</p>
      <nav aria-label="Demo role switcher" style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 18 }}>{Object.entries(roles).map(([key, item]) => <Link key={key} href={`/login/${key}`} className="pill" style={{ textDecoration: "none", background: key === selectedRole ? "#e6f5f1" : "#f5f8f7", color: "var(--navy)" }}>{item.eyebrow}</Link>)}</nav>
      <form onSubmit={submit} style={{ display: "grid", gap: 14, marginTop: 24 }}>
        {selectedRole === "hospital" ? <label style={{ fontWeight: 700 }}>Dataset caregiver profile<select required value={identifier} onChange={(event) => setIdentifier(event.target.value)} style={{ display: "block", width: "100%", marginTop: 7, padding: 13, border: "1px solid #dce7e4", borderRadius: 12, font: "inherit" }}>{providers.map((provider) => <option key={provider.caregiver_id} value={provider.caregiver_id}>{provider.caregiver_id} · {provider.role} · {provider.languages.join(", ")}</option>)}</select></label> : <label style={{ fontWeight: 700 }}>Email or mobile number<input required value={identifier} onChange={(event) => setIdentifier(event.target.value)} placeholder="name@example.com or +91…" style={{ display: "block", width: "100%", marginTop: 7, padding: 13, border: "1px solid #dce7e4", borderRadius: 12, font: "inherit" }} /></label>}
        <button className="button" disabled={busy} style={{ marginTop: 5 }}>{busy ? "Signing in…" : `${role.action} →`}</button>
      </form>
      {notice && <p role="alert" style={{ color: "#a91e2a" }}>{notice}</p>}
      <p className="muted" style={{ marginBottom: 0, fontSize: 13 }}>Demo-only JWT access. Switch roles above; no sign-up, password reset, or clinical account is created.</p>
    </section>
  </main>;
}
