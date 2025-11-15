import { parentPort } from "node:worker_threads";

import { createAppTestHarness } from "./helpers/app-harness.js";

const {
  loginForm,
  tokenInput,
  logSelect,
  logContent,
  logMeta,
  logsStatus,
  refreshLogs,
  scheduleForm,
  saveScheduleButton,
  scheduleReset: scheduleResetButton,
  enqueueResponses,
  okResponse,
  fetchQueue,
  flush,
  FakeEvent,
} = createAppTestHarness();

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
  values: {
    LOG_DIR: "/var/log/app",
  },
};

const schedulePayload = { mode: "cron", expression: "0 * * * *", datetime: "" };

const initialLogsPayload = {
  log_dir: "/var/log/app",
  files: [
    {
      name: "app.log",
      modified: "2024-06-20T10:00:00.000Z",
      size: 4096,
    },
    {
      name: "worker.log",
      modified: "2024-06-20T10:30:00.000Z",
      size: 2048,
    },
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

await import(new URL("../src/app.js", import.meta.url));

tokenInput.value = "demo-token";
loginForm.dispatchEvent(new FakeEvent("submit", { bubbles: true, cancelable: true }));

await flush();
await flush();
await flush();

const optionsBefore = logSelect.options.map((option) => option.value);
const selectionBefore = logSelect.value;
const contentBefore = logContent.textContent;
const metaBefore = logMeta.textContent;

let resolveScheduleSave;
enqueueResponses([
  () =>
    new Promise((resolve) => {
      resolveScheduleSave = () =>
        resolve(
          new Response(
            JSON.stringify({ mode: "cron", expression: "0 * * * *", datetime: "" }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
    }),
]);

const scheduleButtonsBefore = {
  saveDisabled: saveScheduleButton.disabled,
  resetDisabled: scheduleResetButton.disabled,
  formBusy: scheduleForm.getAttribute("aria-busy"),
};

scheduleForm.dispatchEvent(new FakeEvent("submit", { bubbles: true, cancelable: true }));

const scheduleButtonsDuring = {
  saveDisabled: saveScheduleButton.disabled,
  resetDisabled: scheduleResetButton.disabled,
  formBusy: scheduleForm.getAttribute("aria-busy"),
};

resolveScheduleSave();

await flush();
await flush();

const scheduleButtonsAfter = {
  saveDisabled: saveScheduleButton.disabled,
  resetDisabled: scheduleResetButton.disabled,
  formBusy: scheduleForm.getAttribute("aria-busy"),
};

enqueueResponses([
  () => Promise.reject(new Error("Network unreachable")),
]);

refreshLogs.dispatchEvent(new FakeEvent("click", { bubbles: true }));

const contentDuringRefresh = logContent.textContent;
const selectDisabledDuringRefresh = logSelect.disabled;
const selectBusyDuringRefresh = logSelect.getAttribute("aria-busy");
const contentBusyDuringRefresh = logContent.getAttribute("aria-busy");
const refreshDisabledDuringRequest = refreshLogs.disabled;

await flush();
await flush();

const optionsAfter = logSelect.options.map((option) => option.value);
const selectionAfter = logSelect.value;
const contentAfter = logContent.textContent;
const metaAfter = logMeta.textContent;
const logsStatusText = logsStatus.textContent;
const selectBusyAfter = logSelect.getAttribute("aria-busy");
const contentBusyAfter = logContent.getAttribute("aria-busy");

parentPort.postMessage({
  optionsBefore,
  optionsAfter,
  selectionBefore,
  selectionAfter,
  contentBefore,
  contentAfter,
  metaBefore,
  metaAfter,
  logsStatusText,
  refreshDisabled: refreshLogs.disabled,
  refreshDisabledDuringRequest,
  contentDuringRefresh,
  selectDisabledDuringRefresh,
  selectBusyDuringRefresh,
  contentBusyDuringRefresh,
  selectBusyAfter,
  contentBusyAfter,
  scheduleButtons: {
    before: scheduleButtonsBefore,
    during: scheduleButtonsDuring,
    after: scheduleButtonsAfter,
  },
  remainingFetchHandlers: fetchQueue.length,
});
