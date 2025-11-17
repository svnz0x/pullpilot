import test from "node:test";
import assert from "node:assert/strict";

import { createApiUrlBuilder } from "../src/api-url.js";

const createWindowStub = ({ origin = "https://example.test", pathname = "/ui/" } = {}) => {
  const location = { origin, pathname };
  const document = {
    querySelector: () => null,
  };

  return {
    location,
    document,
    URL,
  };
};

test("buildApiUrl mantiene la base /ui para rutas relativas", () => {
  const windowStub = createWindowStub({ pathname: "/ui/" });
  const buildApiUrl = createApiUrlBuilder(windowStub);

  assert.equal(
    buildApiUrl("auth-check"),
    "https://example.test/ui/auth-check",
    "las rutas relativas deben resolverse bajo /ui/",
  );
  assert.equal(
    buildApiUrl("logs"),
    "https://example.test/ui/logs",
    "se deben preservar las rutas relativas adicionales",
  );
});

test("buildApiUrl conserva las rutas absolutas contra el origen", () => {
  const windowStub = createWindowStub({ pathname: "/ui/" });
  const buildApiUrl = createApiUrlBuilder(windowStub);

  assert.equal(
    buildApiUrl("/config"),
    "https://example.test/config",
    "las rutas absolutas deben construirse en el origen sin duplicar /ui",
  );
  assert.equal(
    buildApiUrl("/schedule"),
    "https://example.test/schedule",
    "las rutas absolutas adicionales deben conservarse",
  );
});
