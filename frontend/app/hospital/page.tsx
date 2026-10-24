import Link from "next/link";

const requests = [["CC-204", "Same-day teleconsult", "Patient waiting", "11 min"], ["CC-198", "Home nursing referral", "Finding availability", "24 min"], ["CC-191", "Lab-result review", "Ready for assignment", "32 min"]];

export default function HospitalDashboard() {
  return <main className="container" style={{ padding: "24px 0 64px" }}>
    <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, flexWrap: "wrap" }}><Link href="/" style={{ color: "var(--teal)", textDecoration: "none", fontWeight: 700 }}>← CareCompass AI</Link><Link href="/login/hospital" className="button" style={{ textDecoration: "none" }}>Switch account</Link></header>
    <section style={{ marginTop: 40 }}><span className="eyebrow">Hospital & clinic dashboard</span><h1 style={{ fontSize: "clamp(36px, 6vw, 58px)", margin: "10px 0" }}>Care coordination at a glance.</h1><p className="muted" style={{ fontSize: 18 }}>Review incoming routed requests, capacity, and referral handoffs.</p></section>
    <section className="grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", marginTop: 28 }}>{[["12", "Requests today"], ["4", "Waiting assignment"], ["18 min", "Average response"], ["96%", "Coverage"]].map(([value, label]) => <article className="card" key={label} style={{ padding: 20 }}><strong style={{ fontSize: 30 }}>{value}</strong><p className="muted" style={{ marginBottom: 0 }}>{label}</p></article>)}</section>
    <section className="card" style={{ padding: 24, marginTop: 24 }}><div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}><div><span className="eyebrow">Live referrals</span><h2 style={{ margin: "7px 0 0", fontSize: 27 }}>Incoming care requests</h2></div><button className="button">Update capacity</button></div><div style={{ marginTop: 18, display: "grid", gap: 10 }}>{requests.map(([id, service, state, time]) => <article key={id} style={{ display: "grid", gridTemplateColumns: "minmax(95px,.55fr) 1.4fr 1fr auto", gap: 12, alignItems: "center", border: "1px solid #e4ece9", padding: 15, borderRadius: 14 }}><strong>{id}</strong><span>{service}</span><span className="muted">{state}</span><span className="pill">{time}</span></article>)}</div></section>
  </main>;
}
