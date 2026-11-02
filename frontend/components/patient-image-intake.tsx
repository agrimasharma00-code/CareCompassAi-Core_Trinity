"use client";

import { ChangeEvent, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { API_BASE_URL } from "../lib/api";

type Box = { x: number; y: number; w: number; h: number };
type Prediction = { brand: string; generic?: string; confidence?: number };
type RxResult = { status?: string; message?: string; results?: { top_predictions: Prediction[]; confidence: number }[]; disclaimer?: string };
type SkinResult = { status?: string; message?: string; risk?: string; kind?: string; image_quality?: string; findings?: string[]; plain_explanation?: string; disclaimers?: string[]; top_prediction?: { name: string; confidence: number }; top_predictions?: { name: string; confidence: number }[]; gradcam_png_base64?: string | null; disclaimer?: string };

const token = () => typeof window === "undefined" ? "" : sessionStorage.getItem("niramaya_demo_token") ?? "";
const headers = () => ({ Authorization: `Bearer ${token()}` });

export default function PatientImageIntake() {
  const [skinFile, setSkinFile] = useState<File | null>(null);
  const [skin, setSkin] = useState<SkinResult | null>(null);
  const [rxFile, setRxFile] = useState<File | null>(null);
  const [boxes, setBoxes] = useState<Box[]>([]);
  const [imageSize, setImageSize] = useState({ width: 0, height: 0 });
  const [manualBox, setManualBox] = useState<Box>({ x: 0, y: 0, w: 180, h: 48 });
  const [rx, setRx] = useState<RxResult | null>(null);
  const [medicines, setMedicines] = useState<string[]>([""]);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState<string[]>([]);
  const skinUrl = useMemo(() => skinFile ? URL.createObjectURL(skinFile) : "", [skinFile]);
  const rxUrl = useMemo(() => rxFile ? URL.createObjectURL(rxFile) : "", [rxFile]);
  useEffect(() => () => { if (skinUrl) URL.revokeObjectURL(skinUrl); if (rxUrl) URL.revokeObjectURL(rxUrl); }, [skinUrl, rxUrl]);

  async function uploadSkin() {
    if (!skinFile) return;
    setBusy(true); setStatus("");
    try {
      const form = new FormData(); form.append("image", skinFile);
      const response = await fetch(`${API_BASE_URL}/api/v1/intake/skin-check`, { method: "POST", headers: headers(), body: form });
      const data = await response.json(); if (!response.ok) throw new Error(data.detail || "Skin image could not be checked.");
      if (data.status === "model_missing" || data.status === "ml_unavailable") {
        const fallback = new FormData(); fallback.append("file", skinFile); fallback.append("lang", "auto"); fallback.append("note", "Describe the visible medical image without diagnosing.");
        const visionResponse = await fetch(`${API_BASE_URL}/api/v1/pathovision`, { method: "POST", body: fallback });
        const vision = await visionResponse.json();
        if (!visionResponse.ok) throw new Error(vision.detail || "No image model is available. Configure OPENAI_API_KEY with a vision model or ANTHROPIC_API_KEY on the backend; Sarvam text models cannot inspect images.");
        setSkin({ ...vision, status: "vision" }); setStatus("General image description ready. It is not a diagnosis and must be checked by a clinician.");
      } else {
        setSkin(data); setStatus("Skin screening result ready. This is not a diagnosis.");
      }
    } catch (error) { setStatus(error instanceof Error ? error.message : "Skin image could not be checked."); }
    finally { setBusy(false); }
  }

  async function segmentRx() {
    if (!rxFile) return;
    setBusy(true); setStatus("");
    try {
      const form = new FormData(); form.append("image", rxFile);
      const response = await fetch(`${API_BASE_URL}/api/v1/intake/prescription/segment`, { method: "POST", headers: headers(), body: form });
      const data = await response.json(); if (!response.ok) throw new Error(data.detail || "Could not inspect prescription image.");
      setBoxes(data.boxes ?? []); setImageSize({ width: data.image_width || 0, height: data.image_height || 0 }); setStatus(data.message || "Review the medicine-name boxes, then read or enter them manually."); setRx(null);
    } catch (error) { setStatus(error instanceof Error ? error.message : "Could not inspect prescription image."); }
    finally { setBusy(false); }
  }

  async function readRx() {
    if (!rxFile || !boxes.length) { setStatus("Upload a prescription and add at least one medicine-name crop."); return; }
    setBusy(true);
    try {
      const form = new FormData(); form.append("image", rxFile); form.append("boxes", JSON.stringify(boxes));
      const response = await fetch(`${API_BASE_URL}/api/v1/intake/prescription/predict`, { method: "POST", headers: headers(), body: form });
      const data = await response.json() as RxResult; if (!response.ok) throw new Error((data as {detail?: string}).detail || "Could not read prescription crops.");
      setRx(data);
      if (data.results?.length) setMedicines(data.results.map((item) => item.top_predictions?.[0]?.brand ?? ""));
      setStatus(data.status === "model_missing" ? "No trained reader is installed. Enter the names below from the prescription." : "Check every suggested name against the prescription before saving.");
    } catch (error) { setStatus(error instanceof Error ? error.message : "Could not read prescription crops."); }
    finally { setBusy(false); }
  }

  async function saveMeds() {
    const names = medicines.map((name) => name.trim()).filter(Boolean);
    if (!names.length) { setStatus("Enter or confirm at least one medicine name first."); return; }
    setBusy(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/intake/medications/confirm`, { method: "POST", headers: { ...headers(), "Content-Type": "application/json" }, body: JSON.stringify({ medications: names.map((brand, i) => { const candidate = rx?.results?.[i]?.top_predictions?.[0]?.brand; return { brand, source: candidate ? (candidate.toLowerCase() === brand.toLowerCase() ? "ai_confirmed" : "ai_corrected") : "manual", ai_confidence: rx?.results?.[i]?.confidence ?? null }; }) }) });
      const data = await response.json(); if (!response.ok) throw new Error(data.detail || "Medication list could not be saved.");
      sessionStorage.setItem("niramaya_confirmed_meds", JSON.stringify(names));
      setSaved(names); setStatus("Confirmed medicines saved to your care handoff.");
    } catch (error) { setStatus(error instanceof Error ? error.message : "Medication list could not be saved."); }
    finally { setBusy(false); }
  }

  function choose(file: File | undefined, setter: (file: File | null) => void) { setter(file ?? null); }
  return <section className="card" style={{ marginTop: 24, padding: 22 }}>
    <span className="eyebrow">Optional image intake</span><h2 style={{ margin: "8px 0" }}>Add context for your care conversation</h2>
    <p className="muted" style={{ lineHeight: 1.55 }}>Upload a skin image for a screening aid, or a prescription to help list medicine names. Image suggestions are not diagnoses or prescriptions; verify them yourself.</p>
    {!token() && <p role="note">Sign in to save private intake details. <Link href="/login/patient">Patient sign-in →</Link></p>}
    <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(280px,1fr))", marginTop: 18 }}>
      <article style={{ border: "1px solid #dce7e4", borderRadius: 15, padding: 16 }}><h3 style={{ marginTop: 0 }}>Medical image description / skin screening</h3><p className="muted" style={{ fontSize: 13 }}>For a general description, the selected image is sent to the configured OpenAI vision API and is not saved by Niramaya. HAM10000 CNN weights, when trained, cover only a small set of dermatoscopic lesion classes; they cannot classify every skin or medical image.</p><input type="file" accept="image/jpeg,image/png,image/webp" onChange={(e: ChangeEvent<HTMLInputElement>) => { choose(e.target.files?.[0], setSkinFile); setSkin(null); }} />{skinUrl && <img src={skinUrl} alt="Selected medical image" style={{ width: "100%", maxHeight: 190, objectFit: "contain", marginTop: 12, borderRadius: 10 }} />}<button className="button" style={{ marginTop: 12 }} disabled={!skinFile || busy} onClick={uploadSkin}>{busy ? "Reviewing…" : "Describe / review image"}</button>{skin && <div style={{ marginTop: 12 }}><strong>{skin.status === "ok" ? skin.risk?.replaceAll("_", " ") : skin.status === "vision" ? (skin.kind || "Medical image").replaceAll("_", " ") : "Image could not be analyzed"}</strong>{skin.status === "vision" && <><p>{skin.plain_explanation}</p>{skin.image_quality && <p>Image quality: {skin.image_quality}</p>}{skin.findings?.length ? <><b>Visible details</b><ul>{skin.findings.map((finding, index) => <li key={index}>{finding}</li>)}</ul></> : null}{skin.disclaimers?.map((item, index) => <small key={index} style={{ display: "block", marginTop: 5 }}>{item}</small>)}</>}{skin.status !== "vision" && <><p>{skin.top_prediction ? `${skin.top_prediction.name} · ${Math.round(skin.top_prediction.confidence * 100)}% model confidence` : skin.message}</p>{skin.gradcam_png_base64 && <img alt="Model attention visualization" src={`data:image/png;base64,${skin.gradcam_png_base64}`} style={{ width: "100%", borderRadius: 8 }} />}<small>{skin.disclaimer}</small></>}</div>}</article>
      <article style={{ border: "1px solid #dce7e4", borderRadius: 15, padding: 16 }}><h3 style={{ marginTop: 0 }}>Prescription medicine names</h3><input type="file" accept="image/jpeg,image/png,image/webp" onChange={(e: ChangeEvent<HTMLInputElement>) => { choose(e.target.files?.[0], setRxFile); setBoxes([]); setRx(null); }} />{rxUrl && <><img src={rxUrl} alt="Uploaded prescription" style={{ width: "100%", maxHeight: 260, objectFit: "contain", borderRadius: 10, marginTop: 12 }} /><button className="button" style={{ marginTop: 10 }} disabled={busy} onClick={segmentRx}>Find word crops</button></>}
        {imageSize.width > 0 && <div style={{ marginTop: 10 }}><strong>{boxes.length} word crops · original image {imageSize.width} × {imageSize.height}</strong><p className="muted" style={{ fontSize: 13 }}>Remove false crops or add a box by entering its position on the original image.</p>{boxes.map((box, i) => <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "5px 0" }}>Crop {i + 1}: x {box.x}, y {box.y}, {box.w} × {box.h} <button type="button" onClick={() => setBoxes(boxes.filter((_, index) => index !== i))}>Remove</button></div>)}<div style={{ display: "flex", gap: 5, flexWrap: "wrap", marginTop: 8 }}>{(["x", "y", "w", "h"] as const).map((key) => <label key={key} style={{ fontSize: 12 }}>{key}<input type="number" min={0} value={manualBox[key]} onChange={(e) => setManualBox({ ...manualBox, [key]: Math.max(0, Number(e.target.value)) })} style={{ display: "block", width: 70, padding: 6 }} /></label>)}<button type="button" onClick={() => { if (manualBox.w && manualBox.h) setBoxes([...boxes, manualBox].slice(0, 20)); }}>Add crop</button></div>{boxes.length > 0 && <button className="button" style={{ marginTop: 8 }} disabled={busy} onClick={readRx}>Suggest medicine names</button>}</div>}
        <div style={{ marginTop: 12 }}><strong>Review / enter medicine names</strong>{medicines.map((name, i) => <div key={i} style={{ display: "flex", gap: 8, marginTop: 7 }}><input aria-label={`Medicine name ${i + 1}`} value={name} onChange={(e) => setMedicines(medicines.map((value, index) => index === i ? e.target.value : value))} placeholder="Medicine name" style={{ flex: 1, minWidth: 0, padding: 9, border: "1px solid #dce7e4", borderRadius: 8 }} /><button type="button" onClick={() => setMedicines(medicines.length > 1 ? medicines.filter((_, index) => index !== i) : [""])}>Remove</button></div>)}<button type="button" style={{ marginTop: 8 }} onClick={() => setMedicines([...medicines, ""])}>+ Add medicine</button><button className="button" style={{ display: "block", marginTop: 10 }} onClick={saveMeds} disabled={busy}>Confirm medicines</button>{saved.length > 0 && <p>Saved: {saved.join(", ")}</p>}{rx?.disclaimer && <small>{rx.disclaimer}</small>}</div>
      </article>
    </div>{status && <p role="status" aria-live="polite" style={{ marginBottom: 0, color: "#345" }}>{status}</p>}
  </section>;
}
