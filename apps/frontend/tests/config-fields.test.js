import test from "node:test";
import assert from "node:assert/strict";

import { bootApp } from "./helpers/boot-app.js";
import { createFetchQueue } from "./helpers/fetch-queue.js";
import { flushTasks } from "./helpers/flush.js";

test("config fields expose HTML constraints and block invalid values", async () => {
  const { fetch: fetchMock, enqueueResponses, okResponse, queue } = createFetchQueue();

  const authCheckResponse = () => Promise.resolve(new Response(null, { status: 204 }));
  const configPayload = {
    schema: {
      variables: [
        {
          name: "LOCK_FILE",
          type: "string",
          default: "/var/lock/docker-updater.lock",
          description: "Archivo de bloqueo",
          constraints: { pattern: "^/.*" },
        },
        {
          name: "LOG_RETENTION_DAYS",
          type: "integer",
          default: 14,
          description: "Número de días de retención",
          constraints: { min: 1 },
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

  await bootApp({ fetchMock });

  const loginForm = document.getElementById("token-form");
  const tokenInput = document.getElementById("token-input");
  const configForm = document.getElementById("config-form");
  const configFields = document.getElementById("config-fields");
  const configStatus = document.getElementById("config-status");

  tokenInput.value = "demo-token";
  loginForm.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));

  await flushTasks(3);

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

  configForm.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));

  await flushTasks();

  const summaryNode = configStatus.querySelector("span");
  const detailsList = configStatus.querySelector("ul");
  const firstDetail = detailsList?.children?.[0]?.textContent ?? "";

  assert.equal(lockInput?.getAttribute?.("pattern"), "^/.*");
  assert.equal(lockInput?.hasAttribute?.("required"), true);
  assert.equal(lockInput?.getAttribute?.("aria-required"), "true");

  assert.equal(retentionInput?.getAttribute?.("min"), "1");
  assert.equal(Boolean(retentionField?.classList?.contains("is-error")), true);

  assert.equal(queue.length, 1);
  assert.equal(summaryNode?.textContent ?? "", "Revisa los campos marcados antes de guardar.");
  assert.equal(firstDetail, "LOG_RETENTION_DAYS: Debe ser como mínimo 1.");
});
