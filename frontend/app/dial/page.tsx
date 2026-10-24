"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { API_BASE_URL } from "../../lib/api";

type CallState = "idle" | "dialing" | "connecting" | "connected" | "ended" | "error";
type Theme = "classic" | "cyber" | "luxury" | "minimal" | "neon";
type Turn = { role: "You" | "NOVA"; text: string; at: string };
type NovaEvent = { type: string; text?: string; transcript?: string; agent_reply?: string; audio_base64?: string; audio_mime_type?: string; message?: string };

const NOVA_NUMBER = "99990000";
const KEYS = [["1", ""], ["2", "ABC"], ["3", "DEF"], ["4", "GHI"], ["5", "JKL"], ["6", "MNO"], ["7", "PQRS"], ["8", "TUV"], ["9", "WXYZ"], ["*", ""], ["0", "+"], ["#", ""]] as const;
const API_WS_URL = API_BASE_URL.replace(/^http/, "ws");

export default function NovaDialPage() {
  const [digits, setDigits] = useState("");
  const [callState, setCallState] = useState<CallState>("idle");
  const [status, setStatus] = useState("Enter 99990000, then press call.");
  const [seconds, setSeconds] = useState(0);
  const [theme, setTheme] = useState<Theme>("classic");
  const [muted, setMuted] = useState(false);
  const [speakerOn, setSpeakerOn] = useState(true);
  const [speaking, setSpeaking] = useState(false);
  const [partial, setPartial] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [historyEnabled, setHistoryEnabled] = useState(false);
  const [showTranscript, setShowTranscript] = useState(true);
  const socketRef = useRef<WebSocket | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const contextRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const audioSourceRef = useRef<AudioBufferSourceNode | null>(null);
  const speakingRef = useRef(false);
  const callStartedAtRef = useRef<number | null>(null);
  const ringtoneRef = useRef<OscillatorNode | null>(null);

  useEffect(() => {
    if (callState !== "connected" || !callStartedAtRef.current) return;
    const interval = window.setInterval(() => setSeconds(Math.floor((Date.now() - (callStartedAtRef.current ?? Date.now())) / 1000)), 1000);
    return () => window.clearInterval(interval);
  }, [callState]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey || (event.target as HTMLElement)?.tagName === "TEXTAREA") return;
      if (/^[0-9*#]$/.test(event.key)) { event.preventDefault(); addDigit(event.key); }
      if (event.key === "Backspace") { event.preventDefault(); eraseDigit(); }
      if (event.key === "Enter") { event.preventDefault(); void beginCall(); }
      if (event.key === "Escape") endCall("Call ended.");
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  });

  useEffect(() => () => endCall("Call ended."), []);

  function timestamp() { return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); }
  function addTurn(role: Turn["role"], text: string) { setTurns((previous) => [...previous, { role, text, at: timestamp() }]); }
  function addDigit(key: string) {
    if (!["idle", "dialing", "ended", "error"].includes(callState) || digits.length >= 16) return;
    setDigits((current) => current + key); setCallState("dialing"); setStatus("Ready to call");
  }
  function eraseDigit() {
    if (!["idle", "dialing", "ended", "error"].includes(callState)) return;
    setDigits((current) => current.slice(0, -1)); setCallState(digits.length <= 1 ? "idle" : "dialing");
  }
  function stopRingtone() { ringtoneRef.current?.stop(); ringtoneRef.current?.disconnect(); ringtoneRef.current = null; }
  function ring(context: AudioContext) {
    const oscillator = context.createOscillator(); const gain = context.createGain();
    oscillator.frequency.value = 440; gain.gain.value = 0.035; oscillator.connect(gain); gain.connect(context.destination); oscillator.start(); ringtoneRef.current = oscillator;
  }
  function stopAgentAudio() {
    audioSourceRef.current?.stop(); audioSourceRef.current?.disconnect(); audioSourceRef.current = null;
    speakingRef.current = false; setSpeaking(false);
  }
  function playAgentAudio(audioBase64?: string, mime?: string) {
    if (!audioBase64 || !mime || !speakerOn || !contextRef.current) { setStatus("Listening…"); return; }
    try {
      const binary = atob(audioBase64); const bytes = new Uint8Array(binary.length);
      for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
      void contextRef.current.decodeAudioData(bytes.buffer).then((buffer) => {
        stopAgentAudio();
        const source = contextRef.current?.createBufferSource();
        if (!source || !contextRef.current) return;
        source.buffer = buffer; source.connect(contextRef.current.destination); audioSourceRef.current = source;
        speakingRef.current = true; setSpeaking(true); setStatus("NOVA is speaking — tap the waveform to interrupt.");
        source.onended = () => { if (audioSourceRef.current === source) { audioSourceRef.current = null; speakingRef.current = false; setSpeaking(false); setStatus("Listening…"); } };
        source.start();
      }).catch(() => setStatus("NOVA replied, but audio could not be played."));
    } catch { setStatus("NOVA replied, but audio could not be decoded."); }
  }
  function cleanupMedia() {
    stopRingtone(); stopAgentAudio(); processorRef.current?.disconnect(); sourceRef.current?.disconnect();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    processorRef.current = null; sourceRef.current = null; streamRef.current = null;
    void contextRef.current?.close(); contextRef.current = null;
  }
  function endCall(message = "Call ended.") {
    if (socketRef.current?.readyState === WebSocket.OPEN) socketRef.current.send("end");
    socketRef.current?.close(); socketRef.current = null; cleanupMedia(); callStartedAtRef.current = null;
    if (callState === "connected" && historyEnabled) {
      const item = { number: NOVA_NUMBER, duration: seconds, endedAt: new Date().toISOString(), turns };
      const stored = JSON.parse(window.localStorage.getItem("nova-call-history") ?? "[]") as object[];
      window.localStorage.setItem("nova-call-history", JSON.stringify([item, ...stored].slice(0, 12)));
    }
    setPartial(""); setMuted(false); setSpeaking(false); setCallState("ended"); setStatus(message);
  }
  function stopForError(message: string) { cleanupMedia(); socketRef.current?.close(); socketRef.current = null; setCallState("error"); setStatus(message); }
  function sendPCM(samples: Float32Array, sampleRate: number) {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN || muted || speakingRef.current) return;
    const ratio = sampleRate / 16000; const pcm = new Int16Array(Math.floor(samples.length / ratio));
    for (let index = 0; index < pcm.length; index += 1) pcm[index] = Math.max(-1, Math.min(1, samples[Math.floor(index * ratio)])) * 0x7fff;
    socket.send(pcm.buffer);
  }
  async function beginCall() {
    if (callState === "connecting" || callState === "connected") return;
    if (digits !== NOVA_NUMBER) { setCallState("error"); setStatus(digits ? "Number not available. Dial 99990000 for NOVA." : "Enter 99990000 first."); return; }
    setCallState("connecting"); setStatus("Calling AI Assistant…"); setTurns([]); setSeconds(0);
    const context = new AudioContext(); contextRef.current = context;
    try {
      await context.resume(); ring(context);
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
      const socket = new WebSocket(`${API_WS_URL}/api/v1/voice/realtime?assistant=nova`);
      socket.binaryType = "arraybuffer"; socketRef.current = socket; streamRef.current = stream;
      socket.onopen = () => {
        const source = context.createMediaStreamSource(stream); const processor = context.createScriptProcessor(2048, 1, 1); const quiet = context.createGain(); quiet.gain.value = 0;
        processor.onaudioprocess = (event) => sendPCM(event.inputBuffer.getChannelData(0), context.sampleRate);
        source.connect(processor); processor.connect(quiet); quiet.connect(context.destination); sourceRef.current = source; processorRef.current = processor;
      };
      socket.onmessage = (event) => {
        const message = JSON.parse(event.data) as NovaEvent;
        if (message.type === "ready") {
          stopRingtone(); callStartedAtRef.current = Date.now(); setCallState("connected"); setStatus("Connected — NOVA is speaking.");
          if (message.text) addTurn("NOVA", message.text); playAgentAudio(message.audio_base64, message.audio_mime_type);
        }
        if (message.type === "partial") { setPartial(message.text ?? ""); if (!speakingRef.current) setStatus("Listening…"); }
        if (message.type === "final") { const transcript = message.transcript?.trim(); const reply = message.agent_reply?.trim(); if (transcript) addTurn("You", transcript); if (reply) addTurn("NOVA", reply); setPartial(""); playAgentAudio(message.audio_base64, message.audio_mime_type); }
        if (message.type === "error") stopForError(message.message ?? "NOVA could not connect right now.");
      };
      socket.onerror = () => stopForError("Could not connect to the voice service. Check that the CareCompass backend is running and SARVAM_API_KEY is configured.");
      socket.onclose = () => { if (socketRef.current === socket) stopForError("Voice connection closed before it was ready."); };
    } catch (error) {
      const message = error instanceof DOMException && error.name === "NotAllowedError" ? "Microphone permission was denied. Allow it in the browser, then call again." : "Microphone or network is unavailable. Check your connection and try again.";
      stopForError(message);
    }
  }
  function interrupt() { if (!speaking) return; stopAgentAudio(); setStatus("Listening…"); }
  function toggleMute() { const next = !muted; streamRef.current?.getAudioTracks().forEach((track) => { track.enabled = !next; }); setMuted(next); setStatus(next ? "Microphone muted." : "Listening…"); }
  function toggleSpeaker() { const next = !speakerOn; setSpeakerOn(next); if (!next) stopAgentAudio(); setStatus(next ? "Speaker on." : "Speaker muted."); }
  function clearHistory() { window.localStorage.removeItem("nova-call-history"); setStatus("Saved call history cleared from this browser."); }
  const time = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const duration = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;

  return <main className={`nova-page nova-${theme}`}>
    <header className="nova-header"><Link href="/patient">← Back to CareCompass</Link><div><label htmlFor="theme">Phone theme</label><select id="theme" value={theme} onChange={(event) => setTheme(event.target.value as Theme)}><option value="classic">Classic Retro</option><option value="cyber">Cyberpunk AI</option><option value="luxury">Luxury Edition</option><option value="minimal">Minimalist</option><option value="neon">Dark Neon</option></select></div></header>
    <section className="nova-layout">
      <div className="nova-phone" aria-label="Virtual NOVA keypad phone">
        <div className="nova-speaker"><i /><i /><i /><i /><i /></div>
        <div className="nova-screen">
          <div className="nova-statusbar"><span>▂▅▇</span><span>AI NET</span><span>{time}</span><span>▰</span></div>
          {callState === "connected" ? <div className="nova-call-screen"><p>AI ASSISTANT</p><strong>NOVA</strong><span>Connected · {duration}</span><button type="button" onClick={interrupt} className={`nova-wave ${speaking ? "active" : ""}`} aria-label="Interrupt NOVA"><i /><i /><i /><i /><i /></button><small>{muted ? "Microphone muted" : partial || (speaking ? "Speaking…" : "Listening…")}</small></div> : <div className="nova-idle-screen"><p>{callState === "connecting" ? "CALLING AI ASSISTANT…" : callState === "error" ? "CALL FAILED" : "NOVA DIAL"}</p><strong>{digits || "_"}</strong><span>{status}</span></div>}
        </div>
        <div className="nova-nav"><button type="button" onClick={eraseDigit} aria-label="Delete digit">⌫</button><button type="button" onClick={() => setStatus("Dial 99990000 to talk to NOVA.")} aria-label="Information">●</button><button type="button" onClick={() => setShowTranscript((value) => !value)} aria-label="Show transcript">☰</button></div>
        <div className="nova-keypad">{KEYS.map(([key, letters]) => <button type="button" key={key} onClick={() => addDigit(key)}><b>{key}</b><small>{letters}</small></button>)}</div>
        <div className="nova-actions"><button type="button" onClick={() => void beginCall()} className="nova-call" disabled={callState === "connecting" || callState === "connected"} aria-label="Call NOVA">☎</button><button type="button" onClick={() => endCall("Call ended.")} className="nova-end" aria-label="End call">⌕</button></div>
        {callState === "connected" && <div className="nova-call-controls"><button type="button" onClick={toggleMute}>{muted ? "Unmute" : "Mute"}</button><button type="button" onClick={toggleSpeaker}>{speakerOn ? "Speaker on" : "Speaker off"}</button><button type="button" onClick={() => endCall("Call ended.")}>End call</button></div>}
      </div>
      <aside className="nova-panel">
        <span className="nova-eyebrow">DIAL 99990000</span><h1>Talk to intelligence.</h1><p>Dial NOVA for a real multilingual voice conversation powered by Sarvam. Speak naturally in English, Hindi, or Hinglish.</p>
        <div className="nova-privacy"><strong>Microphone privacy</strong><span>Microphone capture is active only during a connected call. Audio is not saved by this app.</span><label><input type="checkbox" checked={historyEnabled} onChange={(event) => setHistoryEnabled(event.target.checked)} /> Save this call&apos;s text transcript locally</label><button type="button" onClick={clearHistory}>Clear saved history</button></div>
        {showTranscript && <div className="nova-transcript" aria-live="polite"><div><strong>Live transcript</strong><button type="button" onClick={() => setTurns([])}>Clear</button></div>{turns.length === 0 ? <p>Your conversation will appear here after NOVA connects.</p> : turns.map((turn, index) => <article key={`${turn.role}-${index}`} className={turn.role === "You" ? "nova-you" : "nova-agent"}><small>{turn.role} · {turn.at}</small><p>{turn.text}</p></article>)}{partial && <article className="nova-you pending"><small>You are saying</small><p>{partial}</p></article>}</div>}
        <p className="nova-note">NOVA is an AI assistant. For urgent medical care, use CareCompass and call 5555.</p>
      </aside>
    </section>
  </main>;
}
