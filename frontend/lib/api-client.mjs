/** @template T @typedef {{ok: true, data: T} | {ok: false, error: string, retryable: boolean}} ApiResult */

/** @param {string} url @param {RequestInit} init @param {number} timeoutMs @returns {Promise<ApiResult<unknown>>} */
export async function boundedFetch(url, init = {}, timeoutMs = 15_000) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { ...init, signal: controller.signal });
    const raw = await response.text();
    let payload = null;
    if (raw) { try { payload = JSON.parse(raw); } catch { payload = { detail: raw }; } }
    if (!response.ok) {
      const detail = payload && typeof payload === "object" ? payload.detail ?? payload.message : null;
      return { ok: false, error: typeof detail === "string" ? detail : `Request failed (${response.status})`, retryable: response.status === 408 || response.status === 429 || response.status >= 500 };
    }
    return { ok: true, data: payload };
  } catch (error) {
    const timedOut = error instanceof DOMException && error.name === "AbortError";
    return { ok: false, error: timedOut ? "The request timed out. Please try again." : "Could not connect. Please try again.", retryable: true };
  } finally { clearTimeout(timeout); }
}
