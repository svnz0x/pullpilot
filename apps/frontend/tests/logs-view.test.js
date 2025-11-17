import test from "node:test";
import assert from "node:assert/strict";

import { bootApp } from "./helpers/boot-app.js";
import { createFetchQueue } from "./helpers/fetch-queue.js";
import { flushTasks } from "./helpers/flush.js";

test("logs view loads options and handles refresh failures", async () => {
  const { fetch: fetchMock, enqueueResponses, okResponse, queue } = createFetchQueue();

  const authCheckResponse = () => Promise.resolve(new Response(null, { status: 204 }));
  const configPayload = {
    schema: {
      variables: [
        {
          name: "LOG_DIR",
          type: "string",
          default: "/var/log/app",
          description: "Directorio de logs",
          constraints: { pattern: "^/.+" },
        },
      ],
    },
    values: { LOG_DIR: "/var/log/app" },
  };
  const schedulePayload = { mode: "cron", expression: "0 * * * *", datetime: "" };
  const initialLogsPayload = {
    log_dir: "/var/log/app",
    files: [
      { name: "app.log", modified: "2024-06-20T10:00:00.000Z", size: 4096 },
      { name: "worker.log", modified: "2024-06-20T10:30:00.000Z", size: 2048 },
    ],
    selected: {
      name: "worker.log",
      modified: "2024-06-20T10:30:00.000Z",
      size: 2048,
      content: "línea 1\nlínea 2",
    },
  };

  enqueueResponses([
    authCheckResponse,
    () => okResponse(configPayload),
    () => okResponse(schedulePayload),
    () => okResponse(initialLogsPayload),
  ]);

  await bootApp({ fetchMock });

  const loginForm = document.getElementById("token-form");
  const tokenInput = document.getElementById("token-input");
  const logSelect = document.getElementById("log-select");
  const logContent = document.getElementById("log-content");
  const logMeta = document.getElementById("log-meta");
  const logsStatus = document.getElementById("logs-status");
  const refreshLogs = document.getElementById("refresh-logs");
  const scheduleForm = document.getElementById("schedule-form");
  const saveScheduleButton = document.getElementById("save-schedule");
  const scheduleResetButton = document.getElementById("reset-schedule");

  tokenInput.value = "demo-token";
  loginForm.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  await flushTasks(3);

  const optionsBefore = Array.from(logSelect.options).map((option) => option.value);
  const selectionBefore = logSelect.value;
  const contentBefore = logContent.textContent;
  const metaBefore = logMeta.textContent;

  let resolveScheduleSave;
  enqueueResponses([
    () =>
      new Promise((resolve) => {
        resolveScheduleSave = () =>
          resolve(
            new Response(JSON.stringify({ mode: "cron", expression: "0 * * * *", datetime: "" }), {
              status: 200,
              headers: { "Content-Type": "application/json" },
            }),
          );
      }),
  ]);

  const scheduleButtonsBefore = {
    saveDisabled: saveScheduleButton.disabled,
    resetDisabled: scheduleResetButton.disabled,
    formBusy: scheduleForm.getAttribute("aria-busy"),
  };

  scheduleForm.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));

  const scheduleButtonsDuring = {
    saveDisabled: saveScheduleButton.disabled,
    resetDisabled: scheduleResetButton.disabled,
    formBusy: scheduleForm.getAttribute("aria-busy"),
  };

  resolveScheduleSave();
  await flushTasks(2);

  const scheduleButtonsAfter = {
    saveDisabled: saveScheduleButton.disabled,
    resetDisabled: scheduleResetButton.disabled,
    formBusy: scheduleForm.getAttribute("aria-busy"),
  };

  enqueueResponses([() => Promise.reject(new Error("Network unreachable"))]);

  refreshLogs.dispatchEvent(new Event("click", { bubbles: true }));

  const contentDuringRefresh = logContent.textContent;
  const selectDisabledDuringRefresh = logSelect.disabled;
  const selectBusyDuringRefresh = logSelect.getAttribute("aria-busy");
  const contentBusyDuringRefresh = logContent.getAttribute("aria-busy");
  const refreshDisabledDuringRequest = refreshLogs.disabled;

  await flushTasks(2);

  const optionsAfter = Array.from(logSelect.options).map((option) => option.value);
  const selectionAfter = logSelect.value;
  const contentAfter = logContent.textContent;
  const metaAfter = logMeta.textContent;
  const logsStatusText = logsStatus.textContent;
  const selectBusyAfter = logSelect.getAttribute("aria-busy");
  const contentBusyAfter = logContent.getAttribute("aria-busy");

  assert.deepEqual(optionsBefore, ["app.log", "worker.log"]);
  assert.equal(selectionBefore, "worker.log");
  assert.equal(contentBefore, "línea 1\nlínea 2");
  assert.deepEqual(optionsAfter, optionsBefore);
  assert.equal(selectionAfter, selectionBefore);
  assert.equal(contentAfter, contentBefore);
  assert.equal(metaAfter, metaBefore);
  assert.equal(logsStatusText, "No se pudieron cargar los logs.");

  assert.equal(refreshLogs.disabled, false);
  assert.equal(refreshDisabledDuringRequest, true);
  assert.equal(selectDisabledDuringRefresh, true);
  assert.equal(selectBusyDuringRefresh, "true");
  assert.equal(contentBusyDuringRefresh, "true");
  assert.equal(selectBusyAfter, null);
  assert.equal(contentBusyAfter, null);
  assert.equal(contentDuringRefresh.includes("Cargando"), true);

  assert.deepEqual(scheduleButtonsBefore, {
    saveDisabled: false,
    resetDisabled: false,
    formBusy: null,
  });
  assert.deepEqual(scheduleButtonsDuring, {
    saveDisabled: true,
    resetDisabled: true,
    formBusy: "true",
  });
  assert.deepEqual(scheduleButtonsAfter, {
    saveDisabled: false,
    resetDisabled: false,
    formBusy: null,
  });

  assert.equal(queue.length, 0);
});
