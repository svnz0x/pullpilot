import test from "node:test";
import assert from "node:assert/strict";

import { bootApp } from "./helpers/boot-app.js";
import { createFetchQueue } from "./helpers/fetch-queue.js";
import { flushTasks } from "./helpers/flush.js";

test("generic unauthorized response clears persisted token and asks for a new one", async () => {
  const { fetch: fetchMock, enqueueResponses, okResponse } = createFetchQueue();

  const unauthorizedResponse = () =>
    Promise.resolve(
      new Response(JSON.stringify({ detail: "Unauthorized" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }),
    );

  await bootApp({ fetchMock });

  const loginForm = document.getElementById("token-form");
  const tokenInput = document.getElementById("token-input");
  const loginStatus = document.getElementById("login-status");
  const rememberCheckbox = document.getElementById("remember-token");
  const tokenValue = "demo-token";

  rememberCheckbox.checked = true;
  tokenInput.value = tokenValue;

  enqueueResponses([
    () => okResponse({}),
    () => unauthorizedResponse(),
    () => okResponse({ mode: "cron", expression: "", datetime: "" }),
    () => okResponse({ files: [], selected: null, log_dir: "/logs" }),
  ]);

  loginForm.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  await flushTasks(2);

  const checkboxAfterUnauthorized = rememberCheckbox.checked;
  const tokenInputAfterUnauthorized = tokenInput.value;
  const storedAfterUnauthorized = localStorage.getItem("pullpilot.bearerToken");
  const loginStatusAfterUnauthorized = loginStatus.textContent;

  rememberCheckbox.checked = true;
  tokenInput.value = tokenValue;

  enqueueResponses([
    () => okResponse({}),
    () =>
      okResponse({
        schema: { variables: [] },
        values: {},
        multiline: {},
        meta: { multiline_fields: [] },
      }),
    () => okResponse({ mode: "cron", expression: "", datetime: "" }),
    () => okResponse({ files: [], selected: null, log_dir: "/logs" }),
  ]);

  loginForm.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  await flushTasks(3);

  const storedAfterRelogin = localStorage.getItem("pullpilot.bearerToken");

  assert.equal(checkboxAfterUnauthorized, false);
  assert.equal(tokenInputAfterUnauthorized, "");
  assert.equal(storedAfterUnauthorized, null);
  assert.equal(
    loginStatusAfterUnauthorized,
    "El token ha caducado o es incorrecto. Introduce uno nuevo. Introduce de nuevo el token para continuar.",
  );
  assert.equal(storedAfterRelogin, tokenValue);
});
