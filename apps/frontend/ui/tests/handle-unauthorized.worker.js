import { parentPort } from "node:worker_threads";
import { createAppTestHarness } from "./helpers/app-harness.js";

const {
  loginForm,
  tokenInput,
  loginStatus,
  rememberCheckbox,
  enqueueResponses,
  okResponse,
  flush,
  FakeEvent,
  window: windowStub,
} = createAppTestHarness();

const unauthorizedResponse = () =>
  Promise.resolve(
    new Response(JSON.stringify({ detail: "Unauthorized" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    }),
  );

const tokenValue = "demo-token";

await import(new URL("../src/app.js", import.meta.url));

rememberCheckbox.checked = true;
tokenInput.value = tokenValue;

enqueueResponses([
  () => okResponse({}),
  () => unauthorizedResponse(),
  () => okResponse({ mode: "cron", expression: "", datetime: "" }),
  () => okResponse({ files: [], selected: null, log_dir: "/logs" }),
]);

loginForm.dispatchEvent(new FakeEvent("submit", { bubbles: true, cancelable: true }));
await flush();
await flush();

const checkboxAfterUnauthorized = rememberCheckbox.checked;
const tokenInputAfterUnauthorized = tokenInput.value;
const storedAfterUnauthorized = windowStub.localStorage.getItem("pullpilot.bearerToken");
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

loginForm.dispatchEvent(new FakeEvent("submit", { bubbles: true, cancelable: true }));
await flush();
await flush();
await flush();

const storedAfterRelogin = windowStub.localStorage.getItem("pullpilot.bearerToken");

parentPort.postMessage({
  checkboxAfterUnauthorized,
  tokenInputAfterUnauthorized,
  storedAfterUnauthorized,
  storedAfterRelogin,
  loginStatusAfterUnauthorized,
  tokenValue,
});
