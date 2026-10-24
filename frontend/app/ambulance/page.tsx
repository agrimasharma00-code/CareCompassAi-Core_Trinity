"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { API_BASE_URL } from "../../lib/api";

type Alert = { id: string; patient_name: string; summary: string; red_flags: string[]; latitude: number; longitude: number; status: string; created_at: string };

export default function AmbulanceDashboard() {
  const [alerts, setAlerts] = useState<Alert[]>([]); const [notice, setNotice] = useState("");
  const refresh = () => void fetch(`${API_BASE_URL}/api/v1/alerts`).then((response) => response.json()).then(setAlerts).catch(() => setNotice("Could not load the demo dispatch feed."));
  useEffect(() => { refresh(); const socket = new WebSocket(`${API_BASE_URL.replace(/^http/, "ws")}/api/v1/ws/dispatch`); socket.onmessage = refresh; return () => socket.close(); }, []);
  async function update(id: string, status: string) { const response = await fetch(`${API_BASE_URL}/api/v1/alerts/${id}/status`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }) }); if (!response.ok) { setNotice("Could not update the alert."); return; } setNotice(`${id} marked ${status}.`); refresh(); }
  return <main className="container" style={{ padding: "24px 0 64px" }}>
    <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, flexWrap: "wrap" }}><Link href="/" style={{ color: "var(--teal)", textDecoration: "none", fontWeight: 700 }}>← Niramaya AI</Link><Link href="/login/ambulance" className="button" style={{ textDecoration: "none" }}>Switch account</Link></header>
    <section style={{ marginTop: 40 }}><span className="eyebrow">Ambulance partner dashboard</span><h1 style={{ fontSize: "clamp(36px, 6vw, 58px)", margin: "10px 0" }}>Keep emergency response moving.</h1><p className="muted" style={{ fontSize: 18 }}>Demo dispatch supplements the family&apos;s call. The patient is always told to call 5555 first.</p></section>
    <section className="grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", marginTop: 28 }}>{[[String(alerts.length), "Live demo alerts"], [String(alerts.filter((alert) => alert.status === "new").length), "Awaiting acceptance"], [String(alerts.filter((alert) => alert.status === "en_route").length), "En route"], ["5555", "Call-first emergency rule"]].map(([value, label]) => <article className="card" key={label} style={{ padding: 20 }}><strong style={{ fontSize: 30 }}>{value}</strong><p className="muted" style={{ marginBottom: 0 }}>{label}</p></article>)}</section>
    <section className="card" style={{ padding: 24, marginTop: 24 }}><span className="eyebrow">Live emergency alerts</span><h2 style={{ margin: "7px 0 0", fontSize: 27 }}>Dispatch queue</h2>{alerts.length === 0 ? <p className="muted">No demo alerts. An emergency in the patient re-triage check-in will appear here.</p> : <div style={{ marginTop: 18, display: "grid", gap: 12 }}>{alerts.map((alert) => <article key={alert.id} style={{ border: "1px solid #f0c9c9", borderRadius: 14, padding: 16, background: "#fffafa" }}><div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}><strong>{alert.id} · {alert.patient_name}</strong><span className="pill">{alert.status}</span></div><p>{alert.summary}</p><p className="muted" style={{ fontSize: 13 }}>Red flags: {alert.red_flags.join(", ") || "not supplied"} · Demo map pin: {alert.latitude.toFixed(4)}, {alert.longitude.toFixed(4)}</p><div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}><button className="button" onClick={() => update(alert.id, "accepted")}>Accept</button><button className="button" onClick={() => update(alert.id, "en_route")}>En route</button><button className="button" style={{ background: "#e7f5f2", color: "var(--teal)" }} onClick={() => update(alert.id, "arrived")}>Arrived</button></div></article>)}</div>}</section>{notice && <p className="pill" style={{ marginTop: 16 }}>{notice}</p>}
  </main>;
}
