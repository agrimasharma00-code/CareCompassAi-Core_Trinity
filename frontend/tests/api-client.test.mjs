import test from "node:test";
import assert from "node:assert/strict";
import { boundedFetch } from "../lib/api-client.mjs";

test("bounded fetch timeout returns a retryable error result", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (_url, { signal }) => new Promise((_resolve, reject) => {
    signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
  });
  try {
    const result = await boundedFetch("http://test", {}, 2);
    assert.deepEqual(result, { ok: false, error: "The request timed out. Please try again.", retryable: true });
  } finally { globalThis.fetch = originalFetch; }
});
