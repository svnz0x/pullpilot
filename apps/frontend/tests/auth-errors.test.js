import test from "node:test";
import assert from "node:assert/strict";

import {
  buildMissingCredentialsMessage,
  resolveUnauthorizedDetails,
} from "../src/auth-errors.js";

const LOGIN_FALLBACK =
  "El token proporcionado no está autorizado. Vuelve a intentarlo.";
const FETCH_FALLBACK =
  "El token ha caducado o es incorrecto. Introduce uno nuevo.";

const buildLoginFlowMessage = (error) => {
  const { message, reason } = resolveUnauthorizedDetails(error, LOGIN_FALLBACK);
  return {
    reason,
    message:
      reason === "missing-credentials"
        ? buildMissingCredentialsMessage(message)
        : message,
  };
};

const buildAuthorizedFetchMessage = (error) => {
  const { message, reason } = resolveUnauthorizedDetails(error, FETCH_FALLBACK);
  return {
    reason,
    message:
      reason === "missing-credentials"
        ? buildMissingCredentialsMessage(message)
        : message,
  };
};

const createMissingCredentialsError = (detailMessage) => ({
  payload: {
    error: "missing credentials",
    detail: {
      message: detailMessage,
    },
  },
});

test("login and authorizedFetch share enriched guidance for missing credentials", () => {
  const error = createMissingCredentialsError(
    "Faltan credenciales. Se requiere un token bearer.",
  );
  const loginResult = buildLoginFlowMessage(error);
  const fetchResult = buildAuthorizedFetchMessage(error);

  assert.equal(loginResult.reason, "missing-credentials");
  assert.equal(fetchResult.reason, "missing-credentials");
  assert.equal(loginResult.message, fetchResult.message);
  assert.match(
    loginResult.message,
    /Configura la variable de entorno PULLPILOT_TOKEN en el servidor\./,
    "the enriched message should instruct configuring the token",
  );
  assert.match(
    loginResult.message,
    /Reinicia el servidor después de modificar PULLPILOT_TOKEN\./,
    "the enriched message should mention restarting the server",
  );
  assert.match(
    loginResult.message,
    /El token introducido se conservará y se reutilizará automáticamente cuando el backend acepte credenciales\./,
    "the enriched message should mention persisting the token",
  );
});

test("messages stay aligned when backend references PULLPILOT_TOKEN", () => {
  const error = createMissingCredentialsError(
    "PULLPILOT_TOKEN no está configurado.",
  );
  const loginResult = buildLoginFlowMessage(error);
  const fetchResult = buildAuthorizedFetchMessage(error);

  assert.equal(loginResult.reason, "missing-credentials");
  assert.equal(fetchResult.reason, "missing-credentials");
  assert.equal(loginResult.message, fetchResult.message);
  assert.ok(
    loginResult.message.startsWith("Faltan credenciales."),
    "the enriched message should start with the missing credentials prefix",
  );
  assert.match(
    loginResult.message,
    /Reinicia el servidor después de modificar PULLPILOT_TOKEN\./,
    "the enriched message should mention restarting the server",
  );
  assert.match(
    loginResult.message,
    /El token introducido se conservará y se reutilizará automáticamente cuando el backend acepte credenciales\./,
    "the enriched message should mention persisting the token",
  );
});
