"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { API_BASE_URL } from "../../lib/api";

type CareResult = {
  follow_up_question: string | null;
  care_type: string | null;
  urgency: string | null;
  red_flags: string[];
  reasoning: string;
  matched_caregivers: { caregiver_id: string; score: number; reason: string }[];
};
type AssistantResult = {
  mode: "emergency" | "care" | "followup" | "answer" | "smalltalk" | "app_help" | "off_topic";
  message: string;
  care: CareResult | null;
  language: "Hindi" | "Hinglish" | "English";
  suggestions: string[];
  care_context: CareContext | null;
  spoken_message?: string | null;
};
type CareContext = { care_type: string; urgency: string; reasoning: string; symptoms: string[] };
type VoiceLanguage = "hi-IN" | "en-IN";
type AssistantLanguage = "Hindi" | "Hinglish" | "English";
type Turn = { role: string; content: string; follow_up_question?: string; language?: VoiceLanguage; suggestions?: string[]; spoken_message?: string | null; care_context?: CareContext | null };

const names: Record<string, string> = {
  paramedic_home_visit: "Medic home visit",
  home_nursing: "Nursing at home",
  lab_test_home: "Lab test at home",
  teleconsultation: "Virtual doctor",
  emergency_112: "Emergency – call 112",
};

const hindiNames: Record<string, string> = {
  paramedic_home_visit: "घर पर मेडिक विज़िट",
  home_nursing: "घर पर नर्सिंग सेवा",
  lab_test_home: "घर पर लैब टेस्ट",
  teleconsultation: "ऑनलाइन डॉक्टर से परामर्श",
  emergency_112: "आपातकाल – 112 पर कॉल करें",
};
const hinglishNames: Record<string, string> = { paramedic_home_visit: "Medic home visit", home_nursing: "Ghar par nursing service", lab_test_home: "Ghar par lab test", teleconsultation: "Online doctor se salah", emergency_112: "Emergency – 112 par call karein" };

function inferVoiceLanguage(text: string, detected?: string | null): VoiceLanguage {
  if (detected?.toLowerCase().startsWith("hi") || /[\u0900-\u097f]/.test(text)) return "hi-IN";
  const hindiMarkers = new Set(["ko", "hai", "nahi", "nahin", "mein", "se", "chahiye", "ghar", "bukhar", "khansi", "dard"]);
  if (text.toLowerCase().split(/\W+/).some((word) => hindiMarkers.has(word))) return "hi-IN";
  return "en-IN";
}

function spokenSummary(result: AssistantResult): string { return result.spoken_message || result.message; }

function plainCareValue(value: string | null | undefined, language: AssistantLanguage = "English") {
  const labels = language === "Hindi" ? hindiNames : language === "Hinglish" ? hinglishNames : names;
  return labels[value || ""] || "Care option";
}

function plainUrgency(value: string | null | undefined, language: AssistantLanguage = "English") {
  const labels: Record<string, string> = language === "Hindi"
    ? { same_day: "आज ही", scheduled: "निर्धारित समय पर", emergency: "आपातकालीन" }
    : language === "Hinglish" ? { same_day: "aaj hi", scheduled: "tay samay par", emergency: "emergency" } : { same_day: "same day", scheduled: "scheduled", emergency: "emergency" };
  return labels[value || ""] || "";
}

function plainReasoning(value: string, language: AssistantLanguage, careType: string | null, urgency: string | null) {
  if (language === "Hindi") return `आपके बताए लक्षणों के आधार पर ${plainCareValue(careType, language)} का सुझाव है। प्राथमिकता: ${plainUrgency(urgency, language)}।`;
  if (language === "Hinglish") return `Aapki batayi problem ke hisaab se ${plainCareValue(careType, language)} suggest kiya hai. Priority: ${plainUrgency(urgency, language)}.`;
  const careLabels: Record<string, string> = {
    paramedic_home_visit: "Medic home visit", home_nursing: "Nursing at home", lab_test_home: "Lab test at home", teleconsultation: "Virtual doctor", emergency_112: "Emergency – call 112",
  };
  const urgencyLabels: Record<string, string> = { same_day: "same day", scheduled: "scheduled", emergency: "emergency" };
  let output = value;
  for (const [apiValue, label] of Object.entries({ ...careLabels, ...urgencyLabels })) output = output.replaceAll(apiValue, label);
  return output;
}

const redFlagLabels: Record<string, string> = { chest_pain: "chest pain", breathlessness: "difficulty breathing", unconsciousness: "unconsciousness", severe_bleeding: "severe bleeding", stroke_symptoms: "stroke symptoms", seizure: "seizure", high_fever_infant: "high fever in an infant", suicidal_ideation: "suicidal thoughts", severe_dehydration: "severe dehydration" };
const hindiRedFlagLabels: Record<string, string> = { chest_pain: "सीने में दर्द", breathlessness: "सांस लेने में तकलीफ़", unconsciousness: "बेहोशी", severe_bleeding: "गंभीर रक्तस्राव", stroke_symptoms: "स्ट्रोक के लक्षण", seizure: "दौरा", high_fever_infant: "शिशु को तेज़ बुखार", suicidal_ideation: "आत्महत्या के विचार", severe_dehydration: "गंभीर निर्जलीकरण" };
const hinglishRedFlagLabels: Record<string, string> = { chest_pain: "seene mein dard", breathlessness: "saans lene mein dikkat", unconsciousness: "behoshi", severe_bleeding: "zyada bleeding", stroke_symptoms: "stroke ke signs", seizure: "daura", high_fever_infant: "shishu ko tez bukhar", suicidal_ideation: "khudkushi ke vichaar", severe_dehydration: "bahut paani ki kami" };

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
  const [result, setResult] = useState<AssistantResult | null>(null);
  const [careContext, setCareContext] = useState<CareContext | null>(null);
  const [showCaregivers, setShowCaregivers] = useState(false);
  const conversationEndRef = useRef<HTMLDivElement | null>(null);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState("");
  const [error, setError] = useState("");
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [readAloud, setReadAloud] = useState(false);
  const [hasUsedMic, setHasUsedMic] = useState(false);
  const readAloudRef = useRef(readAloud);
  const streamRef = useRef<MediaStream | null>(null);
  const contextRef = useRef<AudioContext | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const chunksRef = useRef<Float32Array[]>([]);
  const sourceRateRef = useRef(48_000);
  const intervalRef = useRef<number | null>(null);
  const stopTimeoutRef = useRef<number | null>(null);
  const startedAtRef = useRef(0);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioUrlRef = useRef<string | null>(null);
  const speechRequestRef = useRef(0);
  readAloudRef.current = readAloud;

  function stopSpeech() {
    speechRequestRef.current += 1;
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
      audioRef.current = null;
    }
    if (audioUrlRef.current) {
      URL.revokeObjectURL(audioUrlRef.current);
      audioUrlRef.current = null;
    }
  }

  async function playSpeech(text: string, language: VoiceLanguage, showError = false) {
    stopSpeech();
    const requestId = speechRequestRef.current;
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/voice/tts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: text.slice(0, 500), language }),
      });
      if (requestId !== speechRequestRef.current) return;
      if (!response.ok) throw new Error("Spoken reply is unavailable right now.");
      const audioUrl = URL.createObjectURL(await response.blob());
      if (requestId !== speechRequestRef.current) {
        URL.revokeObjectURL(audioUrl);
        return;
      }
      const audio = new Audio(audioUrl);
      audioRef.current = audio;
      audioUrlRef.current = audioUrl;
      const cleanup = () => {
        if (audioRef.current === audio) audioRef.current = null;
        if (audioUrlRef.current === audioUrl) audioUrlRef.current = null;
        URL.revokeObjectURL(audioUrl);
      };
      audio.onended = cleanup;
      audio.onerror = cleanup;
      await audio.play();
    } catch (err) {
      if (showError && requestId === speechRequestRef.current) {
        setError(err instanceof Error ? err.message : "Could not play the spoken reply.");
      }
    }
  }

  async function submitText(message: string, detectedLanguage?: string | null) {
    const trimmed = message.trim();
    if (!trimmed) return;
    stopSpeech();
    setBusy(true);
    setError("");
    const responseLanguage = inferVoiceLanguage(trimmed, detectedLanguage);
    const turns: Turn[] = [...history, { role: "user", content: trimmed, language: responseLanguage }];
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/assistant/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: trimmed,
          language: detectedLanguage || "auto",
          location: { lat: Number(lat), lng: Number(lng) },
          history,
          care_context: careContext,
        }),
      });
      if (!response.ok) throw new Error(`Assistant service returned ${response.status}`);
      const data: AssistantResult = await response.json();
      const nextHistory = data.mode === "care" ? turns : [...turns, { role: "assistant", content: data.message, follow_up_question: data.mode === "followup" ? data.message : undefined, language: responseLanguage, suggestions: data.suggestions, spoken_message: data.spoken_message, care_context: data.care_context }];
      setHistory(nextHistory);
      setInput("");
      setResult(data);
      setCareContext(data.care_context);
      setShowCaregivers(false);
      if (readAloudRef.current) void playSpeech(spokenSummary(data), responseLanguage);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reach the assistant service.");
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
    stopSpeech();
    if (!hasUsedMic) {
      setHasUsedMic(true);
      setReadAloud(true);
    }
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
      await submitText(transcript, payload.language_code);
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

  useEffect(() => () => {
    stopTracksAndAudio();
    if (audioRef.current) audioRef.current.pause();
    if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current);
  }, []);

  useEffect(() => {
    if (history.length) conversationEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [history, result]);

  const emergency = result?.mode === "emergency" || result?.care?.care_type === "emergency_112";
  const responseLanguage: VoiceLanguage = result?.language === "Hindi" || result?.language === "Hinglish" ? "hi-IN" : "en-IN";
  const recordingStatus = recording ? `Listening… ${formatTimer(recordingSeconds)} / 0:30` : "";

  return (
    <main className="container patient-layout" style={{ maxWidth: 850 }}>
      <Link href="/" style={{ color: "var(--teal)", textDecoration: "none", fontWeight: 700 }}>← CareCompass</Link>
      <span className="eyebrow" style={{ display: "block", marginTop: 42 }}>Care intake</span>
      <h1 style={{ fontSize: "clamp(36px, 6vw, 56px)", margin: "10px 0" }}>Let’s find the right care.</h1>
      <p className="muted" style={{ fontSize: 17 }}>Share what support you need. This service routes care and does not diagnose or prescribe.</p>

      <section className="card patient-composer" style={{ padding: 24, marginTop: 26 }}>
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
          <label className="read-aloud-toggle">
            <input
              type="checkbox"
              checked={readAloud}
              onChange={(event) => setReadAloud(event.target.checked)}
              aria-label="Read aloud"
            />
            <span>Read aloud</span>
            {!hasUsedMic && <span className="muted read-aloud-hint">Voice replies turn on after your first mic use</span>}
          </label>
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
        <section aria-label="Conversation" className="patient-history" style={{ marginTop: 20 }}>
          {history.map((turn, index) => (
            <div key={index} style={{ textAlign: turn.role === "user" ? "right" : "left", margin: "10px 0" }}>
              <span className="card conversation-bubble" style={{ display: "inline-flex", alignItems: "center", gap: 8, padding: "12px 16px", maxWidth: "85%" }}>
                {turn.content}
                {turn.role === "assistant" && <button type="button" className="speaker-button" aria-label="Read this message aloud" title="Read this message aloud" onClick={() => void playSpeech(turn.spoken_message || turn.content, turn.language || "en-IN", true)}>🔊</button>}
              </span>
              {turn.role === "assistant" && !!turn.suggestions?.length && <div style={{ display: "flex", justifyContent: "flex-start", flexWrap: "wrap", gap: 8, marginTop: 8 }}>{turn.suggestions.map((suggestion) => <button key={suggestion} type="button" className="pill" disabled={busy || transcribing} onClick={() => void submitText(suggestion)} style={{ border: "1px solid #cfe2dd", cursor: "pointer", background: "white" }}>{suggestion}</button>)}</div>}
            </div>
          ))}
        </section>
      )}

      {result && (
        <section className="patient-result" style={{ marginTop: 24 }}>
          {emergency ? (
            <div className="danger">
              <a href="tel:112" className="button" style={{ background: "white", color: "#a91e2a", fontSize: 22, textDecoration: "none", display: "inline-block", marginBottom: 20 }}>{result.language === "Hindi" ? "112 पर कॉल करें" : result.language === "Hinglish" ? "112 par call karein" : "Call 112"}</a>
              <h2 style={{ fontSize: 30, margin: "0 0 8px" }}>{result.message}</h2>
              <p style={{ margin: 0 }}>{result.language === "Hindi" ? "यह ऐप आपकी ओर से आपातकालीन सेवाओं को कॉल नहीं कर सकती।" : result.language === "Hinglish" ? "Yeh app aapki taraf se emergency services ko call nahi kar sakti." : "CareCompass cannot call emergency services for you."}</p>
              {(result.care?.red_flags || []).length > 0 && <p>{result.language === "Hindi" ? "खतरे के संकेत:" : result.language === "Hinglish" ? "Khatre ke signs:" : "Red flags:"} {result.care?.red_flags.map((flag) => (result.language === "Hindi" ? hindiRedFlagLabels[flag] : result.language === "Hinglish" ? hinglishRedFlagLabels[flag] : redFlagLabels[flag]) || flag).join(", ")}</p>}
            </div>
          ) : result.mode === "care" && result.care ? (
            <article className="card" style={{ padding: 24 }}>
              <p style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 0, fontWeight: 700 }}>
                {result.message}
                <button type="button" className="speaker-button" aria-label="Read care summary aloud" title="Read care summary aloud" onClick={() => void playSpeech(spokenSummary(result), responseLanguage, true)}>🔊</button>
              </p>
              {!!result.suggestions.length && <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 14 }}>{result.suggestions.map((suggestion) => <button key={suggestion} type="button" className="pill" disabled={busy || transcribing} onClick={() => void submitText(suggestion)} style={{ border: "1px solid #cfe2dd", cursor: "pointer", background: "white" }}>{suggestion}</button>)}</div>}
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                <h2 style={{ margin: "0 auto 0 0", fontSize: 27 }}>{plainCareValue(result.care.care_type, result.language)}</h2>
                <span className="pill">{plainUrgency(result.care.urgency, result.language)}</span>
              </div>
              <p className="muted" style={{ lineHeight: 1.6 }}>{plainReasoning(result.care.reasoning, result.language, result.care.care_type, result.care.urgency)}</p>
              {result.care.red_flags.length > 0 && <p style={{ color: "#a91e2a", fontWeight: 700 }}>{result.language === "Hindi" ? "खतरे के संकेत:" : result.language === "Hinglish" ? "Khatre ke signs:" : "Red flags:"} {result.care.red_flags.map((flag) => (result.language === "Hindi" ? hindiRedFlagLabels[flag] : result.language === "Hinglish" ? hinglishRedFlagLabels[flag] : redFlagLabels[flag]) || flag).join(", ")}</p>}
              {result.care.matched_caregivers.length > 0 && <>
                <button type="button" className="button" aria-expanded={showCaregivers} onClick={() => setShowCaregivers((visible) => !visible)} style={{ marginTop: 10 }}>
                  {showCaregivers ? (result.language === "Hindi" ? "उपलब्ध देखभालकर्ता छिपाएँ" : result.language === "Hinglish" ? "Available caregivers chhupayein" : "Hide available caregivers") : result.language === "Hindi" ? `उपलब्ध देखभालकर्ता दिखाएँ (${result.care.matched_caregivers.length})` : result.language === "Hinglish" ? `Available caregivers dikhayein (${result.care.matched_caregivers.length})` : `Show available caregivers (${result.care.matched_caregivers.length})`}
                </button>
                {showCaregivers && <div className="grid" style={{ marginTop: 16 }}>{result.care.matched_caregivers.map((caregiver) => (
                      <div key={caregiver.caregiver_id} style={{ border: "1px solid #e4ece9", borderRadius: 15, padding: 16, display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
                        <div><strong>{caregiver.caregiver_id}</strong><div className="muted" style={{ fontSize: 14, marginTop: 4 }}>{caregiver.reason}</div></div>
                        <div style={{ textAlign: "right" }}><span className="pill">{caregiver.score.toFixed(2)}</span><br /><button onClick={() => { setToast("Booking will be available soon."); setTimeout(() => setToast(""), 2600); }} style={{ border: 0, background: "none", color: "var(--teal)", fontWeight: 700, cursor: "pointer", marginTop: 8 }}>Book</button></div>
                      </div>
                ))}</div>}
              </>}
            </article>
          ) : null}
        </section>
      )}
      <div ref={conversationEndRef} aria-hidden="true" style={{ order: 2, height: 1 }} />
      {toast && <div role="status" className="pill" style={{ position: "fixed", bottom: 20, left: "50%", transform: "translateX(-50%)", padding: 14 }}>{toast}</div>}
    </main>
  );
}

