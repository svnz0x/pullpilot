import { parentPort } from "node:worker_threads";

import { createAppTestHarness } from "./helpers/app-harness.js";

const {
  loginForm,
  tokenInput,
  resetConfigButton,
  retryConfigButton,
  configStatus,
  enqueueResponses,
  okResponse,
  fetchQueue,
  flush,
  FakeEvent,
} = createAppTestHarness();

const authCheckResponse = () => Promise.resolve(new Response(null, { status: 204 }));

const configPayload = {
  schema: {
    variables: [],
  },
  values: {
    BASE_DIR: "/srv/app",
    LOG_DIR: "/srv/app/logs",
  },
};

const schedulePayload = { mode: "cron", expression: "", datetime: "" };
const logsPayload = { files: [], selected: null, log_dir: "" };

enqueueResponses([
  authCheckResponse,
  () => Promise.resolve(new Response(null, { status: 500 })),
  () => okResponse(schedulePayload),
  () => okResponse(logsPayload),
]);

await import(new URL("../src/app.js", import.meta.url));

tokenInput.value = "demo-token";
loginForm.dispatchEvent(new FakeEvent("submit", { bubbles: true, cancelable: true }));

await flush();
await flush();
await flush();

const failureSummary = configStatus.querySelector("span")?.textContent ?? "";
const resetDisabledAfterFailure = Boolean(resetConfigButton.disabled);
const retryVisibleAfterFailure = !retryConfigButton.hidden;

resetConfigButton.dispatchEvent(new FakeEvent("click", { bubbles: true, cancelable: true }));

await flush();

const manualNotice = configStatus.querySelector("span")?.textContent ?? "";

enqueueResponses([() => okResponse(configPayload)]);

retryConfigButton.dispatchEvent(new FakeEvent("click", { bubbles: true, cancelable: true }));

await flush();
await flush();

const resetEnabledAfterRetry = !resetConfigButton.disabled;
const retryHiddenAfterRetry = retryConfigButton.hidden;
const successSummary = configStatus.querySelector("span")?.textContent ?? "";

parentPort.postMessage({
  failure: {
    summary: failureSummary,
    resetDisabled: resetDisabledAfterFailure,
    retryVisible: retryVisibleAfterFailure,
  },
  manualNotice,
  retry: {
    resetEnabled: resetEnabledAfterRetry,
    retryHidden: retryHiddenAfterRetry,
    successSummary,
    remainingFetchHandlers: fetchQueue.length,
  },
});
