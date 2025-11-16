import { parentPort } from "node:worker_threads";

import { createAppTestHarness } from "./helpers/app-harness.js";

const {
  loginForm,
  tokenInput,
  configForm,
  configFields,
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
    variables: [
      {
        name: "LOCK_FILE",
        type: "string",
        default: "/var/lock/docker-updater.lock",
        description: "Archivo de bloqueo",
        constraints: {
          pattern: "^/.*",
        },
      },
      {
        name: "LOG_RETENTION_DAYS",
        type: "integer",
        default: 14,
        description: "Número de días de retención",
        constraints: {
          min: 1,
        },
      },
    ],
  },
  values: {
    LOCK_FILE: "/var/lock/docker-updater.lock",
    LOG_RETENTION_DAYS: 14,
  },
};

const schedulePayload = { mode: "cron", expression: "", datetime: "" };
const logsPayload = { files: [], selected: null, log_dir: "" };

enqueueResponses([
  authCheckResponse,
  () => okResponse(configPayload),
  () => okResponse(schedulePayload),
  () => okResponse(logsPayload),
]);

await import(new URL("../src/app.js", import.meta.url));

tokenInput.value = "demo-token";
loginForm.dispatchEvent(new FakeEvent("submit", { bubbles: true, cancelable: true }));

await flush();
await flush();
await flush();

const findField = (name) =>
  configFields.querySelector(`.config-field[data-name="${name}"]`) ?? null;

const lockField = findField("LOCK_FILE");
const lockInput = lockField?.querySelector?.(".value-input") ?? null;

const retentionField = findField("LOG_RETENTION_DAYS");
const retentionInput = retentionField?.querySelector?.(".value-input") ?? null;

enqueueResponses([() => okResponse(configPayload)]);

if (retentionInput) {
  retentionInput.value = "0";
}

configForm.dispatchEvent(new FakeEvent("submit", { bubbles: true, cancelable: true }));

await flush();

const summaryNode = configStatus.querySelector("span");
const detailsList = configStatus.querySelector("ul");
const firstDetail = detailsList?.children?.[0]?.textContent ?? "";

parentPort.postMessage({
  lockField: {
    pattern: lockInput?.getAttribute?.("pattern") ?? null,
    required: Boolean(lockInput?.hasAttribute?.("required")),
    ariaRequired: lockInput?.getAttribute?.("aria-required") ?? null,
  },
  retentionField: {
    min: retentionInput?.getAttribute?.("min") ?? null,
    hasErrorClass: Boolean(retentionField?.classList?.contains("is-error")),
  },
  validation: {
    remainingFetchHandlers: fetchQueue.length,
    summary: summaryNode?.textContent ?? "",
    firstDetail,
  },
});
