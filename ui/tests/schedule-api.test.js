import test from "node:test";
import assert from "node:assert/strict";

import { createScheduleApi } from "../src/schedule-api.js";

test("createScheduleApi load usa authorizedFetch con la ruta de schedule", async () => {
  const calls = [];
  const authorizedFetch = async (url, options) => {
    calls.push({ url, options });
    return { ok: true, json: async () => ({}) };
  };
  const buildApiUrl = (path) => {
    assert.equal(path, "/schedule");
    return `https://example.test${path}`;
  };

  const api = createScheduleApi({ authorizedFetch, buildApiUrl });
  await api.load();

  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "https://example.test/schedule");
  assert.equal(calls[0].options, undefined);
});

test("createScheduleApi save envía una petición PUT con JSON", async () => {
  const calls = [];
  const authorizedFetch = async (url, options) => {
    calls.push({ url, options });
    return { ok: true, json: async () => ({}) };
  };
  const buildApiUrl = (path) => {
    assert.equal(path, "/schedule");
    return `https://example.test${path}`;
  };
  const payload = { mode: "cron", expression: "0 4 * * *" };

  const api = createScheduleApi({ authorizedFetch, buildApiUrl });
  await api.save(payload);

  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "https://example.test/schedule");
  assert.deepEqual(calls[0].options, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
});

test("createScheduleApi valida los argumentos proporcionados", () => {
  const buildApiUrl = (path) => path;
  assert.throws(
    () => createScheduleApi({ authorizedFetch: null, buildApiUrl }),
    /authorizedFetch must be a function/,
  );
  assert.throws(
    () => createScheduleApi({ authorizedFetch: () => {}, buildApiUrl: null }),
    /buildApiUrl must be a function/,
  );
});
