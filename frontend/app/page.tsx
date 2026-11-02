import Link from "next/link";
import styles from "./home-visuals.module.css";

const portals = [
  { icon: "✳", title: "Get care", eyebrow: "Care navigation", description: "Describe a health concern and get a clear next step in English, Hindi, or Hinglish.", href: "/patient", action: "Start intake" },
  { icon: "☼", title: "SereneMind", eyebrow: "Wellbeing support", description: "Take a private, supportive wellbeing check-in. This is not diagnosis or therapy.", href: "/serenemind", action: "Open SereneMind" },
  { icon: "✚", title: "Provider workspace", eyebrow: "Care coordination", description: "Review and respond to demo booking requests in the provider dashboard.", href: "/login", action: "Provider login" },
  { icon: "➜", title: "Dispatch workspace", eyebrow: "Demo response", description: "Review demo alerts and update dispatch status. This is not an ambulance service.", href: "/login", action: "Dispatch login" },
];

export default function HomePage() {
  return <main>
    <header className="container" style={{ display: "flex", justifyContent: "space-between", padding: "24px 0", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
      <Link href="/" aria-label="CareCompass home" style={{ color: "inherit", textDecoration: "none", fontFamily: "Manrope", fontSize: 22, fontWeight: 800 }}>✳ CareCompass</Link>
      <nav aria-label="Main navigation" style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <Link href="/patient">Get care</Link><Link href="/login">Log in</Link>
        <a href="tel:112" className="button emergency-button" style={{ minHeight: 44, display: "inline-flex", alignItems: "center", textDecoration: "none" }}>Emergency · Call 112</a>
      </nav>
    </header>
    <section className={`container ${styles.hero}`}>
      <div className={styles.copy}>
        <span className="eyebrow">One connected care journey</span>
        <h1>Find the right next step for care.</h1>
        <p className="muted">CareCompass helps you describe a concern, understand the care options, and connect with a demo provider workflow.</p>
        <div className={styles.heartbeat} aria-label="Care navigation available"><span aria-hidden="true">♥</span><i aria-hidden="true" /><b>Care navigation, in your language</b></div>
      </div>
      <div className={styles.doctorArt} aria-hidden="true"><div className={styles.artGlow} /><img src="/illustrations/carecompass-care-team.png" alt="" /></div>
    </section>
    <section className="container" style={{ paddingBottom: 72 }}>
      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(min(245px,100%),1fr))" }}>
        {portals.map((portal) => <article className="card" key={portal.title} style={{ padding: 24, minHeight: 260, display: "flex", flexDirection: "column" }}>
          <div style={{ fontSize: 27, color: "var(--teal)" }} aria-hidden="true">{portal.icon}</div>
          <span className="eyebrow" style={{ marginTop: 18 }}>{portal.eyebrow}</span><h2 style={{ margin: "7px 0", fontSize: 24 }}>{portal.title}</h2>
          <p className="muted" style={{ lineHeight: 1.55, marginTop: 4 }}>{portal.description}</p>
          <Link href={portal.href} className="button" style={{ minHeight: 44, display: "inline-flex", alignItems: "center", textDecoration: "none", marginTop: "auto", alignSelf: "start" }}>{portal.action} →</Link>
        </article>)}
      </div>
    </section>
    <footer className="container muted" style={{ padding: "22px 0", borderTop: "1px solid #e2eae8", fontSize: 13 }}>Care guidance only · Not diagnosis or prescription · For emergencies call 112.</footer>
  </main>;
}