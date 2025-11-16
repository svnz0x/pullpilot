import test from "node:test";
import assert from "node:assert/strict";
import { Worker } from "node:worker_threads";

const runWorker = (url) =>
  new Promise((resolve, reject) => {
    const worker = new Worker(url, { type: "module" });
    worker.once("message", resolve);
    worker.once("error", reject);
    worker.once("exit", (code) => {
      if (code !== 0) {
        reject(new Error(`Worker exited with code ${code}`));
      }
    });
  });

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
