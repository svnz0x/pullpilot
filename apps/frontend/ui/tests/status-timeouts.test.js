import test from "node:test";
import assert from "node:assert/strict";

import { bootApp } from "./helpers/boot-app.js";
import { createFetchQueue } from "./helpers/fetch-queue.js";
import { flushTasks } from "./helpers/flush.js";
import { installMockTimers } from "./helpers/mock-timers.js";

test("latest status remains visible until its own timeout", async () => {
  const timers = installMockTimers();
  const { fetch: fetchMock, enqueueResponses, okResponse } = createFetchQueue();

  const authCheckResponse = () => Promise.resolve(new Response(null, { status: 204 }));
  const configPayload = {
    schema: { variables: [] },
    values: { BASE_DIR: "/srv/app", LOG_DIR: "/srv/app/logs" },
  };
  const schedulePayload = { mode: "cron", expression: "0 0 * * *", datetime: "" };
  const logsPayload = { files: [], selected: null, log_dir: "" };

  enqueueResponses([
    authCheckResponse,
    () => okResponse(configPayload),
    () => okResponse(schedulePayload),
    () => okResponse(logsPayload),
  ]);

  await bootApp({ fetchMock });

  const loginForm = document.getElementById("token-form");
  const tokenInput = document.getElementById("token-input");
  const scheduleStatus = document.getElementById("schedule-status");
  const scheduleReset = document.getElementById("reset-schedule");

  tokenInput.value = "demo-token";
  loginForm.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));

  const flushWithTimers = () => timers.flushWith(() => flushTasks());

  await flushWithTimers();
  await flushWithTimers();
  await flushWithTimers();

  let initialSummary = scheduleStatus.querySelector("span")?.textContent ?? "";
  let attempts = 0;
  while (initialSummary !== "Programación cargada correctamente." && attempts < 5) {
    await flushWithTimers();
    initialSummary = scheduleStatus.querySelector("span")?.textContent ?? "";
    attempts += 1;
  }

  const firstSummary = initialSummary;

  timers.advanceTimersBy(100);

  scheduleReset.dispatchEvent(new Event("click", { bubbles: true, cancelable: true }));

  const secondSummary = scheduleStatus.querySelector("span")?.textContent ?? "";

  timers.advanceTimersBy(2401);
  const visibleAfterFirstTimer = scheduleStatus.hidden === false;

  timers.advanceTimersBy(200);
  const hiddenAfterSecondTimer = scheduleStatus.hidden === true;

  assert.equal(firstSummary, "Programación cargada correctamente.");
  assert.equal(secondSummary, "Se restauró la programación cargada.");
  assert.equal(visibleAfterFirstTimer, true);
  assert.equal(hiddenAfterSecondTimer, true);

  timers.restore();
});
