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
  const [speaking, setSpeaking] = useState(false);
  const [agentReply, setAgentReply] = useState("");
  const socketRef = useRef<WebSocket | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const contextRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const speakingRef = useRef(false);
  const agentAudioRef = useRef<HTMLAudioElement | null>(null);

  function playAgentAudio(audioBase64?: string, audioMimeType?: string, reply?: string) {
    if (!audioBase64 || !audioMimeType) { setState(reply ?? "Care guidance is ready."); return; }
    const audio = new Audio(`data:${audioMimeType};base64,${audioBase64}`);
    const finish = () => {
      if (agentAudioRef.current !== audio) return;
      agentAudioRef.current = null; speakingRef.current = false; setSpeaking(false); setState("Listening… tell me more, or tap to end.");
    };
    agentAudioRef.current?.pause(); agentAudioRef.current = audio; speakingRef.current = true; setSpeaking(true); setState("CareCompass is speaking…");
    audio.onended = finish; audio.onerror = finish;
    void audio.play().catch(() => { finish(); setState(`${reply ?? "Care guidance is ready."} Audio playback was blocked by the browser.`); });
  }

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
  function stopVoice(message = "Voice session ended.") {
    agentAudioRef.current?.pause(); agentAudioRef.current = null; speakingRef.current = false; setSpeaking(false);
    processorRef.current?.disconnect(); contextRef.current?.close(); streamRef.current?.getTracks().forEach((track) => track.stop());
    if (socketRef.current?.readyState === WebSocket.OPEN) socketRef.current.send("end");
    socketRef.current?.close(); socketRef.current = null; streamRef.current = null; contextRef.current = null; processorRef.current = null;
    setListening(false); setState(message);
  }
  async function voice() {
    if (listening) { stopVoice(); return; }
    try {
      const health = await fetch(`${API}/health`);
      if (!health.ok) throw new Error("The CareCompass backend is unavailable.");
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
      const socket = new WebSocket(`${API.replace(/^http/, "ws")}/api/v1/voice/realtime`);
      socket.binaryType = "arraybuffer";
      socketRef.current = socket;
      streamRef.current = stream;
      socket.onmessage = (event) => {
        const message = JSON.parse(event.data) as { type: string; text?: string; transcript?: string; response?: CareResult; agent_reply?: string; audio_base64?: string; audio_mime_type?: string; message?: string };
        if (message.type === "partial") { setInput(message.text ?? ""); setState("Listening…"); }
        if (message.type === "ready") playAgentAudio(message.audio_base64, message.audio_mime_type, message.text);
        if (message.type === "final" && message.response) { setInput(message.transcript ?? ""); setResult(message.response); setAgentReply(message.agent_reply ?? ""); playAgentAudio(message.audio_base64, message.audio_mime_type, message.agent_reply); }
        if (message.type === "error") stopVoice(message.message ?? "Voice connection failed.");
      };
      socket.onerror = () => stopVoice("Could not connect to the Sarvam voice service. Check that the backend is running and your Sarvam key is in .env.");
      socket.onopen = async () => {
        const context = new AudioContext(); const source = context.createMediaStreamSource(stream); const processor = context.createScriptProcessor(2048, 1, 1);
        processor.onaudioprocess = (event) => {
          if (socket.readyState !== WebSocket.OPEN || speakingRef.current) return;
          const input = event.inputBuffer.getChannelData(0), ratio = context.sampleRate / 16000, pcm = new Int16Array(Math.floor(input.length / ratio));
          for (let index = 0; index < pcm.length; index++) pcm[index] = Math.max(-1, Math.min(1, input[Math.floor(index * ratio)])) * 0x7fff;
          socket.send(pcm.buffer);
        };
        source.connect(processor); processor.connect(context.destination); contextRef.current = context; processorRef.current = processor; setListening(true); setState("Listening with Sarvam… tap again to stop.");
      };
    } catch (error) {
      const message = error instanceof Error ? error.message : "Microphone access is required for voice guidance.";
      setState(`${message} Start the backend with: cd backend; uvicorn app.main:app --reload --port 8000`);
    }
  }
  const emergency = result?.care_type === "emergency_referral";
  return <main className="min-h-screen bg-[#f5f8f7] text-slate-900"><nav className="mx-auto flex max-w-6xl items-center justify-between px-5 py-5"><div className="flex items-center gap-2 text-xl font-black"><span className="grid h-9 w-9 place-items-center rounded-xl bg-emerald-600 text-white">+</span>CareCompass</div><div className="hidden gap-6 text-sm font-bold text-slate-600 sm:flex"><button onClick={() => setState("Hospital login is the next screen.")}>Hospital login</button><button onClick={() => setState("Ambulance partner login is the next screen.")}>Ambulance partners</button></div></nav>
    <section className="mx-auto grid max-w-6xl gap-8 px-5 pb-10 pt-8 lg:grid-cols-[1.1fr_.9fr] lg:items-center lg:pt-16"><div><p className="inline-flex rounded-full bg-emerald-100 px-3 py-1 text-sm font-bold text-emerald-800">Patient care guide</p><h1 className="mt-5 max-w-2xl text-4xl font-black leading-tight tracking-tight sm:text-6xl">Care starts with <span className="text-emerald-600">one clear next step.</span></h1><p className="mt-5 max-w-xl text-lg leading-8 text-slate-600">Share what is happening in English, Hindi, or Hinglish. CareCompass helps you navigate care; it does not diagnose or prescribe.</p><button onClick={() => setResult({ follow_up_question: null, care_type: "emergency_referral", urgency: "immediate", red_flags: ["Emergency support requested"], reasoning: "For a possible emergency, call 112 now.", matched_caregivers: [] })} className="mt-7 rounded-2xl bg-red-600 px-5 py-4 font-bold text-white shadow-lg shadow-red-200">Emergency? Call 112</button></div>
      <section className="rounded-[2rem] bg-slate-950 p-6 text-white shadow-2xl shadow-slate-300"><p className="text-sm font-bold text-emerald-300">LIVE SARVAM VOICE AGENT</p><h2 className="mt-2 text-2xl font-black">How can we help today?</h2><p className="mt-2 text-slate-300">Start a hands-free conversation in Hindi, Hinglish, or English. CareCompass listens, speaks back, and recommends the next care step.</p><button onClick={voice} disabled={busy} className={`mt-7 grid h-28 w-full place-items-center rounded-3xl border border-white/15 font-bold transition ${listening ? "bg-red-500" : "bg-emerald-600 hover:bg-emerald-500"}`}>{listening ? speaking ? "● CareCompass is speaking… tap to end" : "■ End voice conversation" : busy ? "Finding care…" : "● Start voice conversation"}</button><form onSubmit={sendText} className="mt-5"><textarea value={input} onChange={(event) => setInput(event.target.value)} placeholder="Or type here… e.g. papa ko do din se bukhar hai" rows={3} className="w-full rounded-2xl border border-slate-700 bg-slate-900 p-4 text-white placeholder:text-slate-500"/><button disabled={busy} className="mt-3 w-full rounded-xl bg-white px-4 py-3 font-bold text-slate-950 disabled:opacity-50">Get guidance</button></form></section></section>
    <section className="mx-auto max-w-6xl px-5 pb-16" aria-live="polite">{state && <p className="mb-4 rounded-xl bg-slate-200 px-4 py-3 text-sm font-semibold">{state}</p>}{emergency && <article className="rounded-3xl bg-red-700 p-7 text-white"><p className="text-xl font-black">This may need immediate care.</p><a href="tel:112" className="mt-5 inline-block rounded-xl bg-white px-6 py-4 font-black text-red-700">Call 112 now</a><p className="mt-5">{agentReply || result?.reasoning}</p></article>}{result && !emergency && <article className="rounded-3xl bg-white p-6 shadow-sm ring-1 ring-slate-200"><div className="flex flex-wrap items-center gap-3"><h2 className="text-2xl font-black">{result.follow_up_question ? "One quick question" : title(result.care_type)}</h2>{result.urgency && <span className="rounded-full bg-amber-100 px-3 py-1 text-sm font-bold text-amber-800">{title(result.urgency)}</span>}</div><p className="mt-4 text-lg text-slate-700">{agentReply || result.follow_up_question || result.reasoning}</p>{result.matched_caregivers.length > 0 && <div className="mt-5 grid gap-3 sm:grid-cols-2">{result.matched_caregivers.map((caregiver: Caregiver) => <div key={caregiver.caregiver_id} className="rounded-2xl bg-slate-50 p-4"><p className="font-bold">Caregiver {caregiver.caregiver_id}</p><p className="mt-1 text-sm text-slate-600">{caregiver.reason}</p></div>)}</div>}</article>}</section></main>;
}

