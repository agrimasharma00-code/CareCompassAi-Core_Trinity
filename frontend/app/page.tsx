import Link from "next/link";

const portals = [
  { icon: "✳", title: "Patient", eyebrow: "Care navigation", description: "Talk or type in Hindi, Hinglish, or English to find the right next care step.", href: "/login/patient", action: "Patient login" },
  { icon: "✚", title: "Hospital & clinic", eyebrow: "Provider workspace", description: "Review referred requests, availability, and care coordination in one queue.", href: "/login/hospital", action: "Provider login" },
  { icon: "➜", title: "Ambulance partner", eyebrow: "Fleet response", description: "Manage vehicle availability and emergency handoffs from CareCompass.", href: "/login/ambulance", action: "Partner login" },
];

export default function HomePage() {
  return <main>
    <header className="container" style={{ display: "flex", justifyContent: "space-between", padding: "24px 0", alignItems: "center" }}><strong style={{ fontFamily: "Manrope", fontSize: 21 }}>✳ CareCompass <span style={{ color: "var(--teal)" }}>AI</span></strong><Link href="/login/patient" className="button" style={{ textDecoration: "none" }}>Sign in →</Link></header>
    <section className="container" style={{ padding: "64px 0 42px", textAlign: "center" }}><span className="eyebrow">One connected care journey</span><h1 style={{ fontSize: "clamp(42px,7vw,76px)", lineHeight: 1.03, maxWidth: 850, margin: "22px auto" }}>The right care team, one sign-in away.</h1><p className="muted" style={{ fontSize: 19, maxWidth: 620, margin: "0 auto" }}>Choose your CareCompass workspace to continue as a patient, healthcare provider, or ambulance partner.</p></section>
    <section className="container" style={{ paddingBottom: 72 }}><div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(245px,1fr))" }}>{portals.map((portal) => <article className="card" key={portal.title} style={{ padding: 24, minHeight: 290, display: "flex", flexDirection: "column" }}><div style={{ fontSize: 27, color: "var(--teal)" }}>{portal.icon}</div><span className="eyebrow" style={{ marginTop: 22 }}>{portal.eyebrow}</span><h2 style={{ margin: "7px 0", fontSize: 25 }}>{portal.title}</h2><p className="muted" style={{ lineHeight: 1.55, marginTop: 4 }}>{portal.description}</p><Link href={portal.href} className="button" style={{ textDecoration: "none", marginTop: "auto", alignSelf: "start" }}>{portal.action} →</Link></article>)}</div></section>
    <footer className="container muted" style={{ padding: "22px 0", borderTop: "1px solid #e2eae8", fontSize: 13 }}>Care routing only · Not diagnosis or prescription · Emergency? Call 112.</footer>
  </main>;
}
