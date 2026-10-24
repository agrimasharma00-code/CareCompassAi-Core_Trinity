"use client";

import Link from "next/link";
import { FormEvent, useRef, useState } from "react";

import { API_BASE_URL } from "../../lib/api";

type Caregiver = { caregiver_id: string; score: number; reason: string };
type CareResult = { follow_up_question: string | null; care_type: string | null; urgency: string | null; red_flags: string[]; reasoning: string; matched_caregivers: Caregiver[] };
type Turn = { role: "user" | "assistant"; content: string };
type VoiceMessage = { type: string; text?: string; transcript?: string; response?: CareResult; agent_reply?: string; audio_base64?: string; audio_mime_type?: string; message?: string };

const careNames: Record<string, string> = { paramedic_home_visit: "Medic home visit", nurse: "Home nursing support", gp_teleconsult: "Virtual GP consultation", specialist: "Specialist consultation", emergency_referral: "Emergency support" };

export default function PatientPage() {
  const [input, setInput] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [result, setResult] = useState<CareResult | null>(null);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [liveTranscript, setLiveTranscript] = useState("");
  const [location, setLocation] = useState({ lat: 28.545, lng: 77.192 });
  const socketRef = useRef<WebSocket | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const contextRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<AudioNode | null>(null);
  const speakingRef = useRef(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  function playAgentAudio(audioBase64?: string, mimeType?: string, fallbackText?: string) {
    if (!audioBase64 || !mimeType) { setStatus(fallbackText ?? "Care guidance is ready."); return; }
    const audio = new Audio(`data:${mimeType};base64,${audioBase64}`);
    const finish = () => {
      if (audioRef.current !== audio) return;
      audioRef.current = null; speakingRef.current = false; setSpeaking(false);
      setStatus(socketRef.current?.readyState === WebSocket.OPEN ? "Listening — tell me more, or tap End." : "Care guidance is ready.");
    };
    audioRef.current?.pause(); audioRef.current = audio; speakingRef.current = true; setSpeaking(true); setStatus("CareCompass is speaking…");
    audio.onended = finish; audio.onerror = finish;
    void audio.play().catch(() => { finish(); setStatus(`${fallbackText ?? "Care guidance is ready."} Audio playback was blocked by the browser.`); });
  }

  function addFinalTurn(transcript: string, reply: string, response?: CareResult) {
    if (response) setResult(response);
    setTurns((previous) => [...previous, { role: "user", content: transcript }, { role: "assistant", content: reply }]);
  }

  async function sendText(event: FormEvent) {
    event.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    setBusy(true); setStatus("");
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/voice/chat`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, language: "auto", lat: location.lat, lng: location.lng, conversation_history: turns }) });
      if (!response.ok) throw new Error("CareCompass could not respond right now.");
      const message = await response.json() as { reply: string; response?: CareResult | null; audio_base64?: string; audio_mime_type?: string };
      setInput(""); addFinalTurn(text, message.reply, message.response ?? undefined);
      playAgentAudio(message.audio_base64, message.audio_mime_type, message.reply);
    } catch (error) { setStatus(error instanceof Error ? error.message : "Please try again."); }
    finally { setBusy(false); }
  }

  function stopVoice(message = "Voice session ended.") {
    audioRef.current?.pause(); audioRef.current = null; speakingRef.current = false; setSpeaking(false);
    processorRef.current?.disconnect(); void contextRef.current?.close(); streamRef.current?.getTracks().forEach((track) => track.stop());
    if (socketRef.current?.readyState === WebSocket.OPEN) socketRef.current.send("end");
    socketRef.current?.close(); socketRef.current = null; streamRef.current = null; contextRef.current = null; processorRef.current = null;
    setListening(false); setLiveTranscript(""); setStatus(message);
  }

  async function startVoice() {
    if (listening) { stopVoice(); return; }
    try {
      const health = await fetch(`${API_BASE_URL}/health`);
      if (!health.ok) throw new Error("The CareCompass backend is unavailable.");
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
      const context = new AudioContext(); await context.resume();
      const socket = new WebSocket(`${API_BASE_URL.replace(/^http/, "ws")}/api/v1/voice/realtime`);
      socket.binaryType = "arraybuffer"; socketRef.current = socket; streamRef.current = stream;
      socket.onmessage = (event) => {
        const message = JSON.parse(event.data) as VoiceMessage;
        if (message.type === "ready") {
          const greeting = message.text ?? "Hello, I am CareCompass. Tell me what is happening.";
          setTurns([{ role: "assistant", content: greeting }]);
          playAgentAudio(message.audio_base64, message.audio_mime_type, greeting);
        }
        if (message.type === "partial") { setLiveTranscript(message.text ?? ""); setStatus("Listening…"); }
        if (message.type === "final") {
          const transcript = message.transcript ?? "";
          const reply = message.agent_reply ?? message.response?.follow_up_question ?? message.response?.reasoning ?? "I am here to help.";
          if (transcript) addFinalTurn(transcript, reply, message.response);
          setLiveTranscript(""); playAgentAudio(message.audio_base64, message.audio_mime_type, reply);
        }
        if (message.type === "error") stopVoice(message.message ?? "Voice connection failed.");
      };
      socket.onerror = () => stopVoice("Could not connect to Sarvam voice. Check the backend and the Sarvam key.");
      socket.onclose = () => { if (socketRef.current === socket) stopVoice("Voice connection closed. Tap Talk to CareCompass to reconnect."); };
      socket.onopen = async () => {
        const source = context.createMediaStreamSource(stream);
        const silentOutput = context.createGain(); silentOutput.gain.value = 0;
        const sendPcm = (samples: Float32Array) => {
          if (socket.readyState !== WebSocket.OPEN || speakingRef.current) return;
          const ratio = context.sampleRate / 16000;
          const pcm = new Int16Array(Math.floor(samples.length / ratio));
          for (let i = 0; i < pcm.length; i += 1) pcm[i] = Math.max(-1, Math.min(1, samples[Math.floor(i * ratio)])) * 0x7fff;
          socket.send(pcm.buffer); setStatus("Listening…");
        };
        const legacyProcessor = () => {
          const processor = context.createScriptProcessor(2048, 1, 1);
          processor.onaudioprocess = (event) => sendPcm(event.inputBuffer.getChannelData(0));
          source.connect(processor); processor.connect(silentOutput); processorRef.current = processor;
        };
        try {
          if (!context.audioWorklet || typeof AudioWorkletNode === "undefined") throw new Error("AudioWorklet unavailable");
          const code = `class CareCompassPcm extends AudioWorkletProcessor { constructor(){super();this.buffer=new Float32Array(1600);this.offset=0;} process(inputs){const channel=inputs[0]&&inputs[0][0];if(!channel)return true;for(let i=0;i<channel.length;i+=1){this.buffer[this.offset++]=channel[i];if(this.offset===this.buffer.length){this.port.postMessage(this.buffer.slice(0));this.offset=0;}}return true;} } registerProcessor("carecompass-pcm",CareCompassPcm);`;
          const moduleUrl = URL.createObjectURL(new Blob([code], { type: "application/javascript" }));
          await context.audioWorklet.addModule(moduleUrl); URL.revokeObjectURL(moduleUrl);
          const processor = new AudioWorkletNode(context, "carecompass-pcm");
          processor.port.onmessage = (event: MessageEvent<Float32Array>) => sendPcm(event.data);
          source.connect(processor); processor.connect(silentOutput); processorRef.current = processor;
        } catch { legacyProcessor(); }
        silentOutput.connect(context.destination); contextRef.current = context; setListening(true); setStatus("Connecting to Sarvam… speak after the greeting.");
      };
    } catch (error) {
      const message = error instanceof Error ? error.message : "Microphone access is required for voice guidance.";
      setStatus(message === "Failed to fetch" ? "The browser could not reach CareCompass. Start the backend, then try again." : message);
    }
  }

  function useLocation() {
    if (!navigator.geolocation) { setStatus("Location access is unavailable. Using the default service area."); return; }
    navigator.geolocation.getCurrentPosition(
      (position) => { setLocation({ lat: position.coords.latitude, lng: position.coords.longitude }); setStatus("Location updated for care matching."); },
      () => setStatus("Location was not shared. Using the default service area."),
    );
  }

  const emergency = result?.care_type === "emergency_referral";
  return <main className="container" style={{ maxWidth: 900, padding: "24px 0 64px" }}>
    <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16 }}><Link href="/" style={{ color: "var(--teal)", textDecoration: "none", fontWeight: 700 }}>← CareCompass AI</Link><span className="pill">Sarvam-powered</span></header>
    <section style={{ marginTop: 42, maxWidth: 710 }}><span className="eyebrow">CareAgent Nexus</span><h1 style={{ fontSize: "clamp(36px, 6vw, 58px)", margin: "10px 0" }}>Let&apos;s find the right care.</h1><p className="muted" style={{ fontSize: 18, lineHeight: 1.6 }}>Speak or type in English, Hindi, or Hinglish. CareCompass helps navigate care; it does not diagnose or prescribe.</p></section>
    <section className="card" style={{ marginTop: 28, padding: 24 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}><div><span className="eyebrow">Live voice conversation</span><h2 style={{ margin: "7px 0 0", fontSize: 26 }}>Talk to CareCompass</h2></div><button type="button" onClick={startVoice} disabled={busy} className="button" style={{ background: listening ? "#a91e2a" : "var(--teal)" }}>{listening ? (speaking ? "CareCompass is speaking…" : "■ End voice") : "● Talk to CareCompass"}</button></div>
      <p className="muted" style={{ margin: "12px 0 0", fontSize: 14 }}>Your words and the agent&apos;s reply appear in this conversation. Allow microphone access when asked.</p>
      <div aria-live="polite" style={{ marginTop: 20, maxHeight: 330, overflowY: "auto", display: "grid", gap: 10, padding: 4 }}>
        {turns.length === 0 && <p className="muted" style={{ margin: "28px 0", textAlign: "center" }}>Start a voice conversation or type a message below.</p>}
        {turns.map((turn, index) => <div key={`${turn.role}-${index}`} style={{ justifySelf: turn.role === "user" ? "end" : "start", maxWidth: "88%", borderRadius: 18, padding: "12px 15px", background: turn.role === "user" ? "#e6f5f1" : "#f1f5f4" }}><strong style={{ display: "block", fontSize: 11, color: "var(--teal)", letterSpacing: ".07em", textTransform: "uppercase", marginBottom: 5 }}>{turn.role === "user" ? "You" : "CareCompass"}</strong>{turn.content}</div>)}
        {liveTranscript && <div style={{ justifySelf: "end", maxWidth: "88%", borderRadius: 18, padding: "12px 15px", background: "#f0fbf8", color: "var(--muted)" }}><strong style={{ display: "block", fontSize: 11, color: "var(--teal)", marginBottom: 5 }}>YOU ARE SAYING</strong>{liveTranscript}</div>}
      </div>
      <form onSubmit={sendText} style={{ marginTop: 20 }}><label htmlFor="message" style={{ fontWeight: 700 }}>Or type your message</label><textarea id="message" value={input} onChange={(event) => setInput(event.target.value)} placeholder="e.g. papa ko do din se bukhar hai" rows={3} style={{ width: "100%", resize: "vertical", margin: "10px 0 14px", padding: 15, border: "1px solid #dce7e4", borderRadius: 14, color: "var(--navy)", font: "inherit" }} /><div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}><button type="submit" disabled={busy} className="button">{busy ? "CareCompass is thinking…" : "Send message →"}</button><button type="button" onClick={useLocation} className="button" style={{ background: "#e7f5f2", color: "var(--teal)" }}>◎ Use my location</button></div></form>
    </section>
    {status && <p role="status" className="pill" style={{ marginTop: 16 }}>{status}</p>}
    {emergency && <section className="danger" style={{ marginTop: 24 }}><a href="tel:112" className="button" style={{ background: "white", color: "#a91e2a", textDecoration: "none" }}>Call 112 now</a><h2 style={{ margin: "20px 0 7px", fontSize: 29 }}>This may need immediate care.</h2><p style={{ margin: 0 }}>{result?.reasoning}</p></section>}
    {result && !emergency && <section className="card" style={{ marginTop: 24, padding: 24 }}><span className="pill">{result.urgency?.replace("_", " ") ?? "Care guidance"}</span><h2 style={{ margin: "12px 0 6px", fontSize: 26 }}>{result.follow_up_question ? "One quick question" : careNames[result.care_type ?? ""] ?? "Care option"}</h2><p className="muted" style={{ lineHeight: 1.6 }}>{result.follow_up_question ?? result.reasoning}</p>{result.matched_caregivers.length > 0 && <div className="grid" style={{ marginTop: 16 }}>{result.matched_caregivers.map((caregiver) => <div key={caregiver.caregiver_id} style={{ border: "1px solid #e4ece9", borderRadius: 15, padding: 16 }}><strong>{caregiver.caregiver_id}</strong><p className="muted" style={{ margin: "7px 0 0", fontSize: 14 }}>{caregiver.reason}</p></div>)}</div>}</section>}
  </main>;
}
