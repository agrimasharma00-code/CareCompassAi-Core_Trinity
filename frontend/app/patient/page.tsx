"use client";

import { useEffect, useRef, useState, type CSSProperties, type FormEvent, type KeyboardEvent } from "react";
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
  safety_net?: string | null;
  why_not?: string | null;
};
type CareContext = { care_type: string; urgency: string; reasoning: string; symptoms: string[] };
type VoiceLanguage = "hi-IN" | "en-IN";
type AssistantLanguage = "Hindi" | "Hinglish" | "English";
type AuthUser = { username: string; name: string; role: "patient" | "dispatch" | "provider"; caregiver_id: string | null };
type Booking = { id: number; caregiver_id: string; slot: string; care_type: string; urgency: string; handoff_summary: string; state: string; proposed_slot: string | null };
type CheckIn = { id: number; booking_id: number; state: string; answer: string | null };
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

function appointmentSlots(reason: string): { value: string; label: string }[] {
  const window = reason.match(/free\s+(\d{2}:\d{2})[–-](\d{2}:\d{2})/i);
  if (!window) return [];
  const [startHour, startMinute] = window[1].split(":").map(Number);
  const [endHour, endMinute] = window[2].split(":").map(Number);
  const now = Date.now();
  const slots: { value: string; label: string }[] = [];
  const dateParts = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata", year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(new Date());
  const datePart = (type: string) => dateParts.find((part) => part.type === type)?.value || "";
  const today = new Date(Date.UTC(Number(datePart("year")), Number(datePart("month")) - 1, Number(datePart("day"))));
  const start = startHour * 60 + startMinute;
  const end = endHour * 60 + endMinute;
  for (let day = 0; day < 7; day += 1) {
    const date = new Date(today.getTime() + day * 86_400_000).toISOString().slice(0, 10);
    for (let minute = start; minute < end; minute += 30) {
      const time = `${String(Math.floor(minute / 60)).padStart(2, "0")}:${String(minute % 60).padStart(2, "0")}`;
      const value = `${date}T${time}:00+05:30`;
      if (new Date(value).getTime() <= now) continue;
      slots.push({ value, label: `${date} · ${time} IST` });
    }
  }
  return slots;
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
  const composerRef = useRef<HTMLElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState("");
  const [error, setError] = useState("");
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [readAloud, setReadAloud] = useState(false);
  const [voiceInputLanguage, setVoiceInputLanguage] = useState<VoiceLanguage>("hi-IN");
  const [locationOpen, setLocationOpen] = useState(false);
  const [composerHeight, setComposerHeight] = useState(118);
  const hasUsedMicRef = useRef(false);
  const [authUser, setAuthUser] = useState<AuthUser | null>(null);
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [checkins, setCheckins] = useState<CheckIn[]>([]);
  const [dispatchAlertBusy, setDispatchAlertBusy] = useState(false);
  const [dispatchAlertMessage, setDispatchAlertMessage] = useState("");
  const [dispatchAlertStatus, setDispatchAlertStatus] = useState("");
  const [bookingCaregiver, setBookingCaregiver] = useState<string | null>(null);
  const [bookingSlot, setBookingSlot] = useState("");
  const [bookingBusy, setBookingBusy] = useState(false);
  const [bookingError, setBookingError] = useState("");
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

  useEffect(() => {
    try {
      const stored = localStorage.getItem("carecompass_voice_language");
      if (stored === "hi-IN" || stored === "en-IN") setVoiceInputLanguage(stored);
    } catch { /* Keep Hindi as the default when browser storage is unavailable. */ }
  }, []);

  useEffect(() => {
    const composer = composerRef.current;
    if (!composer || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => setComposerHeight(Math.ceil(composer.getBoundingClientRect().height)));
    observer.observe(composer);
    setComposerHeight(Math.ceil(composer.getBoundingClientRect().height));
    return () => observer.disconnect();
  }, []);

  function chooseVoiceLanguage(language: VoiceLanguage) {
    setVoiceInputLanguage(language);
    try { localStorage.setItem("carecompass_voice_language", language); } catch { /* Storage is optional. */ }
  }

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
      if (inputRef.current) inputRef.current.style.height = "44px";
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
    if (!hasUsedMicRef.current) {
      hasUsedMicRef.current = true;
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
      form.append("language_code", voiceInputLanguage);
      const response = await fetch(`${API_BASE_URL}/api/v1/voice/stt`, { method: "POST", body: form });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = typeof payload.detail === "string" ? payload.detail : "Voice transcription is unavailable.";
        throw new Error(detail);
      }
      const transcript = typeof payload.transcript === "string" ? payload.transcript.trim() : "";
      if (!transcript) throw new Error("No speech was detected. Please try again or type your request.");
      setInput(transcript);
      await submitText(transcript, payload.language_code || voiceInputLanguage);
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
    const refreshAuth = () => {
      const token = localStorage.getItem("carecompass_token");
      if (!token) { setAuthUser(null); return; }
      fetch(`${API_BASE_URL}/api/v1/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
        .then((response) => response.ok ? response.json() : Promise.reject(new Error("expired")))
        .then((user: AuthUser) => setAuthUser(user))
        .catch(() => {
          localStorage.removeItem("carecompass_token");
          localStorage.removeItem("carecompass_user");
          setAuthUser(null);
        });
    };
    refreshAuth();
    window.addEventListener("storage", refreshAuth);
    return () => window.removeEventListener("storage", refreshAuth);
  }, []);

  useEffect(() => {
    if (!authUser || authUser.role !== "patient") { setBookings([]); return; }
    const token = localStorage.getItem("carecompass_token");
    if (!token) return;
    fetch(`${API_BASE_URL}/api/v1/bookings/mine`, { headers: { Authorization: `Bearer ${token}` } })
      .then((response) => response.ok ? response.json() : Promise.reject(new Error("Could not load bookings")))
      .then((items: Booking[]) => setBookings(items))
      .catch(() => setBookingError("Could not load your booking status. Refresh to try again."));
    fetch(`${API_BASE_URL}/api/v1/checkins/mine`, { headers: { Authorization: `Bearer ${token}` } }).then((r) => r.ok ? r.json() : []).then(setCheckins).catch(() => setCheckins([]));
    fetch(`${API_BASE_URL}/api/v1/alerts/mine`, { headers: { Authorization: `Bearer ${token}` } }).then((r) => r.ok ? r.json() : []).then((items: { status: string }[]) => { if (items[0]) setDispatchAlertStatus(items[0].status); }).catch(() => undefined);
  }, [authUser]);

  useEffect(() => {
    if (!authUser) return;
    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let stopped = false;
    let retry = 0;
    const connect = () => {
      if (stopped) return;
      const token = localStorage.getItem("carecompass_token");
      if (!token) return;
      socket = new WebSocket(`${API_BASE_URL.replace(/^http/, "ws")}/ws?token=${encodeURIComponent(token)}`);
      socket.onopen = () => { retry = 0; };
      socket.onmessage = (event) => {
        try {
          const update = JSON.parse(event.data);
          if (update.booking && authUser.role === "patient") {
            const booking = update.booking as Booking;
            setBookings((current) => [booking, ...current.filter((item) => item.id !== booking.id)]);
          }
          if (update.alert && authUser.role === "patient") setDispatchAlertStatus(update.alert.status);
          if (update.checkin?.emergency && authUser.role === "patient") setDispatchAlertMessage("Please call 112 now. You can also alert the demo dispatch desk.");
        } catch { /* Ignore malformed updates and keep the live connection. */ }
      };
      socket.onclose = () => {
        if (stopped) return;
        const delay = Math.min(30_000, 500 * (2 ** Math.min(retry, 6)));
        retry += 1;
        reconnectTimer = window.setTimeout(connect, delay);
      };
    };
    connect();
    return () => {
      stopped = true;
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [authUser]);

  function logout() {
    localStorage.removeItem("carecompass_token");
    localStorage.removeItem("carecompass_user");
    setAuthUser(null);
    setBookings([]);
  }

  function openBooking(caregiverId: string) {
    setBookingError("");
    setBookingSlot("");
    if (!authUser || authUser.role !== "patient") {
      setBookingCaregiver(caregiverId);
      setBookingError("Sign in as a demo patient to request this booking. Your intake stays open in this tab.");
      return;
    }
    setBookingCaregiver(caregiverId);
  }

  async function confirmBooking() {
    if (!result?.care || !result.care_context || !bookingCaregiver || !bookingSlot) return;
    const token = localStorage.getItem("carecompass_token");
    if (!token) { setBookingError("Please sign in as a patient to request this booking."); return; }
    setBookingBusy(true);
    setBookingError("");
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/bookings`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
          body: JSON.stringify({ caregiver_id: bookingCaregiver, slot: bookingSlot, triage: result.care, care_context: result.care_context, history, patient_latitude: Number(lat), patient_longitude: Number(lng) }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Could not request this booking.");
      setBookings((current) => [payload as Booking, ...current.filter((item) => item.id !== payload.id)]);
      setBookingCaregiver(null);
      setBookingSlot("");
    } catch (err) {
      setBookingError(err instanceof Error ? err.message : "Could not request this booking.");
    } finally {
      setBookingBusy(false);
    }
  }

  async function alertDispatch() {
    const token = localStorage.getItem("carecompass_token");
    if (!token) { setDispatchAlertMessage("Sign in as a patient to alert the demo dispatch desk."); return; }
    setDispatchAlertBusy(true); setDispatchAlertMessage("");
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/alerts`, { method: "POST", headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" }, body: JSON.stringify({ latitude: Number(lat), longitude: Number(lng), red_flags: result?.care?.red_flags || [], summary: history.filter((turn) => turn.role === "user").slice(-3).map((turn) => turn.content).join("; ").slice(0, 490) || result?.message || "Emergency concern" }) });
      const payload = await response.json(); if (!response.ok) throw new Error(payload.detail || "Could not alert demo dispatch.");
      setDispatchAlertMessage(result?.language === "Hindi" ? `डेमो डिस्पैच डेस्क को सूचना मिली · स्थिति: ${payload.status}। यह एम्बुलेंस सेवा नहीं है; आपात स्थिति में 112 पर कॉल करें।` : result?.language === "Hinglish" ? `Demo dispatch desk ko alert mila · status ${payload.status}. Yeh ambulance nahi hai; emergency mein 112 par call karein.` : `Demo dispatch desk alerted · status ${payload.status}. This is not an ambulance service; keep 112 as your emergency contact.`);
      setDispatchAlertStatus(payload.status);
    } catch (error) { setDispatchAlertMessage(error instanceof Error ? error.message : "Could not alert demo dispatch."); }
    finally { setDispatchAlertBusy(false); }
  }

  async function simulateCheckIn(checkin: CheckIn, answer: string) {
    const token = localStorage.getItem("carecompass_token"); if (!token) return;
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/checkins/${checkin.id}/simulate`, { method: "POST", headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" }, body: JSON.stringify({ answer }) });
      const payload = await response.json(); if (!response.ok) throw new Error(payload.detail || "Check-in failed.");
      setCheckins((items) => items.map((item) => item.id === checkin.id ? { ...item, state: payload.state, answer } : item));
      if (payload.emergency) { setResult((current) => current ? { ...current, mode: "emergency", message: current.language === "Hindi" ? "यह आपातकाल हो सकता है। कृपया अभी 112 पर कॉल करें।" : current.language === "Hinglish" ? "Yeh emergency ho sakti hai. Kripya abhi 112 par call karein." : "This may be an emergency. Please call 112 now.", care: payload.care } : current); setDispatchAlertMessage(result?.language === "Hindi" ? "कृपया अभी 112 पर कॉल करें। आप डेमो डिस्पैच डेस्क को भी अलर्ट कर सकती हैं।" : result?.language === "Hinglish" ? "Kripya abhi 112 par call karein. Aap demo dispatch desk ko bhi alert kar sakti hain." : payload.message); }
      else setToast(result?.language === "Hindi" ? (answer === "same" ? "आपकी मौजूदा बुकिंग जारी है।" : "आपके बेहतर महसूस करने की जानकारी दर्ज हो गई है।") : result?.language === "Hinglish" ? (answer === "same" ? "Aapki booking jaari hai." : "Aapke behtar mehsoos karne ki baat note kar li.") : payload.message);
    } catch (error) { setBookingError(error instanceof Error ? error.message : "Check-in failed."); }
  }

  useEffect(() => {
    if (history.length) window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "smooth" });
  }, [history, result, composerHeight]);

  const emergency = result?.mode === "emergency" || result?.care?.care_type === "emergency_112";
  const responseLanguage: VoiceLanguage = result?.language === "Hindi" || result?.language === "Hinglish" ? "hi-IN" : "en-IN";
  const recordingStatus = recording ? `Listening… ${formatTimer(recordingSeconds)} / 0:30` : "";

  return (
    <main className="container patient-layout" style={{ maxWidth: 850, "--composer-height": `${composerHeight}px` } as CSSProperties}>
      <Link href="/" style={{ color: "var(--teal)", textDecoration: "none", fontWeight: 700 }}>← CareCompass</Link>
      <div style={{ display: "flex", justifyContent: "flex-end", marginTop: -26 }}>
        {authUser ? <button type="button" className="pill" onClick={logout}>Log out · {authUser.name}</button> : <Link href="/login" className="pill" style={{ textDecoration: "none" }}>Demo login</Link>}
      </div>
      <span className="eyebrow" style={{ display: "block", marginTop: 42 }}>Care intake</span>
      <h1 style={{ fontSize: "clamp(36px, 6vw, 56px)", margin: "10px 0" }}>Let’s find the right care.</h1>
      <p className="muted" style={{ fontSize: 17 }}>Share what support you need. This service routes care and does not diagnose or prescribe.</p>

      <section ref={composerRef} className="card patient-composer">
        {locationOpen && <div className="location-popover" role="dialog" aria-label="Location settings">
          <button type="button" className="button location-use" onClick={useLocation}>Use my location</button>
          <label>Latitude<input aria-label="Latitude" inputMode="decimal" value={lat} onChange={(event) => setLat(event.target.value)} /></label>
          <label>Longitude<input aria-label="Longitude" inputMode="decimal" value={lng} onChange={(event) => setLng(event.target.value)} /></label>
        </div>}
        {(recording || transcribing) && <p className={`voice-status${recording ? " is-recording" : ""}`} role="status" aria-live="polite">{recording ? recordingStatus : "Transcribing…"}</p>}
        <form onSubmit={send}>
          <div className="composer-row">
            <textarea
              ref={inputRef}
              id="message"
              aria-label="What’s going on?"
              value={input}
              onChange={(event) => {
                setInput(event.target.value);
                event.target.style.height = "44px";
                event.target.style.height = `${Math.min(event.target.scrollHeight, 120)}px`;
              }}
              onKeyDown={(event: KeyboardEvent<HTMLTextAreaElement>) => {
                if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void submitText(input); }
              }}
              placeholder={voiceInputLanguage === "hi-IN" ? "अपनी परेशानी लिखें…" : "Type your request…"}
              rows={1}
              disabled={busy || transcribing}
              className="message-input"
            />
            <button type="button" className={`mic-button${recording ? " is-recording" : ""}`} aria-label="Speak your request" aria-pressed={recording} title={recording ? "Stop recording" : "Speak your request"} onClick={() => recording ? void stopRecording() : void startRecording()} disabled={busy || transcribing}>
              <span aria-hidden="true">{recording ? "■" : "🎙"}</span>
            </button>
            <button type="submit" className="send-button" aria-label="Send request" title="Send request" disabled={busy || transcribing || recording || !input.trim()}>{busy ? "…" : "➤"}</button>
          </div>
          <div className="composer-toolbar">
            <div className="language-toggle" role="group" aria-label="Speech input language">
              <button type="button" aria-pressed={voiceInputLanguage === "hi-IN"} onClick={() => chooseVoiceLanguage("hi-IN")}>हिंदी</button>
              <button type="button" aria-pressed={voiceInputLanguage === "en-IN"} onClick={() => chooseVoiceLanguage("en-IN")}>English</button>
            </div>
            <button type="button" className="toolbar-chip" aria-expanded={locationOpen} onClick={() => setLocationOpen((open) => !open)}>📍 Location</button>
            <button type="button" className="icon-toggle" aria-label={readAloud ? "Turn read aloud off" : "Turn read aloud on"} aria-pressed={readAloud} title={readAloud ? "Turn read aloud off" : "Turn read aloud on"} onClick={() => setReadAloud((enabled) => !enabled)}>{readAloud ? "🔊" : "🔇"}</button>
          </div>
        </form>
        {error && <p role="alert" className="composer-error">{error}</p>}
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
              <button type="button" className="button" disabled={dispatchAlertBusy} onClick={() => void alertDispatch()} style={{ display: "block", background: "#741722", marginBottom: 16 }}>{result.language === "Hindi" ? "डेमो डिस्पैच डेस्क को अलर्ट करें (112 के अलावा)" : result.language === "Hinglish" ? "Demo dispatch desk ko alert karein (112 ke alawa)" : "Alert demo dispatch desk (in addition to 112)"}</button>
              <small style={{ display: "block", marginBottom: 12 }}>{result.language === "Hindi" ? "यह केवल डेमो डिस्पैच है, एम्बुलेंस नहीं; 112 का विकल्प नहीं है।" : result.language === "Hinglish" ? "Yeh sirf demo dispatch hai, ambulance nahi; 112 ka replacement nahi." : "Demo dispatch only; this is not an ambulance and does not replace 112."}</small>
              {dispatchAlertMessage && <p role="status">{dispatchAlertMessage}</p>}
              {dispatchAlertStatus && <p role="status">{result.language === "Hindi" ? `डेमो डिस्पैच स्थिति: ${dispatchAlertStatus}` : result.language === "Hinglish" ? `Demo dispatch status: ${dispatchAlertStatus}` : `Demo dispatch status: ${dispatchAlertStatus}`}</p>}
              <h2 style={{ fontSize: 30, margin: "0 0 8px" }}>{result.message}</h2>
              <p style={{ margin: 0 }}>{result.language === "Hindi" ? "यह ऐप आपकी ओर से आपातकालीन सेवाओं को कॉल नहीं कर सकती।" : result.language === "Hinglish" ? "Yeh app aapki taraf se emergency services ko call nahi kar sakti." : "CareCompass cannot call emergency services for you."}</p>
              {(result.care?.red_flags || []).length > 0 && <p>{result.language === "Hindi" ? "खतरे के संकेत:" : result.language === "Hinglish" ? "Khatre ke signs:" : "Red flags:"} {result.care?.red_flags.map((flag) => (result.language === "Hindi" ? hindiRedFlagLabels[flag] : result.language === "Hinglish" ? hinglishRedFlagLabels[flag] : redFlagLabels[flag]) || flag).join(", ")}</p>}
            </div>
          ) : result.mode === "care" && result.care ? (
            <article className="card" style={{ padding: 24 }}>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                <h2 style={{ margin: "0 auto 0 0", fontSize: 27 }}>{plainCareValue(result.care.care_type, result.language)}</h2>
                <span className="pill">{plainUrgency(result.care.urgency, result.language)}</span>
                <button type="button" className="speaker-button" aria-label="Read care summary aloud" title="Read care summary aloud" onClick={() => void playSpeech(spokenSummary(result), responseLanguage, true)}>🔊</button>
              </div>
              <p className="muted" style={{ lineHeight: 1.6 }}>{plainReasoning(result.care.reasoning, result.language, result.care.care_type, result.care.urgency)}</p>
              {result.why_not && <p style={{ whiteSpace: "pre-line", lineHeight: 1.55 }}><strong>{result.language === "Hindi" ? "अन्य विकल्प" : result.language === "Hinglish" ? "Dusre options" : "Why other options were not selected"}:</strong> {result.why_not}</p>}
              {result.safety_net && <p className="pill" style={{ display: "block", whiteSpace: "normal", lineHeight: 1.5, padding: 12 }}>{result.safety_net}</p>}
              {result.care.red_flags.length > 0 && <p style={{ color: "#a91e2a", fontWeight: 700 }}>{result.language === "Hindi" ? "खतरे के संकेत:" : result.language === "Hinglish" ? "Khatre ke signs:" : "Red flags:"} {result.care.red_flags.map((flag) => (result.language === "Hindi" ? hindiRedFlagLabels[flag] : result.language === "Hinglish" ? hinglishRedFlagLabels[flag] : redFlagLabels[flag]) || flag).join(", ")}</p>}
              {result.care.matched_caregivers.length > 0 && <>
                <button type="button" className="button" aria-expanded={showCaregivers} onClick={() => setShowCaregivers((visible) => !visible)} style={{ marginTop: 10 }}>
                  {showCaregivers ? (result.language === "Hindi" ? "उपलब्ध देखभालकर्ता छिपाएँ" : result.language === "Hinglish" ? "Available caregivers chhupayein" : "Hide available caregivers") : result.language === "Hindi" ? `उपलब्ध देखभालकर्ता दिखाएँ (${result.care.matched_caregivers.length})` : result.language === "Hinglish" ? `Available caregivers dikhayein (${result.care.matched_caregivers.length})` : `Show available caregivers (${result.care.matched_caregivers.length})`}
                </button>
                {showCaregivers && <div className="grid" style={{ marginTop: 16 }}>{result.care.matched_caregivers.map((caregiver) => (
                      <div key={caregiver.caregiver_id} style={{ border: "1px solid #e4ece9", borderRadius: 15, padding: 16, display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
                        <div><strong>{caregiver.caregiver_id}</strong><div className="muted" style={{ fontSize: 14, marginTop: 4 }}>{caregiver.reason}</div></div>
                        <div style={{ textAlign: "right" }}><span className="pill">{caregiver.score.toFixed(2)}</span><br /><button type="button" onClick={() => openBooking(caregiver.caregiver_id)} style={{ border: 0, background: "none", color: "var(--teal)", fontWeight: 700, cursor: "pointer", marginTop: 8 }}>Book</button></div>
                        {bookingCaregiver === caregiver.caregiver_id && <div style={{ flexBasis: "100%", display: "grid", gap: 10 }}>
                          {bookingError && <p role="alert" style={{ color: "#a91e2a", margin: 0 }}>{bookingError} {!authUser && <Link href="/login" target="_blank" style={{ color: "inherit", fontWeight: 700 }}>Open demo login</Link>}</p>}
                          {authUser?.role === "patient" && <>
                            <label>Choose an available time
                              <select value={bookingSlot} onChange={(event) => setBookingSlot(event.target.value)} style={{ display: "block", width: "100%", padding: 11, marginTop: 6, border: "1px solid #dce7e4", borderRadius: 10 }}>
                                <option value="">Select a slot (IST)</option>
                                {appointmentSlots(caregiver.reason).map((slot) => <option key={slot.value} value={slot.value}>{slot.label}</option>)}
                              </select>
                            </label>
                            <div style={{ display: "flex", gap: 8 }}><button type="button" className="button" disabled={!bookingSlot || bookingBusy} onClick={() => void confirmBooking()}>{bookingBusy ? "Requesting…" : "Confirm request"}</button><button type="button" className="pill" onClick={() => { setBookingCaregiver(null); setBookingError(""); }}>Cancel</button></div>
                          </>}
                        </div>}
                      </div>
                ))}</div>}
              </>}
              {bookingError && !bookingCaregiver && <p role="alert" style={{ color: "#a91e2a" }}>{bookingError}</p>}
              {bookings.length > 0 && <section aria-label="My bookings" style={{ marginTop: 20 }}><h3>My booking requests</h3>{bookings.map((booking) => <div key={booking.id} className="pill" style={{ display: "block", marginTop: 8, padding: 12 }}><strong>{booking.caregiver_id}</strong> · {new Date(booking.slot).toLocaleString()} · <span>{booking.state === "requested" ? "Waiting for provider confirmation" : booking.state}</span></div>)}</section>}
              {checkins.filter((checkin) => checkin.state === "pending").map((checkin) => <section key={checkin.id} className="pill" style={{ display: "block", marginTop: 12, padding: 14 }}><strong>{result.language === "Hindi" ? "डेमो चेक-इन (6 घंटे बाद)" : result.language === "Hinglish" ? "Demo check-in (6 ghante baad)" : "Simulate check-in (6 hours later)"}</strong><p>{result.language === "Hindi" ? "क्या हालत बिगड़ी है? सांस लेने में तकलीफ़, सीने में दर्द या बेहोशी है?" : result.language === "Hinglish" ? "Kya halat bigdi hai? Saans lene mein takleef, seene mein dard ya behoshi hai?" : "Is it worse? Any breathing difficulty, chest pain or fainting?"}</p><div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>{(["worse", "same", "better"] as const).map((answer) => <button key={answer} className="button" style={{ padding: "9px 14px" }} onClick={() => void simulateCheckIn(checkin, answer)}>{result.language === "Hindi" ? ({ worse: "बिगड़ी", same: "वैसी ही", better: "बेहतर" } as const)[answer] : result.language === "Hinglish" ? ({ worse: "Bigdi", same: "Waisi hi", better: "Behtar" } as const)[answer] : answer[0].toUpperCase() + answer.slice(1)}</button>)}<button className="button" style={{ padding: "9px 14px", background: "#a91e2a" }} onClick={() => void simulateCheckIn(checkin, result.language === "Hindi" ? "हाँ, सीने में दर्द है" : result.language === "Hinglish" ? "Haan, seene mein dard hai" : "Yes, chest pain")}>{result.language === "Hindi" ? "हाँ, खतरे का संकेत" : result.language === "Hinglish" ? "Haan, red flag" : "Yes, red flag"}</button></div></section>)}
            </article>
          ) : null}
          {!emergency && result.mode === "care" && !!result.suggestions.length && <div className="care-suggestions" aria-label="Care options">{result.suggestions.map((suggestion) => <button key={suggestion} type="button" className="pill" disabled={busy || transcribing} onClick={() => void submitText(suggestion)}>{suggestion}</button>)}</div>}
        </section>
      )}
      <div ref={conversationEndRef} aria-hidden="true" style={{ order: 2, height: 1 }} />
      {toast && <div role="status" className="pill" style={{ position: "fixed", bottom: 20, left: "50%", transform: "translateX(-50%)", padding: 14 }}>{toast}</div>}
    </main>
  );
}

