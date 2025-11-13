const ignoredMessages = new Set(["missing credentials", "unauthorized"]);

export const resolveUnauthorizedDetails = (error, fallbackMessage) => {
  const payload = error?.payload;
  const fallback = typeof fallbackMessage === "string" ? fallbackMessage : "";
  const defaultResult = { message: fallback, reason: "unknown" };

  const gatherMessages = (...sources) => {
    const results = [];
    const visitedObjects = typeof WeakSet === "function" ? new WeakSet() : new Set();

    const pushMessage = (value) => {
      const trimmed = value.trim();
      if (!trimmed) return;
      const normalized = trimmed.toLowerCase();
      if (ignoredMessages.has(normalized)) return;
      if (!results.includes(trimmed)) {
        results.push(trimmed);
      }
    };

    const visit = (value) => {
      if (value == null) {
        return;
      }
      if (typeof value === "string") {
        pushMessage(value);
        return;
      }
      if (Array.isArray(value)) {
        value.forEach(visit);
        return;
      }
      if (typeof value === "object") {
        if (visitedObjects.has(value)) return;
        visitedObjects.add(value);
        const prioritizedKeys = [
          "detail",
          "details",
          "description",
          "message",
          "error",
          "msg",
          "hint",
          "title",
        ];
        prioritizedKeys.forEach((key) => {
          if (key in value) {
            visit(value[key]);
          }
        });
        Object.keys(value).forEach((key) => {
          if (!prioritizedKeys.includes(key)) {
            visit(value[key]);
          }
        });
      }
    };

    sources.forEach(visit);
    return results;
  };

  if (payload && typeof payload === "object") {
    const detailPayload =
      payload.detail && typeof payload.detail === "object"
        ? payload.detail
        : null;
    const errorCode =
      typeof payload.error === "string" && payload.error
        ? payload.error
        : typeof detailPayload?.error === "string"
        ? detailPayload.error
        : null;
    const normalizedErrorCode = errorCode?.toLowerCase() ?? null;

    if (normalizedErrorCode === "missing credentials") {
      const missingMessages = gatherMessages(
        payload.details,
        payload.message,
        payload.detail,
        detailPayload?.details,
        detailPayload?.message,
        detailPayload,
      );

      if (missingMessages.length > 0) {
        const message = missingMessages[0];
        if (/faltan credenciales/i.test(message)) {
          return { message, reason: "missing-credentials" };
        }
        if (/PULLPILOT_TOKEN/i.test(message)) {
          return {
            message: `Faltan credenciales. ${message}`,
            reason: "missing-credentials",
          };
        }
        return { message, reason: "missing-credentials" };
      }

      return {
        message:
          "Faltan credenciales. Introduce el token proporcionado para continuar.",
        reason: "missing-credentials",
      };
    }

    const genericMessages = gatherMessages(
      payload.detail,
      payload.description,
      payload.message,
      payload.details,
      payload.error,
    );
    if (genericMessages.length > 0) {
      return {
        message: genericMessages[0],
        reason: normalizedErrorCode || "generic",
      };
    }

    if (normalizedErrorCode) {
      return { ...defaultResult, reason: normalizedErrorCode };
    }
  } else if (typeof payload === "string" && payload.trim()) {
    return { message: payload.trim(), reason: "string-payload" };
  }

  return defaultResult;
};

export const resolveUnauthorizedMessage = (error, fallbackMessage) =>
  resolveUnauthorizedDetails(error, fallbackMessage).message;

export const buildMissingCredentialsMessage = (message) => {
  const trimmed = typeof message === "string" ? message.trim() : "";
  const parts = [];
  if (trimmed) {
    parts.push(trimmed);
  }

  const mentionsToken = /PULLPILOT_TOKEN/i.test(trimmed);
  if (!mentionsToken) {
    parts.push(
      "Configura la variable de entorno PULLPILOT_TOKEN en el servidor.",
    );
  }
  parts.push("Reinicia el servidor después de modificar PULLPILOT_TOKEN.");
  parts.push(
    "El token introducido se conservará y se reutilizará automáticamente cuando el backend acepte credenciales.",
  );
  return parts.join(" ").trim();
};
