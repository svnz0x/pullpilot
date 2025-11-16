import test from "node:test";
import assert from "node:assert/strict";
import { runWorker } from "./helpers/run-worker.js";

test("config fields expose HTML constraints and block invalid values", async () => {
  const result = await runWorker(new URL("./config-fields.worker.js", import.meta.url));

  assert.equal(result.lockField.pattern, "^/.*");
  assert.equal(result.lockField.required, true);
  assert.equal(result.lockField.ariaRequired, "true");

  assert.equal(result.retentionField.min, "1");
  assert.equal(result.retentionField.hasErrorClass, true);

  assert.equal(result.validation.remainingFetchHandlers, 1);
  assert.equal(result.validation.summary, "Revisa los campos marcados antes de guardar.");
  assert.equal(
    result.validation.firstDetail,
    "LOG_RETENTION_DAYS: Debe ser como mínimo 1.",
  );
});
