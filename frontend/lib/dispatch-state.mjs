export function alertSummary(state = {}, flags = []) {
  const symptoms = Array.isArray(state.symptoms) ? state.symptoms : [];
  const symptomText = typeof state.symptom_text === "string" ? state.symptom_text : "";
  const parts = [];
  const cleaned = [...new Set([...symptoms, ...symptomText.split(/[;,]/).map((x) => x.trim()).filter(Boolean)])];
  if (cleaned.length) parts.push(`Symptoms: ${cleaned.join(", ")}`);
  if (!cleaned.length && state.requested_service) parts.push(`Requested service: ${String(state.requested_service).replaceAll("_", " ")}`);
  parts.push(`Red flags: ${[...new Set(flags)].map((x) => x.replaceAll("_", " ")).join(", ") || "Emergency concern"}`);
  if (state.who) parts.push(`For: ${state.who}${state.age_group ? ` (${state.age_group})` : ""}`);
  return parts.join("; ").slice(0, 490);
}

export function openAlert(alerts = []) {
  return alerts.find((alert) => ["new", "accepted", "en_route"].includes(alert.status)) || null;
}

export function splitAlerts(alerts = []) {
  return { open: alerts.filter((alert) => alert.status !== "closed"), closed: alerts.filter((alert) => alert.status === "closed") };
}

export function relativeAlertTime(value, now = Date.now()) {
  const seconds = Math.max(0, Math.floor((now - new Date(value).getTime()) / 1000));
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  return `${Math.floor(seconds / 3600)} h ago`;
}

export function absoluteAlertTime(value) {
  return new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

export function composerBottomPadding(height) { return `${Math.max(0, Math.ceil(height))}px`; }
