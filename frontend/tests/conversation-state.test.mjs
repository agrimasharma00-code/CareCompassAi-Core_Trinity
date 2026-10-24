import test from "node:test";
import assert from "node:assert/strict";
import { persistConversation, restoreConversation } from "../lib/conversation-state.mjs";

test("chat history restores after a page reload", () => {
  const values = new Map();
  const storage = { getItem: (key) => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) };
  const turns = [
    { role: "user", content: "मुझे सिरदर्द है" },
    { role: "assistant", content: "ऑनलाइन डॉक्टर से परामर्श", display: { mode: "care", care_context: { care_type: "teleconsultation" } } },
  ];
  assert.equal(persistConversation(storage, "chat", turns), true);
  assert.deepEqual(restoreConversation(storage, "chat"), turns);
});

test("chat history storage failures are handled", () => {
  const unavailable = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } };
  assert.deepEqual(restoreConversation(unavailable, "chat"), []);
  assert.equal(persistConversation(unavailable, "chat", []), false);
});
