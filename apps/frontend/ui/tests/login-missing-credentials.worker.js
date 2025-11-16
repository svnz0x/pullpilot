import { parentPort } from "node:worker_threads";
import { createAppTestHarness } from "./helpers/app-harness.js";

const {
  loginForm,
  tokenInput,
  rememberCheckbox,
  window: windowStub,
  enqueueResponses,
  flush,
  FakeEvent,
} = createAppTestHarness();

const tokenValue = "demo-token";

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

await import(new URL("../src/app.js", import.meta.url));

const runScenario = async (shouldPersist) => {
  rememberCheckbox.checked = shouldPersist;
  tokenInput.value = tokenValue;
  enqueueResponses([() => missingCredentialsResponse()]);
  loginForm.dispatchEvent(new FakeEvent("submit", { bubbles: true, cancelable: true }));
  await flush();
  await flush();
  return {
    persist: shouldPersist,
    local: windowStub.localStorage.getItem("pullpilot.bearerToken"),
    session: windowStub.sessionStorage.getItem("pullpilot.bearerToken"),
    message: document.getElementById("login-status")?.textContent ?? "",
  };
};

const rememberResult = await runScenario(true);
windowStub.localStorage.clear();
windowStub.sessionStorage.clear();

const forgetResult = await runScenario(false);

parentPort.postMessage({
  tokenValue,
  rememberResult,
  forgetResult,
});
