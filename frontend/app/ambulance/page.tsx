import Link from "next/link";

const fleet = [["AMB-12", "Available", "Noida Sector 18", "3.2 km"], ["AMB-07", "On assignment", "Greater Kailash", "ETA 9 min"], ["AMB-21", "Available", "Saket", "5.8 km"]];

export default function AmbulanceDashboard() {
  return <main className="container" style={{ padding: "24px 0 64px" }}>
    <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, flexWrap: "wrap" }}><Link href="/" style={{ color: "var(--teal)", textDecoration: "none", fontWeight: 700 }}>← CareCompass AI</Link><Link href="/login/ambulance" className="button" style={{ textDecoration: "none" }}>Switch account</Link></header>
    <section style={{ marginTop: 40 }}><span className="eyebrow">Ambulance partner dashboard</span><h1 style={{ fontSize: "clamp(36px, 6vw, 58px)", margin: "10px 0" }}>Keep emergency response moving.</h1><p className="muted" style={{ fontSize: 18 }}>Track fleet availability and respond to verified emergency handoffs.</p></section>
    <section className="grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", marginTop: 28 }}>{[["8", "Active ambulances"], ["5", "Available now"], ["10 min", "Median arrival"], ["2", "Pending handoffs"]].map(([value, label]) => <article className="card" key={label} style={{ padding: 20 }}><strong style={{ fontSize: 30 }}>{value}</strong><p className="muted" style={{ marginBottom: 0 }}>{label}</p></article>)}</section>
    <section className="card" style={{ padding: 24, marginTop: 24 }}><div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}><div><span className="eyebrow">Fleet status</span><h2 style={{ margin: "7px 0 0", fontSize: 27 }}>Vehicles in service</h2></div><button className="button">Mark vehicle available</button></div><div style={{ marginTop: 18, display: "grid", gap: 10 }}>{fleet.map(([id, state, area, eta]) => <article key={id} style={{ display: "grid", gridTemplateColumns: "100px 1fr 1fr auto", gap: 12, alignItems: "center", border: "1px solid #e4ece9", padding: 15, borderRadius: 14 }}><strong>{id}</strong><span>{area}</span><span className="muted">{state}</span><span className="pill">{eta}</span></article>)}</div></section>
  </main>;
}
