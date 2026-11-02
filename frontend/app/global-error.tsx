"use client";
import Link from "next/link";
export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <html lang="en"><body style={{ margin: 0, padding: 24, fontFamily: "Arial, sans-serif", color: "#10233A", background: "#F7FAF9" }}><main style={{ maxWidth: 520, margin: "15vh auto", padding: 28, background: "white", borderRadius: 16 }}><h1>Something went wrong</h1><p>CareCompass could not display this page.</p><button onClick={() => reset()} style={{ minHeight: 44, marginRight: 12 }}>Reload</button><Link href="/" style={{ display: "inline-flex", alignItems: "center", minHeight: 44 }}>Go home</Link></main></body></html>;
}
