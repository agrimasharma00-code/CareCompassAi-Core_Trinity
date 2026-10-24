"use client";

import { FormEvent, useRef, useState } from "react";

type Caregiver = { caregiver_id: string; score: number; reason: string };
type CareResult = { follow_up_question: string | null; care_type: string | null; urgency: string | null; red_flags: string[]; reasoning: string; matched_caregivers: Caregiver[] };
const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const title = (value: string | null) => value?.replaceAll("_", " ") ?? "";

export default function PatientPage() {
  const [input, setInput] = useState("");
  const [result, setResult] = useState<CareResult | null>(null);
  const [state, setState] = useState("");
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const contextRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);

  async function requestCare(text: string) {
    setBusy(true); setState("");
    try {
      const response = await fetch(`${API}/api/v1/care/intake-triage-match`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ user_input: text, language: "auto", location: { lat: 28.545, lng: 77.192 }, conversation_history: [] }) });
      if (!response.ok) throw new Error("CareCompass could not route that request.");
      const route: CareResult = await response.json(); setResult(route); setInput("");
      const textToSpeak = route.follow_up_question ?? route.reasoning;
      void fetch(`${API}/api/v1/voice/speak`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: textToSpeak, language_code: "en-IN" }) })
        .then((reply) => reply.json()).then((voice: { audio_base64?: string; audio_mime_type?: string }) => {
          if (voice.audio_base64 && voice.audio_mime_type) new Audio(`data:${voice.audio_mime_type};base64,${voice.audio_base64}`).play();
        }).catch(() => undefined);
    } catch (error) { setState(error instanceof Error ? error.message : "Please try again."); } finally { setBusy(false); }
  }
  async function sendText(event: FormEvent) { event.preventDefault(); if (input.trim() && !busy) await requestCare(input); }
  function stopVoice() {
    processorRef.current?.disconnect(); contextRef.current?.close(); streamRef.current?.getTracks().forEach((track) => track.stop());
    socketRef.current?.send("end"); socketRef.current?.close(); setListening(false); setState("Voice session ended.");
  }
  async function voice() {
    if (listening) { stopVoice(); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
      const socket = new WebSocket(`${API.replace(/^http/, "ws")}/api/v1/voice/realtime`);
      socket.binaryType = "arraybuffer";
      socket.onmessage = (event) => {
        const message = JSON.parse(event.data) as { type: string; text?: string; transcript?: string; response?: CareResult; audio_base64?: string; audio_mime_type?: string; message?: string };
        if (message.type === "partial") { setInput(message.text ?? ""); setState("Listening…"); }
        if (message.type === "final" && message.response) { setInput(message.transcript ?? ""); setResult(message.response); setState("Care guidance is ready."); if (message.audio_base64 && message.audio_mime_type) new Audio(`data:${message.audio_mime_type};base64,${message.audio_base64}`).play(); }
        if (message.type === "error") { setState(message.message ?? "Voice connection failed."); stopVoice(); }
      };
      socket.onerror = () => setState("Could not connect to the Sarvam voice service.");
      socket.onopen = async () => {
        const context = new AudioContext(); const source = context.createMediaStreamSource(stream); const processor = context.createScriptProcessor(2048, 1, 1);
        processor.onaudioprocess = (event) => {
          if (socket.readyState !== WebSocket.OPEN) return;
          const input = event.inputBuffer.getChannelData(0), ratio = context.sampleRate / 16000, pcm = new Int16Array(Math.floor(input.length / ratio));
          for (let index = 0; index < pcm.length; index++) pcm[index] = Math.max(-1, Math.min(1, input[Math.floor(index * ratio)])) * 0x7fff;
          socket.send(pcm.buffer);
        };
        source.connect(processor); processor.connect(context.destination); socketRef.current = socket; streamRef.current = stream; contextRef.current = context; processorRef.current = processor; setListening(true); setState("Listening with Sarvam… tap again to stop.");
      };
    } catch { setState("Microphone access is required for voice guidance."); }
  }
  const emergency = result?.care_type === "emergency_referral";
  return <main className="min-h-screen bg-[#f5f8f7] text-slate-900"><nav className="mx-auto flex max-w-6xl items-center justify-between px-5 py-5"><div className="flex items-center gap-2 text-xl font-black"><span className="grid h-9 w-9 place-items-center rounded-xl bg-emerald-600 text-white">+</span>CareCompass</div><div className="hidden gap-6 text-sm font-bold text-slate-600 sm:flex"><button onClick={() => setState("Hospital login is the next screen.")}>Hospital login</button><button onClick={() => setState("Ambulance partner login is the next screen.")}>Ambulance partners</button></div></nav>
    <section className="mx-auto grid max-w-6xl gap-8 px-5 pb-10 pt-8 lg:grid-cols-[1.1fr_.9fr] lg:items-center lg:pt-16"><div><p className="inline-flex rounded-full bg-emerald-100 px-3 py-1 text-sm font-bold text-emerald-800">Patient care guide</p><h1 className="mt-5 max-w-2xl text-4xl font-black leading-tight tracking-tight sm:text-6xl">Care starts with <span className="text-emerald-600">one clear next step.</span></h1><p className="mt-5 max-w-xl text-lg leading-8 text-slate-600">Share what is happening in English, Hindi, or Hinglish. CareCompass helps you navigate care; it does not diagnose or prescribe.</p><button onClick={() => setResult({ follow_up_question: null, care_type: "emergency_referral", urgency: "immediate", red_flags: ["Emergency support requested"], reasoning: "For a possible emergency, call 112 now.", matched_caregivers: [] })} className="mt-7 rounded-2xl bg-red-600 px-5 py-4 font-bold text-white shadow-lg shadow-red-200">Emergency? Call 112</button></div>
      <section className="rounded-[2rem] bg-slate-950 p-6 text-white shadow-2xl shadow-slate-300"><p className="text-sm font-bold text-emerald-300">LIVE SARVAM VOICE AGENT</p><h2 className="mt-2 text-2xl font-black">How can we help today?</h2><p className="mt-2 text-slate-300">Speak naturally in Hindi, Hinglish, or English. Live transcripts appear while you speak.</p><button onClick={voice} disabled={busy} className={`mt-7 grid h-28 w-full place-items-center rounded-3xl border border-white/15 font-bold transition ${listening ? "bg-red-500" : "bg-emerald-600 hover:bg-emerald-500"}`}>{listening ? "■ Stop listening" : busy ? "Finding care…" : "● Speak your request"}</button><form onSubmit={sendText} className="mt-5"><textarea value={input} onChange={(event) => setInput(event.target.value)} placeholder="Or type here… e.g. papa ko do din se bukhar hai" rows={3} className="w-full rounded-2xl border border-slate-700 bg-slate-900 p-4 text-white placeholder:text-slate-500"/><button disabled={busy} className="mt-3 w-full rounded-xl bg-white px-4 py-3 font-bold text-slate-950 disabled:opacity-50">Get guidance</button></form></section></section>
    <section className="mx-auto max-w-6xl px-5 pb-16" aria-live="polite">{state && <p className="mb-4 rounded-xl bg-slate-200 px-4 py-3 text-sm font-semibold">{state}</p>}{emergency && <article className="rounded-3xl bg-red-700 p-7 text-white"><p className="text-xl font-black">This may need immediate care.</p><a href="tel:112" className="mt-5 inline-block rounded-xl bg-white px-6 py-4 font-black text-red-700">Call 112 now</a><p className="mt-5">{result?.reasoning}</p></article>}{result && !emergency && <article className="rounded-3xl bg-white p-6 shadow-sm ring-1 ring-slate-200"><div className="flex flex-wrap items-center gap-3"><h2 className="text-2xl font-black">{result.follow_up_question ? "One quick question" : title(result.care_type)}</h2>{result.urgency && <span className="rounded-full bg-amber-100 px-3 py-1 text-sm font-bold text-amber-800">{title(result.urgency)}</span>}</div><p className="mt-4 text-lg text-slate-700">{result.follow_up_question ?? result.reasoning}</p>{result.matched_caregivers.length > 0 && <div className="mt-5 grid gap-3 sm:grid-cols-2">{result.matched_caregivers.map((caregiver: Caregiver) => <div key={caregiver.caregiver_id} className="rounded-2xl bg-slate-50 p-4"><p className="font-bold">Caregiver {caregiver.caregiver_id}</p><p className="mt-1 text-sm text-slate-600">{caregiver.reason}</p></div>)}</div>}</article>}</section></main>;
}

