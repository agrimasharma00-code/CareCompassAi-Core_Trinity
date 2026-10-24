import Link from "next/link";

export default function ComingSoon({ title, detail }: { title: string; detail: string }) {
  return <main className="container" style={{ maxWidth: 760, padding: "40px 0" }}><Link href="/">← CareCompass</Link><section className="card" style={{ marginTop: 28, padding: 28 }}><span className="eyebrow">DEMO MODULE</span><h1>{title}</h1><span className="pill">Coming soon</span><p className="muted">{detail}</p><Link className="button" href="/patient" style={{ display: "inline-block", textDecoration: "none" }}>Open patient assistant</Link></section></main>;
}
