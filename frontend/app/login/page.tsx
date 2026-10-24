"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { API_BASE_URL } from "../../lib/api";

type DemoRole = "patient" | "dispatch" | "provider";
type LoginResponse = { access_token: string; user: { username: string; name: string; role: DemoRole; caregiver_id: string | null } };
type DemoProvider = { caregiver_id: string; name: string; role: string; area: string };
type RecentBooking = { caregiver_id: string; slot: string; state: string };

const DEMO_PASSWORD = process.env.NEXT_PUBLIC_DEMO_PASSWORD || "CareCompass-Demo-2026";
const HOME_BY_ROLE: Record<DemoRole, string> = { patient: "/patient", dispatch: "/dispatch", provider: "/provider" };

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [providerPickerOpen, setProviderPickerOpen] = useState(false);
  const [providers, setProviders] = useState<DemoProvider[]>([]);
  const [providerSearch, setProviderSearch] = useState("");
  const [recentBooking, setRecentBooking] = useState<RecentBooking | null>(null);

  async function submit(credentials: { username: string; password: string }) {
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(credentials),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Could not sign in.");
      const login = payload as LoginResponse;
      localStorage.setItem("carecompass_token", login.access_token);
      localStorage.setItem("carecompass_user", JSON.stringify(login.user));
      router.replace(HOME_BY_ROLE[login.user.role]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reach the sign-in service.");
    } finally {
      setBusy(false);
    }
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await submit({ username, password });
  }

  async function demo(role: DemoRole) {
    if (role === "provider") {
      setProviderPickerOpen(true);
      setError("");
      try {
        const [rosterResponse, token] = await Promise.all([fetch(`${API_BASE_URL}/api/v1/auth/providers`), Promise.resolve(localStorage.getItem("carecompass_token"))]);
        if (!rosterResponse.ok) throw new Error("Could not load active caregivers.");
        setProviders(await rosterResponse.json());
        if (token) {
          const userResponse = await fetch(`${API_BASE_URL}/api/v1/auth/me`, { headers: { Authorization: `Bearer ${token}` } });
          const user = userResponse.ok ? await userResponse.json() : null;
          if (user?.role === "patient") {
            const bookingResponse = await fetch(`${API_BASE_URL}/api/v1/bookings/mine`, { headers: { Authorization: `Bearer ${token}` } });
            if (bookingResponse.ok) {
              const bookings: RecentBooking[] = await bookingResponse.json();
              setRecentBooking(bookings.find((item) => item.state !== "cancelled" && item.state !== "rejected") || null);
            }
          }
        }
      } catch (err) { setError(err instanceof Error ? err.message : "Could not load caregivers."); }
      return;
    }
    const demoUser = role === "patient" ? "patient1" : "dispatch";
    setUsername(demoUser);
    setPassword(DEMO_PASSWORD);
    await submit({ username: demoUser, password: DEMO_PASSWORD });
  }

  useEffect(() => {
    const token = localStorage.getItem("carecompass_token");
    if (!token) return;
    fetch(`${API_BASE_URL}/api/v1/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then((response) => response.ok ? response.json() : Promise.reject(new Error("expired")))
      .then(async (user: LoginResponse["user"]) => {
        if (user.role !== "patient") { router.replace(HOME_BY_ROLE[user.role]); return; }
        const bookingsResponse = await fetch(`${API_BASE_URL}/api/v1/bookings/mine`, { headers: { Authorization: `Bearer ${token}` } });
        if (bookingsResponse.ok) {
          const bookings: RecentBooking[] = await bookingsResponse.json();
          setRecentBooking(bookings.find((item) => item.state !== "cancelled" && item.state !== "rejected") || null);
        }
      })
      .catch(() => {
        localStorage.removeItem("carecompass_token");
        localStorage.removeItem("carecompass_user");
      });
  }, [router]);

  return (
    <main className="container" style={{ maxWidth: 560, paddingTop: 48 }}>
      <Link href="/patient" style={{ color: "var(--teal)", textDecoration: "none", fontWeight: 700 }}>← CareCompass</Link>
      <section className="card" style={{ padding: 28, marginTop: 24 }}>
        <span className="eyebrow">DEMO ACCOUNTS</span>
        <h1 style={{ margin: "8px 0" }}>Sign in</h1>
        <p className="muted">These demo roles use synthetic accounts for judging. Intake remains available without signing in.</p>
        <form onSubmit={onSubmit} style={{ display: "grid", gap: 14 }}>
          <label>Username<input autoComplete="username" required value={username} onChange={(event) => setUsername(event.target.value)} style={{ display: "block", width: "100%", padding: 12, marginTop: 6, border: "1px solid #dce7e4", borderRadius: 10 }} /></label>
          <label>Password<input type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} style={{ display: "block", width: "100%", padding: 12, marginTop: 6, border: "1px solid #dce7e4", borderRadius: 10 }} /></label>
          {error && <p role="alert" style={{ color: "#a91e2a", margin: 0 }}>{error}</p>}
          <button className="button" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        </form>
        <hr style={{ border: 0, borderTop: "1px solid #e4ece9", margin: "22px 0" }} />
        <p style={{ fontWeight: 700, marginBottom: 10 }}>Quick demo sign-in</p>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button className="pill" disabled={busy} onClick={() => void demo("patient")}>Demo as Patient</button>
          <button className="pill" disabled={busy} onClick={() => void demo("dispatch")}>Demo as Dispatch</button>
          <button className="pill" disabled={busy} onClick={() => void demo("provider")}>Demo as Provider</button>
        </div>
        {recentBooking && !providerPickerOpen && <button type="button" className="button" style={{ marginTop: 12 }} disabled={busy} onClick={() => void submit({ username: recentBooking.caregiver_id, password: DEMO_PASSWORD })}>Open as the caregiver I just booked ({recentBooking.caregiver_id})</button>}
        {providerPickerOpen && <section aria-label="Choose demo caregiver" style={{ marginTop: 18, border: "1px solid #dce7e4", borderRadius: 14, padding: 14 }}>
          <h2 style={{ fontSize: 20, marginTop: 0 }}>Choose a caregiver account</h2>
          {recentBooking && <button type="button" className="button" disabled={busy} onClick={() => void submit({ username: recentBooking.caregiver_id, password: DEMO_PASSWORD })}>Open as the caregiver I just booked ({recentBooking.caregiver_id})</button>}
          <label style={{ display: "block", margin: "12px 0" }}>Search caregivers<input aria-label="Search caregivers" value={providerSearch} onChange={(event) => setProviderSearch(event.target.value)} placeholder="ID, name, role, or area" style={{ display: "block", width: "100%", padding: 10, marginTop: 5, border: "1px solid #dce7e4", borderRadius: 10 }} /></label>
          <div style={{ display: "grid", gap: 8, maxHeight: 300, overflowY: "auto" }}>{providers.filter((provider) => `${provider.caregiver_id} ${provider.name} ${provider.role} ${provider.area}`.toLowerCase().includes(providerSearch.toLowerCase())).map((provider) => <button key={provider.caregiver_id} type="button" className="pill" disabled={busy} onClick={() => { setUsername(provider.caregiver_id); void submit({ username: provider.caregiver_id, password: DEMO_PASSWORD }); }} style={{ justifyContent: "space-between", textAlign: "left", border: "1px solid #dce7e4", background: "white", borderRadius: 12, padding: 12 }}><strong>{provider.caregiver_id} · {provider.name}</strong><span>{provider.role} · {provider.area}</span></button>)}</div>
          {providers.length > 0 && providers.filter((provider) => `${provider.caregiver_id} ${provider.name} ${provider.role} ${provider.area}`.toLowerCase().includes(providerSearch.toLowerCase())).length === 0 && <p className="muted">No active caregivers match that search.</p>}
        </section>}
        <p className="muted" style={{ marginBottom: 0, fontSize: 13 }}>Quick buttons use the sample password from <code>NEXT_PUBLIC_DEMO_PASSWORD</code>; keep it aligned with backend <code>DEMO_PASSWORD</code>.</p>
      </section>
    </main>
  );
}
