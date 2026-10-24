import test from "node:test";
import assert from "node:assert/strict";
import { alertSummary, absoluteAlertTime, composerBottomPadding, openAlert, relativeAlertTime, splitAlerts } from "../lib/dispatch-state.mjs";

test("alert summary uses structured intake and excludes quick reply text", () => {
  const summary = alertSummary({ symptoms: ["fever"], symptom_text: "fever", who: "self", age_group: "adult", preference: "home_visit" }, ["severe_bleeding"]);
  assert.match(summary, /Symptoms: fever/);
  assert.match(summary, /Red flags: severe bleeding/);
  assert.match(summary, /For: self \(adult\)/);
  assert.doesNotMatch(summary, /Yes, I need care|Home check-up/);
});

test("open alert dedupe ignores closed items and keeps closed feed separate", () => {
  const values = [{ id: 1, status: "closed" }, { id: 2, status: "accepted" }];
  assert.equal(openAlert(values).id, 2);
  assert.deepEqual(splitAlerts(values), { open: [values[1]], closed: [values[0]] });
});

test("alert time is relative with an IST absolute title and composer uses measured height", () => {
  const now = Date.parse("2026-10-25T10:00:00Z");
  assert.equal(relativeAlertTime("2026-10-25T09:58:00Z", now), "2 min ago");
  assert.match(absoluteAlertTime("2026-10-25T09:58:00Z"), /2026/);
  assert.equal(composerBottomPadding(173.2), "174px");
});
