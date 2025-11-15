import test from "node:test";
import assert from "node:assert/strict";

import { createConfigTestRunner } from "../src/app.js";

test("el botón de prueba ejecuta la petición hacia /ui/run-test", async () => {
  const requests = [];
  const authorizedFetch = async (input) => {
    requests.push(input);
    return {
      ok: true,
      json: async () => ({ status: "success" }),
    };
  };
  const buildApiUrl = (path) => `https://example.test/ui/${path}`;
  const showStatus = () => {};
  const hideStatus = () => {};
  const setTestConfigButtonLoading = () => {};
  const buildProcessStatusMessage = () => ({ summary: "", details: [], tone: "success" });
  const buildErrorStatusPayload = () => ({ summary: "", details: [] });
  const configStatus = {};

  const runConfigTest = createConfigTestRunner({
    authorizedFetch,
    buildApiUrl,
    buildProcessStatusMessage,
    buildErrorStatusPayload,
    showStatus,
    hideStatus,
    setTestConfigButtonLoading,
    configStatus,
  });

  await runConfigTest();

  assert.equal(requests.length, 1);
  const url = new URL(requests[0]);
  assert.equal(url.pathname, "/ui/run-test");
});
