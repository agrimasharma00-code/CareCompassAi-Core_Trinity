import Link from "next/link";
import styles from "./home-visuals.module.css";

const portals = [
  { icon: "✳", title: "Patient", eyebrow: "Care navigation", description: "Talk or type in Hindi, Hinglish, or English to find the right next care step.", href: "/login/patient", action: "Patient login" },
  { icon: "✚", title: "Hospital & clinic", eyebrow: "Provider workspace", description: "Review referred requests, availability, and care coordination in one queue.", href: "/login/hospital", action: "Provider login" },
  { icon: "➜", title: "Ambulance partner", eyebrow: "Fleet response", description: "Manage vehicle availability and emergency handoffs from Niramaya.", href: "/login/ambulance", action: "Partner login" },
  { icon: "⌁", title: "PathoVision", eyebrow: "Visual guidance", description: "Upload a wound photo or report for safe, plain-language information and next-step guidance.", href: "/pathovision", action: "Open PathoVision" },
];

export default function HomePage() {
  return <main>
    <header className="container" style={{ display: "flex", justifyContent: "space-between", padding: "24px 0", alignItems: "center", gap: 12 }}><strong style={{ fontFamily: "Manrope", fontSize: 21 }}>✳ Niramaya</strong><div style={{ display: "flex", gap: 10, alignItems: "center" }}><Link href="/dial" style={{ color: "var(--teal)", textDecoration: "none", fontWeight: 800, fontSize: 14 }}>Dial NOVA</Link><Link href="/login/patient" className="button" style={{ textDecoration: "none" }}>Sign in →</Link></div></header>
    <section className={`container ${styles.hero}`}><div className={styles.copy}><span className="eyebrow">One connected care journey</span><h1>The right care team, one sign-in away.</h1><p className="muted">Choose your Niramaya workspace to continue as a patient, healthcare provider, or ambulance partner.</p><div className={styles.heartbeat} aria-label="Care coordination active"><span aria-hidden="true">♥</span><i aria-hidden="true" /><b>Care coordination, always within reach</b></div></div><div className={styles.doctorArt} aria-hidden="true"><div className={styles.artGlow} /><img src="/illustrations/niramaya-doctor-hero.png" alt="" /></div></section>
    <section className="container" style={{ paddingBottom: 72 }}><div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(245px,1fr))" }}>{portals.map((portal) => <article className="card" key={portal.title} style={{ padding: 24, minHeight: 290, display: "flex", flexDirection: "column" }}><div style={{ fontSize: 27, color: "var(--teal)" }}>{portal.icon}</div><span className="eyebrow" style={{ marginTop: 22 }}>{portal.eyebrow}</span><h2 style={{ margin: "7px 0", fontSize: 25 }}>{portal.title}</h2><p className="muted" style={{ lineHeight: 1.55, marginTop: 4 }}>{portal.description}</p><Link href={portal.href} className="button" style={{ textDecoration: "none", marginTop: "auto", alignSelf: "start" }}>{portal.action} →</Link></article>)}</div></section>
    <footer className="container muted" style={{ padding: "22px 0", borderTop: "1px solid #e2eae8", fontSize: 13 }}>Care routing only · Not diagnosis or prescription · Emergency? Call 5555.</footer>
  </main>;
}
