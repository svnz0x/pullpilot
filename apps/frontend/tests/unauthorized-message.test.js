import test from "node:test";
import assert from "node:assert/strict";

import { buildUnauthorizedTokenMessage } from "../src/unauthorized-message.js";

const BASE_MESSAGE = "El token ha caducado o es incorrecto. Introduce uno nuevo.";

const REUSE_SUFFIX =
  "El token guardado se reutilizará automáticamente cuando el servidor vuelva a aceptar credenciales.";
const REENTER_SUFFIX = "Introduce de nuevo el token para continuar.";

const buildStorageOutcome = (message) => ({ handled: true, message });

test("agrega orientación sobre reutilización automática cuando el token está almacenado", () => {
  const result = buildUnauthorizedTokenMessage(BASE_MESSAGE, { reusableToken: true });
  assert.equal(result, `${BASE_MESSAGE} ${REUSE_SUFFIX}`);
});

test("solicita reintroducir el token cuando solo estaba en memoria", () => {
  const result = buildUnauthorizedTokenMessage(BASE_MESSAGE, {
    reusableToken: false,
    hadMemoryToken: true,
  });
  assert.equal(result, `${BASE_MESSAGE} ${REENTER_SUFFIX}`);
});

test("adjunta mensajes adicionales derivados del estado del almacenamiento", () => {
  const storageMessage =
    "No se pudo olvidar el token almacenado en este navegador. Es posible que debas borrarlo manualmente.";
  const result = buildUnauthorizedTokenMessage(BASE_MESSAGE, {
    reusableToken: false,
    hadMemoryToken: true,
    storageOutcome: buildStorageOutcome(storageMessage),
  });
  assert.equal(result, `${BASE_MESSAGE} ${REENTER_SUFFIX} ${storageMessage}`);
});
