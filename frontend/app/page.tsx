"use client";

import { FormEvent, useState } from "react";

type Turn = { role: "user" | "assistant"; content: string };
type Caregiver = { caregiver_id: string; score: number; reason: string };
type Result = { follow_up_question: string | null; care_type: string | null; urgency: string | null; red_flags: string[]; reasoning: string; matched_caregivers: Caregiver[] };

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const pretty = (value: string | null) => value?.replaceAll("_", " ") ?? "";

export default function Home() {
  const [message, setMessage] = useState("");
  const [history, setHistory] = useState<Turn[]>([]);
  const [result, setResult] = useState<Result | null>(null);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!message.trim() || loading) return;
    const userTurn: Turn = { role: "user", content: message.trim() };
    setHistory((previous) => [...previous, userTurn]);
    setLoading(true); setToast("");
    try {
      const response = await fetch(`${API}/api/v1/care/intake-triage-match`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_input: userTurn.content, language: "auto", location: { lat: 28.545, lng: 77.192 }, conversation_history: history })
      });
      if (!response.ok) throw new Error("CareCompass could not process that request.");
      const data: Result = await response.json();
      setResult(data); setMessage("");
      if (data.follow_up_question) setHistory((previous) => [...previous, { role: "assistant", content: data.follow_up_question! }]);
    } catch (error) { setToast(error instanceof Error ? error.message : "Please try again."); }
    finally { setLoading(false); }
  }

  const emergency = result?.care_type === "emergency_referral";
  return <main className="mx-auto min-h-screen max-w-3xl px-4 py-8 sm:py-14">
    <header className="mb-8"><p className="font-semibold text-teal-700">CareCompass</p><h1 className="mt-2 text-3xl font-bold tracking-tight sm:text-4xl">Find the right kind of care.</h1><p className="mt-3 text-lg text-slate-600">Describe what is happening in English, Hindi, or Hinglish. We route care; we do not diagnose or prescribe.</p></header>
    <section className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200 sm:p-7">
      <div aria-live="polite" className="space-y-3">{history.map((turn, index) => <p key={index} className={`max-w-[88%] rounded-xl px-4 py-3 text-base ${turn.role === "user" ? "ml-auto bg-teal-700 text-white" : "bg-slate-100"}`}>{turn.content}</p>)}</div>
      <form onSubmit={submit} className="mt-5"><label htmlFor="request" className="mb-2 block text-lg font-semibold">How can CareCompass help you today?</label><textarea id="request" value={message} onChange={(event) => setMessage(event.target.value)} rows={4} placeholder="e.g. papa ko do din se bukhar hai aur khansi bhi" className="w-full rounded-xl border border-slate-300 p-3 text-base" /><button disabled={loading} className="mt-3 rounded-xl bg-teal-700 px-5 py-3 font-semibold text-white disabled:opacity-60">{loading ? "Routing…" : "Send"}</button></form>
    </section>
    {toast && <p role="status" className="mt-4 rounded-lg bg-slate-900 p-3 text-white">{toast}</p>}
    {emergency && <section className="mt-6 rounded-2xl bg-red-700 p-6 text-white"><p className="text-xl font-bold">This may need immediate care.</p><a href="tel:112" className="mt-4 inline-block rounded-xl bg-white px-6 py-4 text-lg font-bold text-red-800">Call 112</a><p className="mt-4">{result?.reasoning}</p>{result?.red_flags.map((flag) => <p key={flag} className="mt-2 font-semibold">• {flag}</p>)}</section>}
    {result && !emergency && <section className="mt-6 space-y-4"><div className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200"><div className="flex flex-wrap items-center gap-3"><h2 className="text-xl font-bold">{result.follow_up_question ? "One quick question" : pretty(result.care_type)}</h2>{result.urgency && <span className={`rounded-full px-3 py-1 text-sm font-bold ${result.urgency === "same_day" ? "bg-amber-100 text-amber-800" : "bg-emerald-100 text-emerald-800"}`}>{pretty(result.urgency)}</span>}</div><p className="mt-3 text-slate-700">{result.follow_up_question ?? result.reasoning}</p></div>{!result.follow_up_question && result.matched_caregivers.map((caregiver) => <article key={caregiver.caregiver_id} className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200"><h3 className="font-bold">Caregiver {caregiver.caregiver_id}</h3><p className="mt-1 text-sm text-slate-600">Match score: {Math.round(caregiver.score * 100)}%</p><p className="mt-3">{caregiver.reason}</p><button onClick={() => setToast("Booking request noted — booking is a prototype-only confirmation.")} className="mt-4 rounded-lg bg-teal-700 px-4 py-2 font-semibold text-white">Book</button></article>)}</section>}
  </main>;
}
