import test from "node:test";
import assert from "node:assert/strict";
import { runWorker } from "./helpers/run-worker.js";

test("generic unauthorized response clears persisted token and asks for a new one", async () => {
  const result = await runWorker(new URL("./handle-unauthorized.worker.js", import.meta.url));
  assert.equal(result.checkboxAfterUnauthorized, false);
  assert.equal(result.tokenInputAfterUnauthorized, "");
  assert.equal(result.storedAfterUnauthorized, null);
  assert.equal(
    result.loginStatusAfterUnauthorized,
    "El token ha caducado o es incorrecto. Introduce uno nuevo. Introduce de nuevo el token para continuar.",
  );
  assert.equal(result.storedAfterRelogin, result.tokenValue);
});
