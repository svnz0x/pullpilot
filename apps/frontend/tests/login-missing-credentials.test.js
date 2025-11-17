import test from "node:test";
import assert from "node:assert/strict";

import { bootApp } from "./helpers/boot-app.js";
import { createFetchQueue } from "./helpers/fetch-queue.js";
import { flushTasks } from "./helpers/flush.js";

test("missing credentials error clears storage for both persistence modes", async () => {
  const { fetch: fetchMock, enqueueResponses } = createFetchQueue();

  const missingCredentialsResponse = () =>
    Promise.resolve(
      new Response(
        JSON.stringify({
          error: "missing credentials",
          detail: {
            error: "missing credentials",
            message: "Faltan credenciales para procesar la solicitud",
          },
        }),
        {
          status: 401,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

  await bootApp({ fetchMock });

  const loginForm = document.getElementById("token-form");
  const tokenInput = document.getElementById("token-input");
  const rememberCheckbox = document.getElementById("remember-token");
  const tokenValue = "demo-token";

  const runScenario = async (shouldPersist) => {
    rememberCheckbox.checked = shouldPersist;
    tokenInput.value = tokenValue;
    enqueueResponses([() => missingCredentialsResponse()]);
    loginForm.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    await flushTasks(2);
    return {
      persist: shouldPersist,
      local: localStorage.getItem("pullpilot.bearerToken"),
      session: sessionStorage.getItem("pullpilot.bearerToken"),
      message: document.getElementById("login-status")?.textContent ?? "",
    };
  };

  const rememberResult = await runScenario(true);
  localStorage.clear();
  sessionStorage.clear();
  const forgetResult = await runScenario(false);

  assert.equal(rememberResult.local, tokenValue);
  assert.equal(rememberResult.session, null);
  assert.equal(forgetResult.local, null);
  assert.equal(forgetResult.session, null);
});
