"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { API_BASE_URL } from "../../lib/api";

type Result = {
  follow_up_question: string | null;
  care_type: string | null;
  urgency: string | null;
  red_flags: string[];
  reasoning: string;
  matched_caregivers: { caregiver_id: string; score: number; reason: string }[];
};
type Turn = { role: string; content: string; follow_up_question?: string };

const names: Record<string, string> = {
  paramedic_home_visit: "Medic home visit",
  home_nursing: "Home nursing",
  lab_test_home: "Home lab test",
  teleconsultation: "Virtual doctor",
  emergency_112: "Emergency services",
};

function encodeWav(input: Float32Array, sourceRate: number): Blob {
  const targetRate = 16_000;
  const ratio = sourceRate / targetRate;
  const targetLength = Math.max(1, Math.floor(input.length / ratio));
  const pcm = new Int16Array(targetLength);
  for (let i = 0; i < targetLength; i += 1) {
    const start = Math.floor(i * ratio);
    const end = Math.min(input.length, Math.max(start + 1, Math.floor((i + 1) * ratio)));
    let total = 0;
    for (let j = start; j < end; j += 1) total += input[j];
    const sample = Math.max(-1, Math.min(1, total / (end - start)));
    pcm[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }

  const buffer = new ArrayBuffer(44 + pcm.length * 2);
  const view = new DataView(buffer);
  const writeText = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i += 1) view.setUint8(offset + i, value.charCodeAt(i));
  };
  writeText(0, "RIFF");
  view.setUint32(4, 36 + pcm.length * 2, true);
  writeText(8, "WAVE");
  writeText(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, targetRate, true);
  view.setUint32(28, targetRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeText(36, "data");
  view.setUint32(40, pcm.length * 2, true);
  for (let i = 0; i < pcm.length; i += 1) view.setInt16(44 + i * 2, pcm[i], true);
  return new Blob([buffer], { type: "audio/wav" });
}

function formatTimer(seconds: number) {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

export default function PatientPage() {
  const [input, setInput] = useState("");
  const [history, setHistory] = useState<Turn[]>([]);
  const [lat, setLat] = useState("28.54");
  const [lng, setLng] = useState("77.27");
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState("");
  const [error, setError] = useState("");
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const streamRef = useRef<MediaStream | null>(null);
  const contextRef = useRef<AudioContext | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const chunksRef = useRef<Float32Array[]>([]);
  const sourceRateRef = useRef(48_000);
  const intervalRef = useRef<number | null>(null);
  const stopTimeoutRef = useRef<number | null>(null);
  const startedAtRef = useRef(0);

  async function submitText(message: string) {
    const trimmed = message.trim();
    if (!trimmed) return;
    setBusy(true);
    setError("");
    const turns = [...history, { role: "user", content: trimmed }];
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/care/intake-triage-match`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_input: trimmed,
          language: "auto",
          location: { lat: Number(lat), lng: Number(lng) },
          conversation_history: history,
        }),
      });
      if (!response.ok) throw new Error(`Care service returned ${response.status}`);
      const data: Result = await response.json();
      const nextHistory = data.follow_up_question
        ? [...turns, { role: "assistant", content: data.follow_up_question, follow_up_question: data.follow_up_question }]
        : turns;
      setHistory(nextHistory);
      setInput("");
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reach the care service.");
    } finally {
      setBusy(false);
    }
  }

  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await submitText(input);
  }

  function stopTracksAndAudio() {
    if (intervalRef.current !== null) window.clearInterval(intervalRef.current);
    if (stopTimeoutRef.current !== null) window.clearTimeout(stopTimeoutRef.current);
    intervalRef.current = null;
    stopTimeoutRef.current = null;
    processorRef.current?.disconnect();
    sourceRef.current?.disconnect();
    processorRef.current = null;
    sourceRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    const context = contextRef.current;
    contextRef.current = null;
    if (context && context.state !== "closed") void context.close();
  }

  async function startRecording() {
    setError("");
    if (!navigator.mediaDevices?.getUserMedia) {
      setError("Microphone access is unavailable in this browser. You can type your request instead.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
      const context = new AudioContext();
      const source = context.createMediaStreamSource(stream);
      const processor = context.createScriptProcessor(4096, 1, 1);
      sourceRateRef.current = context.sampleRate;
      chunksRef.current = [];
      processor.onaudioprocess = (event) => {
        chunksRef.current.push(new Float32Array(event.inputBuffer.getChannelData(0)));
        event.outputBuffer.getChannelData(0).fill(0);
      };
      source.connect(processor);
      processor.connect(context.destination);
      streamRef.current = stream;
      contextRef.current = context;
      sourceRef.current = source;
      processorRef.current = processor;
      startedAtRef.current = Date.now();
      setRecordingSeconds(0);
      setRecording(true);
      intervalRef.current = window.setInterval(() => {
        setRecordingSeconds(Math.floor((Date.now() - startedAtRef.current) / 1000));
      }, 250);
      stopTimeoutRef.current = window.setTimeout(() => void stopRecording(), 30_000);
    } catch (err) {
      const name = err instanceof DOMException ? err.name : "";
      if (name === "NotAllowedError" || name === "SecurityError") {
        setError("Microphone permission was denied. You can type your request instead.");
      } else if (name === "NotFoundError" || name === "DevicesNotFoundError") {
        setError("No microphone was found. You can type your request instead.");
      } else {
        setError("Could not start the microphone. Please try again or type your request.");
      }
      stopTracksAndAudio();
    }
  }

  async function stopRecording() {
    if (!recording && !streamRef.current) return;
    const chunks = chunksRef.current;
    chunksRef.current = [];
    const rate = sourceRateRef.current;
    stopTracksAndAudio();
    setRecording(false);
    setRecordingSeconds(Math.min(30, Math.floor((Date.now() - startedAtRef.current) / 1000)));
    const sampleCount = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
    if (sampleCount < rate * 0.2) {
      setError("No speech was detected. Please try again or type your request.");
      return;
    }
    const samples = new Float32Array(sampleCount);
    let offset = 0;
    let peak = 0;
    for (const chunk of chunks) {
      samples.set(chunk, offset);
      offset += chunk.length;
      for (let i = 0; i < chunk.length; i += 1) peak = Math.max(peak, Math.abs(chunk[i]));
    }
    if (peak < 0.003) {
      setError("No speech was detected. Please try again or type your request.");
      return;
    }

    setTranscribing(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", encodeWav(samples, rate), "recording.wav");
      const response = await fetch(`${API_BASE_URL}/api/v1/voice/stt`, { method: "POST", body: form });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = typeof payload.detail === "string" ? payload.detail : "Voice transcription is unavailable.";
        throw new Error(detail);
      }
      const transcript = typeof payload.transcript === "string" ? payload.transcript.trim() : "";
      if (!transcript) throw new Error("No speech was detected. Please try again or type your request.");
      setInput(transcript);
      await submitText(transcript);
    } catch (err) {
      setError(err instanceof Error ? `${err.message} You can type your request instead.` : "Voice transcription failed. You can type your request instead.");
    } finally {
      setTranscribing(false);
    }
  }

  function useLocation() {
    if (!navigator.geolocation) {
      setError("Location access is unavailable. Enter coordinates manually.");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLat(position.coords.latitude.toFixed(5));
        setLng(position.coords.longitude.toFixed(5));
      },
      () => setError("Location was not shared. You can enter coordinates manually."),
    );
  }

  useEffect(() => () => stopTracksAndAudio(), []);

  const emergency = result?.care_type === "emergency_112";
  const recordingStatus = recording ? `Listening… ${formatTimer(recordingSeconds)} / 0:30` : "";

  return (
    <main className="container" style={{ padding: "24px 0 60px", maxWidth: 850 }}>
      <Link href="/" style={{ color: "var(--teal)", textDecoration: "none", fontWeight: 700 }}>← CareCompass</Link>
      <span className="eyebrow" style={{ display: "block", marginTop: 42 }}>Care intake</span>
      <h1 style={{ fontSize: "clamp(36px, 6vw, 56px)", margin: "10px 0" }}>Let’s find the right care.</h1>
      <p className="muted" style={{ fontSize: 17 }}>Share what support you need. This service routes care and does not diagnose or prescribe.</p>

      <section className="card" style={{ padding: 24, marginTop: 26 }}>
        <form onSubmit={send}>
          <label htmlFor="message" style={{ fontWeight: 700 }}>What’s going on?</label>
          <div className="intake-composer">
            <textarea
              id="message"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="Describe the service or support you need…"
              rows={4}
              style={{ width: "100%", resize: "vertical", margin: "10px 0 16px", padding: 15, border: "1px solid #dce7e4", borderRadius: 14, color: "var(--navy)" }}
            />
            <button
              type="button"
              className={`mic-button${recording ? " is-recording" : ""}`}
              aria-label="Speak your request"
              aria-pressed={recording}
              title={recording ? "Stop recording" : "Speak your request"}
              onClick={() => recording ? void stopRecording() : void startRecording()}
              disabled={busy || transcribing}
            >
              <span aria-hidden="true">{recording ? "■" : "🎙"}</span>
            </button>
          </div>
          {(recording || transcribing) && (
            <p className={`voice-status${recording ? " is-recording" : ""}`} role="status" aria-live="polite">
              {recording ? recordingStatus : "Transcribing…"}
            </p>
          )}
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", marginBottom: 17 }}>
            <button type="button" onClick={useLocation} className="button" style={{ background: "#e7f5f2", color: "var(--teal)" }}>◎ Use my location</button>
            <label className="muted">Lat <input aria-label="Latitude" value={lat} onChange={(event) => setLat(event.target.value)} style={{ width: 90, padding: 8, border: "1px solid #dce7e4", borderRadius: 8 }} /></label>
            <label className="muted">Lng <input aria-label="Longitude" value={lng} onChange={(event) => setLng(event.target.value)} style={{ width: 90, padding: 8, border: "1px solid #dce7e4", borderRadius: 8 }} /></label>
          </div>
          <button className="button" disabled={busy || transcribing || recording}>{busy ? "Finding care…" : transcribing ? "Transcribing…" : "Continue →"}</button>
        </form>
        {error && <p role="alert" style={{ color: "#a91e2a", marginBottom: 0 }}>{error}</p>}
      </section>

      {history.length > 0 && (
        <section aria-label="Conversation" style={{ marginTop: 20 }}>
          {history.map((turn, index) => (
            <div key={index} style={{ textAlign: turn.role === "user" ? "right" : "left", margin: "10px 0" }}>
              <span className="card" style={{ display: "inline-block", padding: "12px 16px", maxWidth: "85%" }}>{turn.content}</span>
            </div>
          ))}
        </section>
      )}

      {result && (
        <section style={{ marginTop: 24 }}>
          {emergency ? (
            <div className="danger">
              <a href="tel:112" className="button" style={{ background: "white", color: "#a91e2a", fontSize: 22, textDecoration: "none", display: "inline-block", marginBottom: 20 }}>Call 112</a>
              <h2 style={{ fontSize: 30, margin: "0 0 8px" }}>Please contact emergency services now.</h2>
              <p style={{ margin: 0 }}>These symptoms may need urgent emergency attention. CareCompass cannot provide emergency care.</p>
              {result.red_flags.length > 0 && <p>Red flags: {result.red_flags.join(", ")}</p>}
            </div>
          ) : (
            <article className="card" style={{ padding: 24 }}>
              {result.follow_up_question ? (
                <><span className="pill">One more detail</span><p style={{ fontSize: 19, lineHeight: 1.5 }}>{result.follow_up_question}</p></>
              ) : (
                <>
                  <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                    <h2 style={{ margin: "0 auto 0 0", fontSize: 27 }}>{names[result.care_type || ""] || "Care option"}</h2>
                    <span className="pill">{result.urgency?.replace("_", " ")}</span>
                  </div>
                  <p className="muted" style={{ lineHeight: 1.6 }}>{result.reasoning}</p>
                  {result.red_flags.length > 0 && <p style={{ color: "#a91e2a", fontWeight: 700 }}>Red flags: {result.red_flags.join(", ")}</p>}
                  {result.matched_caregivers.length > 0 && (
                    <><h3>Available caregivers</h3><div className="grid">{result.matched_caregivers.map((caregiver) => (
                      <div key={caregiver.caregiver_id} style={{ border: "1px solid #e4ece9", borderRadius: 15, padding: 16, display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
                        <div><strong>{caregiver.caregiver_id}</strong><div className="muted" style={{ fontSize: 14, marginTop: 4 }}>{caregiver.reason}</div></div>
                        <div style={{ textAlign: "right" }}><span className="pill">{caregiver.score.toFixed(2)}</span><br /><button onClick={() => { setToast("Booking will be available soon."); setTimeout(() => setToast(""), 2600); }} style={{ border: 0, background: "none", color: "var(--teal)", fontWeight: 700, cursor: "pointer", marginTop: 8 }}>Book</button></div>
                      </div>
                    ))}</div></>
                  )}
                </>
              )}
            </article>
          )}
        </section>
      )}
      {toast && <div role="status" className="pill" style={{ position: "fixed", bottom: 20, left: "50%", transform: "translateX(-50%)", padding: 14 }}>{toast}</div>}
    </main>
  );
}

