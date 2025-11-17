import test from "node:test";
import assert from "node:assert/strict";

import { bootApp } from "./helpers/boot-app.js";
import { createFetchQueue } from "./helpers/fetch-queue.js";
import { flushTasks } from "./helpers/flush.js";

test("reset button is disabled after failure until retry finishes", async () => {
  const { fetch: fetchMock, enqueueResponses, okResponse, queue } = createFetchQueue();

  const authCheckResponse = () => Promise.resolve(new Response(null, { status: 204 }));
  const configPayload = {
    schema: { variables: [] },
    values: { BASE_DIR: "/srv/app", LOG_DIR: "/srv/app/logs" },
  };
  const schedulePayload = { mode: "cron", expression: "", datetime: "" };
  const logsPayload = { files: [], selected: null, log_dir: "" };

  enqueueResponses([
    authCheckResponse,
    () => Promise.resolve(new Response(null, { status: 500 })),
    () => okResponse(schedulePayload),
    () => okResponse(logsPayload),
  ]);

  await bootApp({ fetchMock });

  const loginForm = document.getElementById("token-form");
  const tokenInput = document.getElementById("token-input");
  const configForm = document.getElementById("config-form");
  const saveConfigButton = document.getElementById("save-config");
  const resetConfigButton = document.getElementById("reset-config");
  const retryConfigButton = document.getElementById("retry-config");
  const configStatus = document.getElementById("config-status");

  tokenInput.value = "demo-token";
  loginForm.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));

  await flushTasks(3);

  const failureSummary = configStatus.querySelector("span")?.textContent ?? "";
  const resetDisabledAfterFailure = Boolean(resetConfigButton.disabled);
  const retryVisibleAfterFailure = !retryConfigButton.hidden;

  resetConfigButton.dispatchEvent(new Event("click", { bubbles: true, cancelable: true }));

  await flushTasks();

  const manualNotice = configStatus.querySelector("span")?.textContent ?? "";

  enqueueResponses([() => okResponse(configPayload)]);

  const saveDisabledBeforeRetry = saveConfigButton.disabled;
  const formBusyBeforeRetry = configForm.getAttribute("aria-busy");

  retryConfigButton.dispatchEvent(new Event("click", { bubbles: true, cancelable: true }));

  const saveDisabledDuringRetry = saveConfigButton.disabled;
  const resetDisabledDuringRetry = resetConfigButton.disabled;
  const formBusyDuringRetry = configForm.getAttribute("aria-busy");

  await flushTasks(2);

  const resetEnabledAfterRetry = !resetConfigButton.disabled;
  const retryHiddenAfterRetry = retryConfigButton.hidden;
  const successSummary = configStatus.querySelector("span")?.textContent ?? "";
  const saveDisabledAfterRetry = saveConfigButton.disabled;
  const formBusyAfterRetry = configForm.getAttribute("aria-busy");

  assert.equal(
    failureSummary,
    "Token válido, pero el backend no devolvió la configuración. Revisa el servicio e inténtalo de nuevo.",
  );
  assert.equal(resetDisabledAfterFailure, true);
  assert.equal(retryVisibleAfterFailure, true);
  assert.equal(
    manualNotice,
    "No hay una configuración cargada para descartar. Usa «Reintentar carga» para intentarlo de nuevo.",
  );

  assert.equal(saveDisabledBeforeRetry, false);
  assert.equal(saveDisabledDuringRetry, true);
  assert.equal(saveDisabledAfterRetry, false);
  assert.equal(resetDisabledDuringRetry, true);
  assert.equal(resetEnabledAfterRetry, true);
  assert.equal(retryHiddenAfterRetry, true);
  assert.equal(successSummary, "Configuración cargada correctamente.");
  assert.equal(formBusyBeforeRetry, null);
  assert.equal(formBusyDuringRetry, "true");
  assert.equal(formBusyAfterRetry, null);
  assert.equal(queue.length, 0);
});
