import test from "node:test";
import assert from "node:assert/strict";

import { createAuthorizedFetch } from "../src/app.js";

test("authorizedFetch clones Request inputs and preserves POST bodies", async () => {
  const auth = {
    getToken: () => "demo-token",
  };

  const buildApiUrl = (value) => {
    const asString = value instanceof URL ? value.toString() : String(value);
    return asString.replace("https://frontend.local/ui", "https://backend.local/api");
  };

  const handleUnauthorized = () => {};
  const createUnauthorizedError = () => {
    const error = new Error("UNAUTHORIZED");
    error.status = 401;
    return error;
  };

  const authorizedFetch = createAuthorizedFetch({
    auth,
    buildApiUrl,
    handleUnauthorized,
    createUnauthorizedError,
  });

  const controller = new AbortController();
  const originalRequest = new Request("https://frontend.local/ui/run-test", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ping: "pong" }),
    mode: "cors",
    credentials: "include",
    signal: controller.signal,
  });

  const originalFetch = globalThis.fetch;
  const recorded = [];
  globalThis.fetch = async (input, init) => {
    const bodyText =
      input instanceof Request
        ? await input.clone().text()
        : typeof init?.body === "string"
        ? init.body
        : init?.body != null
        ? await new Response(init.body).text()
        : "";
    recorded.push({ input, init, bodyText });
    return new Response(null, { status: 200 });
  };

  try {
    const response = await authorizedFetch(originalRequest);
    assert.equal(response.ok, true);
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(recorded.length, 1);
  const entry = recorded[0];
  assert.ok(entry.input instanceof Request);
  assert.equal(entry.input.method, "POST");
  assert.equal(entry.input.url, "https://backend.local/api/run-test");
  assert.equal(entry.bodyText, JSON.stringify({ ping: "pong" }));
  assert.equal(entry.input.mode, "cors");
  assert.equal(entry.input.credentials, "include");
  assert.ok(entry.input.signal instanceof AbortSignal);
  assert.equal(entry.input.signal.aborted, false);
  controller.abort();
  assert.equal(entry.input.signal.aborted, true);
  assert.equal(entry.input.headers.get("Content-Type"), "application/json");
  assert.equal(entry.input.headers.get("Authorization"), "Bearer demo-token");
});
