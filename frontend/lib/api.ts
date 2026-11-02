export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

import { boundedFetch } from "./api-client.mjs";

export type ApiResult<T> = { ok: true; data: T } | { ok: false; error: string; retryable: boolean };

/** The shared bounded fetch primitive. Pass 45_000 for uploads and 25_000 for voice. */
export async function apiRequest<T>(path: string, init: RequestInit = {}, timeoutMs = 15_000): Promise<ApiResult<T>> {
  const result = await boundedFetch(path.startsWith("http") ? path : `${API_BASE_URL}${path}`, init, timeoutMs);
  return result as ApiResult<T>;
}
