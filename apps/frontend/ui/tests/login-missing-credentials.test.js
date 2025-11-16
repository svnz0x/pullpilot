import test from "node:test";
import assert from "node:assert/strict";
import { runWorker } from "./helpers/run-worker.js";

test("missing credentials response keeps token according to remember option", async () => {
  const result = await runWorker(
    new URL("./login-missing-credentials.worker.js", import.meta.url),
  );

  assert.equal(result.rememberResult.local, result.tokenValue);
  assert.equal(result.rememberResult.session, null);
  assert.equal(result.forgetResult.local, null);
  assert.equal(result.forgetResult.session, null);
});
