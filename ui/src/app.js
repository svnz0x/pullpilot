import { createTokenStorage } from "./token-storage.js";
import { createApiUrlBuilder } from "./api-url.js";
import { createScheduleApi } from "./schedule-api.js";
import {
  buildMissingCredentialsMessage,
  resolveUnauthorizedDetails,
} from "./auth-errors.js";
import { buildUnauthorizedTokenMessage } from "./unauthorized-message.js";

export const formatLogMetadata = ({ logDir, modified, size }) => {
  const segments = [];
  if (logDir) {
    segments.push(`Directorio: ${logDir}`);
  }
  if (modified) {
    segments.push(`Última modificación: ${modified}`);
  }
  if (size !== undefined && size !== null) {
    segments.push(`Tamaño: ${size} bytes`);
  }
  return segments.join(" · ");
};

export const resolveLogContentText = (selected) => {
  if (!selected) {
    return "No hay contenido disponible para el archivo seleccionado.";
  }
  if (Object.prototype.hasOwnProperty.call(selected, "content")) {
    return selected.content ?? "";
  }
  return "Archivo sin contenido o no legible.";
};

export const createLogsRequestManager = () => {
  let currentId = 0;
  let activeController = null;

  const start = () => {
    currentId += 1;
    if (activeController?.abort) {
      activeController.abort();
    }

    let controller = null;
    if (typeof AbortController !== "undefined") {
      controller = new AbortController();
    }
    activeController = controller;

    const release = () => {
      if (activeController === controller) {
        activeController = null;
      }
    };

    return { id: currentId, controller, release };
  };

  const isLatest = (id) => id === currentId;
  const getSignal = (controller) => controller?.signal;

  return { start, isLatest, getSignal };
};

export const toggleInitialLoadOnControl = (control, isLoading) => {
  if (!control) return;
  const dataset = control.dataset;
  if (!dataset) {
    if (isLoading && control.disabled !== true) {
      control.disabled = true;
    }
    return;
  }

  if (isLoading) {
    if (dataset.initialLoadDisabled === "true") {
      control.disabled = true;
      control.setAttribute?.("aria-disabled", "true");
      return;
    }
    dataset.initialLoadDisabled = "true";
    dataset.initialLoadWasDisabled = control.disabled ? "true" : "false";
    control.setAttribute?.("aria-disabled", "true");
    if (!control.disabled) {
      control.disabled = true;
    }
    return;
  }

  if (dataset.initialLoadDisabled === "true") {
    const wasDisabled = dataset.initialLoadWasDisabled === "true";
    delete dataset.initialLoadDisabled;
    delete dataset.initialLoadWasDisabled;
    if (wasDisabled) {
      control.setAttribute?.("aria-disabled", "true");
    } else {
      control.disabled = false;
      control.removeAttribute?.("aria-disabled");
    }
  }
};

const initializeApp = () => {
  const body = document.body;
  const loginForm = document.getElementById("token-form");
  const tokenInput = document.getElementById("token-input");
  const loginStatus = document.getElementById("login-status");
  const clearTokenButton = document.getElementById("clear-token");
  const rememberCheckbox = document.getElementById("remember-token");
  const logoutButton = document.getElementById("logout-button");
  const form = document.getElementById("config-form");
  const fieldsContainer = document.getElementById("config-fields");
  const resetButton = document.getElementById("reset-config");
  const configStatus = document.getElementById("config-status");
  const scheduleForm = document.getElementById("schedule-form");
  const scheduleFieldsContainer = document.getElementById("schedule-fields");
  const scheduleModeSelect = document.getElementById("schedule-mode");
  const scheduleExpressionField =
    scheduleFieldsContainer?.querySelector('[data-name="expression"]') ?? null;
  const scheduleExpressionInput = document.getElementById("schedule-expression");
  const scheduleDatetimeField =
    scheduleFieldsContainer?.querySelector('[data-name="datetime"]') ?? null;
  const scheduleDatetimeInput = document.getElementById("schedule-datetime");
  const scheduleStatus = document.getElementById("schedule-status");
  const scheduleResetButton = document.getElementById("reset-schedule");
  const logSelect = document.getElementById("log-select");
  const logContent = document.getElementById("log-content");
  const logMeta = document.getElementById("log-meta");
  const logsStatus = document.getElementById("logs-status");
  const refreshLogs = document.getElementById("refresh-logs");
  const main = document.querySelector("main");
  const initialLoadingBanner = document.getElementById("initial-loading-banner");

  let lastConfigSnapshot = null;
  let lastScheduleSnapshot = null;
  let memoryToken = null;
  let storedToken = null;
  let isInitialDataLoading = false;
  const tokenStorage = createTokenStorage(window);

  const buildApiUrl = createApiUrlBuilder(window);

  const showLoginMessage = (message, tone = "info") => {
    if (!loginStatus) return;
    loginStatus.textContent = message;
    loginStatus.classList.toggle("is-success", tone === "success");
    loginStatus.classList.toggle("is-error", tone === "error");
  };

  const STORAGE_FAILURE_MESSAGES = {
    read:
      "No se pudo acceder al almacenamiento local en este navegador. El token no se recordará automáticamente.",
    write:
      "No se pudo recordar el token en este navegador. El token solo estará disponible en esta sesión.",
    remove:
      "No se pudo actualizar el token almacenado en este navegador. El token podría seguir guardado.",
    clear:
      "No se pudo olvidar el token almacenado en este navegador. Es posible que debas borrarlo manualmente.",
    generic: "No se pudo acceder al almacenamiento local en este navegador.",
  };

  const disableRememberTokenOption = () => {
    if (!rememberCheckbox) return;
    rememberCheckbox.checked = false;
    rememberCheckbox.disabled = true;
    rememberCheckbox.setAttribute("data-storage-unavailable", "true");
  };

  const hasLocalStorageFailure = (status) => {
    const errors = Array.isArray(status?.errors) ? status.errors : [];
    return errors.some((entry) => entry?.storage === "localStorage");
  };

  const describeFallbackLabel = (status) => {
    if (status?.storageLabel) {
      return status.storageLabel;
    }
    if (status?.storage === "sessionStorage") {
      return "el almacenamiento de sesión";
    }
    return "un almacenamiento alternativo";
  };

  const buildFallbackMessage = (status) => {
    const label = describeFallbackLabel(status);
    if (status?.operation === "read") {
      return `Se recuperó el token usando ${label} porque el almacenamiento local no está disponible. El token se conservará solo durante esta sesión.`;
    }
    if (status?.persisted) {
      return `El token se recordará usando ${label} porque el almacenamiento local no está disponible.`;
    }
    return `No se pudo usar el almacenamiento local. El token se guardará solo durante esta sesión (${label}).`;
  };

  const processStorageStatus = (
    status,
    { message, tone = "error", silent = false } = {},
  ) => {
    if (!status) {
      return { handled: false };
    }

    if (status.ok === false) {
      disableRememberTokenOption();
      const resolvedMessage =
        message ||
        STORAGE_FAILURE_MESSAGES[status.operation] ||
        STORAGE_FAILURE_MESSAGES.generic;
      if (!silent) {
        showLoginMessage(resolvedMessage, tone);
      }
      return {
        handled: true,
        message: resolvedMessage,
        tone,
        status,
      };
    }

    if (status.fallbackUsed) {
      disableRememberTokenOption();
      const fallbackMessage = message || buildFallbackMessage(status);
      const fallbackTone = tone ?? "error";
      if (!silent) {
        showLoginMessage(fallbackMessage, fallbackTone);
      }
      return {
        handled: true,
        message: fallbackMessage,
        tone: fallbackTone,
        status,
      };
    }

    if (status.hadErrors && hasLocalStorageFailure(status)) {
      disableRememberTokenOption();
      const resolvedMessage =
        message ||
        STORAGE_FAILURE_MESSAGES[status.operation] ||
        STORAGE_FAILURE_MESSAGES.generic;
      if (!silent) {
        showLoginMessage(resolvedMessage, tone);
      }
      return {
        handled: true,
        message: resolvedMessage,
        tone,
        status,
      };
    }

    return { handled: false, status };
  };

  const applyInitialLoadingStateToForm = (element, isLoading) => {
    if (!element) return;
    if (isLoading) {
      element.setAttribute("data-initial-loading", "true");
      element.setAttribute("aria-busy", "true");
    } else {
      element.removeAttribute("data-initial-loading");
      element.removeAttribute("aria-busy");
    }
    element
      .querySelectorAll("input, select, textarea, button")
      .forEach((control) => toggleInitialLoadOnControl(control, isLoading));
  };

  const setInitialDataLoading = (isLoading) => {
    if (isInitialDataLoading === isLoading) {
      return;
    }
    isInitialDataLoading = isLoading;
    body.classList.toggle("initial-loading", isLoading);
    if (isLoading) {
      main?.setAttribute("aria-busy", "true");
      if (initialLoadingBanner) {
        initialLoadingBanner.hidden = false;
        initialLoadingBanner.textContent = "Cargando datos iniciales…";
      }
    } else {
      main?.removeAttribute("aria-busy");
      if (initialLoadingBanner) {
        initialLoadingBanner.hidden = true;
      }
    }
    applyInitialLoadingStateToForm(form, isLoading);
    applyInitialLoadingStateToForm(scheduleForm, isLoading);
  };

  const storedTokenStatus = tokenStorage.readToken();
  storedToken = storedTokenStatus?.token ?? null;
  const initialStorageOutcome = processStorageStatus(storedTokenStatus, {
    silent: true,
  });

  const resetPortalState = () => {
    if (fieldsContainer) {
      fieldsContainer.innerHTML = "";
    }
    lastConfigSnapshot = null;
    if (scheduleForm) {
      scheduleForm.reset();
    }
    if (scheduleFieldsContainer) {
      scheduleFieldsContainer
        .querySelectorAll(".config-field.is-error")
        .forEach((field) => {
          field.classList.remove("is-error");
          field
            .querySelectorAll(".value-input, textarea[data-multiline]")
            .forEach((control) => control.removeAttribute("aria-invalid"));
        });
    }
    if (scheduleModeSelect) {
      scheduleModeSelect.value = "cron";
    }
    if (scheduleExpressionField) {
      scheduleExpressionField.hidden = false;
    }
    if (scheduleExpressionInput) {
      scheduleExpressionInput.disabled = false;
      scheduleExpressionInput.value = "";
      scheduleExpressionInput.removeAttribute("aria-invalid");
    }
    if (scheduleDatetimeField) {
      scheduleDatetimeField.hidden = true;
    }
    if (scheduleDatetimeInput) {
      scheduleDatetimeInput.disabled = true;
      scheduleDatetimeInput.value = "";
      scheduleDatetimeInput.removeAttribute("aria-invalid");
    }
    if (scheduleStatus) {
      scheduleStatus.hidden = true;
      scheduleStatus.classList.remove("success", "error");
      scheduleStatus.textContent = "";
    }
    lastScheduleSnapshot = null;
    if (configStatus) {
      configStatus.hidden = true;
      configStatus.classList.remove("success", "error");
      configStatus.textContent = "";
    }
    if (logsStatus) {
      logsStatus.hidden = true;
      logsStatus.classList.remove("success", "error");
      logsStatus.textContent = "";
    }
    if (logSelect) {
      logSelect.innerHTML = "";
      logSelect.disabled = true;
    }
    if (logContent) {
      logContent.textContent = "Introduce un token válido para ver los logs.";
    }
    if (logMeta) {
      logMeta.textContent = "";
    }
  };

  const setAuthState = (isAuthenticated) => {
    body.classList.toggle("authenticated", isAuthenticated);
    body.classList.toggle("requires-auth", !isAuthenticated);
    if (!isAuthenticated) {
      setInitialDataLoading(false);
      resetPortalState();
    }
  };

  const auth = {
    getToken: () => memoryToken,
    setToken: (token, { persist = false } = {}) => {
      const trimmed = typeof token === "string" ? token.trim() : "";
      memoryToken = trimmed || null;

      if (!memoryToken) {
        storedToken = null;
        return tokenStorage.clearToken("remove");
      }

      if (persist) {
        const persistStatus = tokenStorage.persistToken(memoryToken);
        if (persistStatus?.ok) {
          storedToken = memoryToken;
        }
        return persistStatus;
      }

      storedToken = null;
      return tokenStorage.clearToken("remove");
    },
    clearToken: ({ forgetPersisted = true } = {}) => {
      memoryToken = null;
      if (!forgetPersisted) {
        return {
          ok: true,
          operation: "memory-clear",
          storage: null,
          storageLabel: null,
          persisted: false,
          fallbackUsed: false,
          attempts: [],
          errors: [],
          hadErrors: false,
        };
      }

      const clearStatus = tokenStorage.clearToken("clear");
      if (clearStatus?.ok) {
        storedToken = null;
      }
      return clearStatus;
    },
  };

  const verifyToken = async (candidate, { persist = false } = {}) => {
    const token = typeof candidate === "string" ? candidate.trim() : "";
    if (!token) {
      const error = new Error("TOKEN_REQUIRED");
      error.code = "TOKEN_REQUIRED";
      throw error;
    }

    let response;
    try {
      response = await fetch(buildApiUrl("auth-check"), {
        headers: { Authorization: `Bearer ${token}` },
      });
    } catch (error) {
      const networkError = new Error("NETWORK_ERROR");
      networkError.cause = error;
      throw networkError;
    }

    let payload = null;
    let payloadError = null;
    if (response.status !== 204) {
      try {
        payload = await response.json();
      } catch (error) {
        payloadError = error;
      }
    }

    if (response.status === 401) {
      const error = new Error("UNAUTHORIZED");
      error.status = response.status;
      if (!payloadError) {
        error.payload = payload;
      }
      throw error;
    }

    if (!response.ok) {
      const error = new Error("REQUEST_FAILED");
      error.status = response.status;
      if (!payloadError) {
        error.payload = payload;
      }
      throw error;
    }

    if (payloadError) {
      const invalidResponseError = new Error("INVALID_RESPONSE");
      invalidResponseError.cause = payloadError;
      throw invalidResponseError;
    }

    const storageStatus = auth.setToken(token, { persist });
    return { success: true, storageStatus };
  };

  const createUnauthorizedError = () => {
    const error = new Error("UNAUTHORIZED");
    error.status = 401;
    return error;
  };

  const handleUnauthorized = (
    error,
    fallbackMessage = "El token ha caducado o es incorrecto. Introduce uno nuevo.",
  ) => {
    const { message, reason } = resolveUnauthorizedDetails(error, fallbackMessage);
    if (reason === "missing-credentials") {
      const finalMessage = buildMissingCredentialsMessage(message);
      showLoginPrompt("error", finalMessage);
      return;
    }

    const hadMemoryToken = memoryToken != null;
    const storedTokenStatus = tokenStorage.readToken();
    storedToken = storedTokenStatus?.token ?? null;
    const reusableToken = Boolean(storedTokenStatus?.token);
    const clearStatus = auth.clearToken({ forgetPersisted: !reusableToken });
    const storageOutcome = processStorageStatus(clearStatus, { silent: true });
    loginForm?.reset();
    if (reusableToken) {
      if (tokenInput) {
        tokenInput.value = storedTokenStatus.token;
      }
      if (rememberCheckbox) {
        rememberCheckbox.checked = true;
      }
    }
    const finalMessage = buildUnauthorizedTokenMessage(message, {
      reusableToken,
      hadMemoryToken,
      storageOutcome,
    });
    showLoginPrompt("error", finalMessage);
  };

  const authorizedFetch = async (input, options = {}) => {
    const token = auth.getToken();
    if (!token) {
      throw createUnauthorizedError();
    }

    const headers = new Headers(options.headers || {});
    if (!headers.has("Authorization")) {
      headers.set("Authorization", `Bearer ${token}`);
    }

    let requestInput = input;
    if (requestInput instanceof Request) {
      requestInput = new Request(buildApiUrl(requestInput.url), requestInput);
    } else if (requestInput instanceof URL || typeof requestInput === "string") {
      requestInput = buildApiUrl(requestInput);
    }

    let response;
    try {
      response = await fetch(requestInput, { ...options, headers });
    } catch (error) {
      throw error;
    }

    if (response.status === 401) {
      const unauthorizedError = createUnauthorizedError();
      try {
        unauthorizedError.payload = await response.clone().json();
      } catch (error) {
        // Ignorar si la respuesta no contiene JSON.
      }
      handleUnauthorized(
        unauthorizedError,
        "El token ha caducado o es incorrecto. Introduce uno nuevo.",
      );
      throw unauthorizedError;
    }

    return response;
  };

  const scheduleApi = createScheduleApi({ authorizedFetch, buildApiUrl });

  const escapeSelector = (value) => {
    const stringValue = String(value);
    if (typeof CSS !== "undefined" && typeof CSS.escape === "function") {
      return CSS.escape(stringValue);
    }
    return stringValue.replace(/([\s!"#$%&'()*+,./:;<=>?@[\\\]^`{|}~])/g, "\\$1");
  };

  const normalizeStatusMessage = (message) => {
    if (message && typeof message === "object") {
      const summary =
        typeof message.summary === "string" && message.summary.trim().length
          ? message.summary.trim()
          : typeof message.text === "string"
          ? message.text
          : typeof message.message === "string"
          ? message.message
          : "";
      const detailsSource = Array.isArray(message.details)
        ? message.details
        : message.details != null
        ? [message.details]
        : [];
      const details = detailsSource
        .map((detail) =>
          detail == null
            ? null
            : typeof detail === "string"
            ? detail
            : typeof detail === "object"
            ? detail.message || detail.text || detail.detail || JSON.stringify(detail)
            : String(detail)
        )
        .filter((detail) => typeof detail === "string" && detail.trim().length)
        .map((detail) => detail.trim());
      return { summary, details };
    }
    if (typeof message === "string") {
      return { summary: message, details: [] };
    }
    return { summary: message != null ? String(message) : "", details: [] };
  };

  const showStatus = (element, message, kind = "info") => {
    if (!element) return;
    const { summary, details } = normalizeStatusMessage(message);
    element.textContent = "";
    if (summary) {
      const summaryNode = document.createElement("span");
      summaryNode.textContent = summary;
      element.appendChild(summaryNode);
    }
    if (details.length) {
      const list = document.createElement("ul");
      details.forEach((detail) => {
        const item = document.createElement("li");
        item.textContent = detail;
        list.appendChild(item);
      });
      element.appendChild(list);
    }
    element.hidden = false;
    element.classList.toggle("success", kind === "success");
    element.classList.toggle("error", kind === "error");
  };

  const hideStatus = (element) => {
    if (!element) return;
    element.hidden = true;
    element.classList.remove("success", "error");
    element.textContent = "";
  };

  const clearFieldErrors = (container = fieldsContainer) => {
    if (!container) return;
    container.querySelectorAll(".config-field.is-error").forEach((field) => {
      field.classList.remove("is-error");
      field
        .querySelectorAll(".value-input, textarea[data-multiline]")
        .forEach((control) => control.removeAttribute("aria-invalid"));
    });
  };

  const REQUIRED_PATH_FIELDS = [
    {
      name: "BASE_DIR",
      message: "Indica un directorio base absoluto y existente antes de guardar.",
    },
    {
      name: "LOG_DIR",
      message: "Indica un directorio de logs absoluto y existente antes de guardar.",
    },
  ];

  const collectMissingPathErrors = (values) => {
    if (!values || typeof values !== "object") {
      return REQUIRED_PATH_FIELDS.slice();
    }
    const entries = [];
    REQUIRED_PATH_FIELDS.forEach((field) => {
      const rawValue = values[field.name];
      const normalized =
        typeof rawValue === "string" ? rawValue.trim() : rawValue != null ? String(rawValue).trim() : "";
      if (!normalized) {
        entries.push({ field: field.name, message: field.message });
      }
    });
    return entries;
  };

  const normalizeDetailEntries = (details, fieldContext = null) => {
    if (details == null) {
      return [];
    }

    const results = [];
    const visit = (value, context) => {
      if (value == null) {
        return;
      }

      const valueType = typeof value;

      if (valueType === "string" || valueType === "number" || valueType === "boolean") {
        if (context) {
          results.push({ field: context, message: value });
        } else {
          results.push(String(value));
        }
        return;
      }

      if (Array.isArray(value)) {
        value.forEach((item) => visit(item, context));
        return;
      }

      if (valueType === "object") {
        const knownField = value.field ?? value.name ?? value.key ?? null;
        const primitiveMessageKey = ["message", "error", "detail"].find((key) => {
          const candidate = value[key];
          return (
            typeof candidate === "string" ||
            typeof candidate === "number" ||
            typeof candidate === "boolean"
          );
        });

        if (knownField || primitiveMessageKey) {
          const entry = { ...value };
          if (!knownField && context) {
            entry.field = context;
          }
          results.push(entry);
          return;
        }

        const detailKeys = new Set(["message", "error", "detail", "errors", "non_field_errors"]);
        Object.entries(value).forEach(([key, nested]) => {
          const nextContext = detailKeys.has(key) ? context : context || key;
          visit(nested, nextContext);
        });
        return;
      }

      results.push(String(value));
    };

    visit(details, fieldContext);
    return results;
  };

  const applyFieldErrorHighlights = (details, container = fieldsContainer) => {
    if (!container) return [];
    const entries = normalizeDetailEntries(details);
    const messages = [];
    entries.forEach((entry) => {
      if (entry == null) {
        return;
      }
      if (typeof entry === "string") {
        const trimmed = entry.trim();
        if (trimmed) {
          messages.push(trimmed);
        }
        return;
      }
      if (typeof entry === "object") {
        const fieldName = entry.field || entry.name || entry.key || null;
        const rawMessage =
          entry.message || entry.error || entry.detail || JSON.stringify(entry);
        const trimmedMessage =
          typeof rawMessage === "string" && rawMessage.trim().length
            ? rawMessage.trim()
            : typeof rawMessage === "string"
            ? rawMessage
            : String(rawMessage);
        if (fieldName) {
          const selector = `.config-field[data-name="${escapeSelector(fieldName)}"]`;
          const field = container.querySelector(selector);
          if (field) {
            field.classList.add("is-error");
            field
              .querySelectorAll(".value-input, textarea[data-multiline]")
              .forEach((control) => control.setAttribute("aria-invalid", "true"));
          }
          messages.push(`${fieldName}: ${trimmedMessage}`);
        } else if (trimmedMessage) {
          messages.push(trimmedMessage);
        }
        return;
      }
      messages.push(String(entry));
    });
    return messages;
  };

  const extractFirstText = (value) => {
    if (value == null) {
      return "";
    }

    const valueType = typeof value;
    if (valueType === "string") {
      return value.trim();
    }
    if (valueType === "number" || valueType === "boolean") {
      return String(value);
    }
    if (Array.isArray(value)) {
      for (const item of value) {
        const text = extractFirstText(item);
        if (text) {
          return text;
        }
      }
      return "";
    }
    if (valueType === "object") {
      const prioritized = ["error", "detail", "message", "title"];
      for (const key of prioritized) {
        if (Object.prototype.hasOwnProperty.call(value, key)) {
          const text = extractFirstText(value[key]);
          if (text) {
            return text;
          }
        }
      }
      for (const nested of Object.values(value)) {
        const text = extractFirstText(nested);
        if (text) {
          return text;
        }
      }
    }
    return "";
  };

  const selectDetailSource = (data) => {
    if (data == null) {
      return null;
    }
    if (Array.isArray(data)) {
      return data;
    }
    if (typeof data === "object") {
      if (data.details !== undefined) {
        return data.details;
      }
      if (data.detail !== undefined) {
        return data.detail;
      }
      if (data.errors !== undefined) {
        return data.errors;
      }
      if (Array.isArray(data.message) || (typeof data.message === "object" && data.message !== null)) {
        return data.message;
      }
      if (Array.isArray(data.error) || (typeof data.error === "object" && data.error !== null)) {
        return data.error;
      }
      const excludedKeys = new Set([
        "error",
        "detail",
        "message",
        "title",
        "status",
        "type",
        "code",
      ]);
      const fallbackEntries = Object.entries(data).filter(([key]) => !excludedKeys.has(key));
      if (fallbackEntries.length) {
        return Object.fromEntries(fallbackEntries);
      }
    }
    return null;
  };

  const buildErrorStatusPayload = (
    data,
    { defaultSummary = "No se pudo guardar la configuración.", container = fieldsContainer } = {},
  ) => {
    const detailSource = selectDetailSource(data);
    const normalizedDetails = normalizeDetailEntries(detailSource);

    const summaryCandidates = [];
    if (typeof data === "string" || typeof data === "number" || typeof data === "boolean") {
      summaryCandidates.push(data);
    } else if (Array.isArray(data)) {
      summaryCandidates.push(...data);
    } else if (data && typeof data === "object") {
      summaryCandidates.push(data.error, data.detail, data.message, data.title);
    }

    if (!summaryCandidates.length && normalizedDetails.length) {
      summaryCandidates.push(...normalizedDetails);
    }

    const summary =
      summaryCandidates.map((candidate) => extractFirstText(candidate)).find((text) => text?.length) ||
      defaultSummary;
    const details = applyFieldErrorHighlights(detailSource, container);
    return { summary, details };
  };

  const normalizeScheduleData = (data) => {
    const mode = data?.mode === "once" ? "once" : "cron";
    const expression =
      typeof data?.expression === "string" ? data.expression.trim() : "";
    const datetime =
      typeof data?.datetime === "string" ? data.datetime.trim() : "";
    if (mode === "cron") {
      return { mode, expression, datetime: "" };
    }
    return { mode, expression: "", datetime };
  };

  const updateScheduleModeUI = (mode) => {
    const normalized = mode === "once" ? "once" : "cron";
    if (scheduleModeSelect) {
      scheduleModeSelect.value = normalized;
    }
    if (scheduleExpressionField) {
      scheduleExpressionField.hidden = normalized !== "cron";
    }
    if (scheduleExpressionInput) {
      scheduleExpressionInput.disabled = normalized !== "cron";
      if (normalized !== "cron") {
        scheduleExpressionInput.removeAttribute("aria-invalid");
      }
    }
    if (scheduleDatetimeField) {
      scheduleDatetimeField.hidden = normalized !== "once";
    }
    if (scheduleDatetimeInput) {
      scheduleDatetimeInput.disabled = normalized !== "once";
      if (normalized !== "once") {
        scheduleDatetimeInput.removeAttribute("aria-invalid");
      }
    }
  };

  const populateSchedule = (data) => {
    const normalized = normalizeScheduleData(data);
    if (scheduleModeSelect) {
      scheduleModeSelect.value = normalized.mode;
    }
    updateScheduleModeUI(normalized.mode);
    clearFieldErrors(scheduleFieldsContainer);
    if (scheduleExpressionInput) {
      scheduleExpressionInput.value = normalized.expression;
    }
    if (scheduleDatetimeInput) {
      scheduleDatetimeInput.value = normalized.datetime;
    }
    lastScheduleSnapshot = normalized;
  };

  const prepareSchedulePayload = () => {
    const errors = [];
    const rawMode = scheduleModeSelect?.value ?? "";
    const normalizedMode = rawMode === "once" ? "once" : rawMode === "cron" ? "cron" : null;
    const payload = {};

    if (!normalizedMode) {
      errors.push({ field: "mode", message: "Selecciona un modo válido." });
      return { payload: null, errors };
    }

    payload.mode = normalizedMode;

    if (normalizedMode === "cron") {
      const trimmedExpression = (scheduleExpressionInput?.value ?? "").trim();
      if (!trimmedExpression) {
        errors.push({ field: "expression", message: "Indica una expresión cron." });
      } else {
        payload.expression = trimmedExpression;
      }
    } else {
      const trimmedDatetime = (scheduleDatetimeInput?.value ?? "").trim();
      if (!trimmedDatetime) {
        errors.push({ field: "datetime", message: "Indica una fecha y hora válidas." });
      } else if (Number.isNaN(Date.parse(trimmedDatetime))) {
        errors.push({
          field: "datetime",
          message: "Usa un formato ISO 8601 válido (ej.: 2030-05-10T12:30:00+02:00).",
        });
      } else {
        payload.datetime = trimmedDatetime;
      }
    }

    return { payload, errors };
  };

  const fetchSchedule = async ({ showLoadingStatus = false } = {}) => {
    clearFieldErrors(scheduleFieldsContainer);
    if (showLoadingStatus) {
      showStatus(scheduleStatus, "Cargando programación…");
    } else {
      hideStatus(scheduleStatus);
    }
    try {
      const response = await scheduleApi.load();
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        const requestError = new Error("REQUEST_FAILED");
        requestError.status = response.status;
        requestError.data = data;
        throw requestError;
      }
      if (data) {
        populateSchedule(data);
      } else {
        populateSchedule({ mode: "cron", expression: "", datetime: "" });
      }
      showStatus(scheduleStatus, "Programación cargada correctamente.", "success");
      setTimeout(() => hideStatus(scheduleStatus), 2500);
      return true;
    } catch (error) {
      console.error(error);
      if (error?.message === "UNAUTHORIZED") {
        showStatus(
          scheduleStatus,
          "No se pudo cargar la programación: introduce un token válido.",
          "error",
        );
      } else {
        showStatus(scheduleStatus, "No se pudo cargar la programación.", "error");
      }
      return false;
    }
  };

  const submitSchedule = async (event) => {
    event.preventDefault();
    hideStatus(scheduleStatus);
    clearFieldErrors(scheduleFieldsContainer);
    const { payload, errors } = prepareSchedulePayload();
    if (errors.length) {
      const detailMessages = applyFieldErrorHighlights(errors, scheduleFieldsContainer);
      showStatus(
        scheduleStatus,
        {
          summary: "Revisa la programación antes de guardar.",
          details: detailMessages,
        },
        "error",
      );
      return;
    }
    try {
      const response = await scheduleApi.save(payload);
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        const requestError = new Error("REQUEST_FAILED");
        requestError.status = response.status;
        requestError.data = data;
        throw requestError;
      }
      if (data) {
        populateSchedule(data);
      } else if (payload) {
        populateSchedule(payload);
      }
      showStatus(scheduleStatus, "Programación guardada.", "success");
      setTimeout(() => hideStatus(scheduleStatus), 2500);
    } catch (error) {
      console.error(error);
      if (error?.message === "UNAUTHORIZED") {
        showStatus(
          scheduleStatus,
          "No se pudo guardar la programación porque falta un token válido.",
          "error",
        );
        return;
      }
      if (error?.data) {
        const statusPayload = buildErrorStatusPayload(error.data, {
          defaultSummary: "No se pudo guardar la programación.",
          container: scheduleFieldsContainer,
        });
        showStatus(scheduleStatus, statusPayload, "error");
        return;
      }
      showStatus(
        scheduleStatus,
        "No se pudo guardar la programación. Revisa los datos e inténtalo de nuevo.",
        "error",
      );
    }
  };

  const resetSchedule = () => {
    clearFieldErrors(scheduleFieldsContainer);
    if (!lastScheduleSnapshot) {
      scheduleForm?.reset();
      updateScheduleModeUI(scheduleModeSelect?.value ?? "cron");
      hideStatus(scheduleStatus);
      return;
    }
    populateSchedule(lastScheduleSnapshot);
    showStatus(scheduleStatus, "Se restauró la programación cargada.");
    setTimeout(() => hideStatus(scheduleStatus), 2500);
  };

  const booleanValue = (value) => {
    if (typeof value === "boolean") return value;
    if (typeof value === "string") return value.toLowerCase() === "true";
    return Boolean(value);
  };

  const createField = (variable, values, multilineValues, multilineSet) => {
    const wrapper = document.createElement("div");
    wrapper.className = "config-field";
    wrapper.dataset.name = variable.name;

    const label = document.createElement("label");
    label.htmlFor = `field-${variable.name}`;

    const isBaseDirField = variable.name === "BASE_DIR";
    const isLogDirField = variable.name === "LOG_DIR";
    if (isBaseDirField) {
      label.textContent = "Carpeta de proyectos docker-compose";
    } else if (isLogDirField) {
      label.textContent = "Carpeta de logs del updater";
    } else {
      label.textContent = variable.name;
    }
    wrapper.appendChild(label);

    const inputContainer = document.createElement("div");
    inputContainer.className = "field-input";

    const hasValue =
      values && Object.prototype.hasOwnProperty.call(values, variable.name);
    const defaultValue = hasValue ? values[variable.name] : variable.default;
    let control;

    if (isBaseDirField || isLogDirField) {
      control = document.createElement("input");
      control.type = "text";
      control.id = `field-${variable.name}`;
      control.classList.add("value-input");
      if (isBaseDirField) {
        control.classList.add("base-dir-input");
      } else if (isLogDirField) {
        control.classList.add("log-dir-input");
      }
      control.dataset.type = variable.type;
      const placeholder = isBaseDirField
        ? "Introduce una ruta absoluta (ej.: /ruta/a/proyectos)"
        : "Introduce una ruta absoluta existente";
      control.placeholder = placeholder;
      control.spellcheck = false;
      if (variable.constraints?.pattern) {
        control.pattern = variable.constraints.pattern;
      }
      control.value = defaultValue ?? "";
    } else if (variable.type === "boolean") {
      control = document.createElement("input");
      control.type = "checkbox";
      control.id = `field-${variable.name}`;
      control.className = "value-input";
      control.dataset.type = "boolean";
      control.checked = booleanValue(defaultValue);
    } else if (
      variable.constraints && Array.isArray(variable.constraints.allowed_values) &&
      variable.constraints.allowed_values.length > 0
    ) {
      control = document.createElement("select");
      control.id = `field-${variable.name}`;
      control.className = "value-input";
      control.dataset.type = variable.type;
      const allowed = variable.constraints.allowed_values;
      allowed.forEach((option) => {
        const opt = document.createElement("option");
        opt.value = option;
        opt.textContent = option;
        if (String(option) === String(defaultValue)) {
          opt.selected = true;
        }
        control.appendChild(opt);
      });
    } else {
      control = document.createElement(variable.multiline ? "textarea" : "input");
      if (variable.multiline) {
        control.classList.add("multiline-input");
      }
      control.id = `field-${variable.name}`;
      control.classList.add("value-input");
      control.dataset.type = variable.type;
      if (variable.type === "integer") {
        control.type = "number";
        control.step = "1";
      } else if (!variable.multiline) {
        control.type = "text";
      }
      control.value = defaultValue ?? "";
    }

    if (control) {
      control.setAttribute("aria-describedby", `field-${variable.name}-description`);
    }
    inputContainer.appendChild(control);

    const descriptionId = `field-${variable.name}-description`;

    if (multilineSet.has(variable.name)) {
      const area = document.createElement("textarea");
      area.className = "multiline-input";
      area.id = `field-${variable.name}-content`;
      area.dataset.multiline = variable.name;
      area.placeholder =
        variable.description || `Introduce el contenido asociado a ${variable.name}`;
      area.setAttribute("aria-labelledby", descriptionId);
      area.value = multilineValues?.[variable.name] ?? "";
      inputContainer.appendChild(area);
    }

    wrapper.appendChild(inputContainer);

    const description = document.createElement("p");
    description.className = "field-description";
    description.id = descriptionId;
    if (isBaseDirField || isLogDirField) {
      const helpLines = [];
      if (variable.description) {
        helpLines.push(variable.description);
      }
      if (isBaseDirField) {
        helpLines.push(
          "Ruta absoluta de la carpeta donde se buscarán los proyectos Docker Compose.",
        );
        helpLines.push(
          "Debe existir antes de ejecutar el script y contener los proyectos docker-compose en sus subdirectorios.",
        );
      } else {
        helpLines.push(
          "Directorio absoluto donde se almacenarán los logs diarios del updater.",
        );
        helpLines.push(
          "Asegúrate de crear la carpeta con permisos de escritura antes de lanzar el script.",
        );
      }
      if (helpLines.length) {
        description.textContent = helpLines[0];
        helpLines.slice(1).forEach((line) => {
          description.appendChild(document.createElement("br"));
          const span = document.createElement("span");
          span.textContent = line;
          description.appendChild(span);
        });
      }
    } else {
      description.textContent = variable.description || "Sin descripción";
    }

    if (variable.default !== undefined && variable.default !== null && String(variable.default).length) {
      const defaultTag = document.createElement("span");
      defaultTag.className = "field-default";
      defaultTag.textContent = `Valor por defecto: ${variable.default}`;
      description.appendChild(document.createElement("br"));
      description.appendChild(defaultTag);
    }

    wrapper.appendChild(description);
    return wrapper;
  };

  const populateConfig = (data) => {
    const { schema, values, multiline, meta } = data;
    fieldsContainer.innerHTML = "";
    const multilineSet = new Set(meta?.multiline_fields ?? []);
    schema?.variables?.forEach((variable) => {
      const field = createField(variable, values, multiline, multilineSet);
      fieldsContainer.appendChild(field);
    });
    lastConfigSnapshot = data;
  };

  const readFormValues = () => {
    const payload = { values: {}, multiline: {} };
    fieldsContainer.querySelectorAll(".config-field").forEach((field) => {
      const name = field.dataset.name;
      if (!name) return;
      const control = field.querySelector(".value-input");
      if (!control) return;
      const type = control.dataset.type;
      if (type === "boolean") {
        payload.values[name] = control.checked;
      } else if (type === "integer") {
        payload.values[name] = control.value === "" ? null : Number(control.value);
      } else {
        const rawValue = control.value;
        payload.values[name] =
          name === "BASE_DIR" || name === "LOG_DIR" ? rawValue.trim() : rawValue;
      }
      const multilineControl = field.querySelector("textarea[data-multiline]");
      if (multilineControl) {
        payload.multiline[name] = multilineControl.value;
      }
    });
    if (Object.keys(payload.multiline).length === 0) {
      delete payload.multiline;
    }
    return payload;
  };

  const fetchConfig = async ({ showLoadingStatus = false } = {}) => {
    if (showLoadingStatus) {
      showStatus(configStatus, "Cargando configuración inicial…");
    } else {
      hideStatus(configStatus);
    }
    try {
      const response = await authorizedFetch(buildApiUrl("config"));
      if (!response.ok) {
        throw new Error(`Error HTTP ${response.status}`);
      }
      const data = await response.json();
      populateConfig(data);
      const missingPathErrors = collectMissingPathErrors(data?.values);
      if (missingPathErrors.length) {
        applyFieldErrorHighlights(missingPathErrors);
        showStatus(
          configStatus,
          {
            summary: "Configura las rutas obligatorias antes de ejecutar el updater.",
            details: missingPathErrors,
          },
          "error",
        );
      } else {
        showStatus(configStatus, "Configuración cargada correctamente.", "success");
        setTimeout(() => hideStatus(configStatus), 2500);
      }
      return true;
    } catch (error) {
      console.error(error);
      if (error?.message === "UNAUTHORIZED") {
        showStatus(
          configStatus,
          "No se pudo cargar la configuración: introduce un token válido.",
          "error",
        );
      } else {
        showStatus(
          configStatus,
          "Token válido, pero el backend no devolvió la configuración. Revisa el servicio e inténtalo de nuevo.",
          "error",
        );
      }
      return false;
    }
  };

  const submitConfig = async (event) => {
    event.preventDefault();
    hideStatus(configStatus);
    clearFieldErrors();
    const payload = readFormValues();
    const missingPathErrors = collectMissingPathErrors(payload.values);
    if (missingPathErrors.length) {
      applyFieldErrorHighlights(missingPathErrors);
      showStatus(
        configStatus,
        {
          summary: "Completa las rutas obligatorias antes de guardar.",
          details: missingPathErrors,
        },
        "error",
      );
      return;
    }
    try {
      const response = await authorizedFetch(buildApiUrl("config"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        const requestError = new Error("REQUEST_FAILED");
        requestError.status = response.status;
        requestError.data = data;
        throw requestError;
      }
      if (data) {
        populateConfig(data);
      }
      showStatus(configStatus, "Cambios guardados.", "success");
    } catch (error) {
      console.error(error);
      if (error?.message === "UNAUTHORIZED") {
        showStatus(
          configStatus,
          "No se pudo guardar la configuración porque falta un token válido.",
          "error",
        );
        return;
      }
      if (error?.data) {
        const statusPayload = buildErrorStatusPayload(error.data);
        showStatus(configStatus, statusPayload, "error");
        return;
      }
      showStatus(
        configStatus,
        "No se pudo guardar la configuración. Revisa los datos e inténtalo de nuevo.",
        "error",
      );
    }
  };

  const resetConfig = () => {
    if (!lastConfigSnapshot) return;
    populateConfig(lastConfigSnapshot);
    const missingPathErrors = collectMissingPathErrors(lastConfigSnapshot.values);
    if (missingPathErrors.length) {
      applyFieldErrorHighlights(missingPathErrors);
      showStatus(
        configStatus,
        {
          summary: "Se restauraron los valores cargados. Completa las rutas obligatorias antes de guardar.",
          details: missingPathErrors,
        },
        "error",
      );
    } else {
      showStatus(configStatus, "Se restauraron los valores cargados.");
      setTimeout(() => hideStatus(configStatus), 2500);
    }
  };

  const logsRequestManager = createLogsRequestManager();

  const fetchLogs = async (selectedName = null, { showLoadingStatus = false } = {}) => {
    if (showLoadingStatus) {
      showStatus(logsStatus, "Cargando lista de logs…");
      if (logSelect) {
        logSelect.disabled = true;
      }
      if (logContent) {
        logContent.textContent = "Cargando logs…";
      }
    } else {
      hideStatus(logsStatus);
    }
    const request = logsRequestManager.start();
    const { id, controller, release } = request;
    const signal = logsRequestManager.getSignal(controller);
    const logsUrl = new URL(buildApiUrl("logs"));
    if (selectedName) {
      logsUrl.searchParams.set("name", selectedName);
    }
    const url = logsUrl.toString();
    try {
      const response = await authorizedFetch(url, signal ? { signal } : {});
      if (!response.ok) {
        throw new Error(`Error HTTP ${response.status}`);
      }
      const data = await response.json();
      if (!logsRequestManager.isLatest(id)) {
        return false;
      }
      renderLogs(data);
      return true;
    } catch (error) {
      if (error?.name === "AbortError") {
        return false;
      }
      if (!logsRequestManager.isLatest(id)) {
        return false;
      }
      console.error(error);
      if (error?.message === "UNAUTHORIZED") {
        if (logSelect) {
          logSelect.innerHTML = "";
          logSelect.disabled = true;
        }
        if (logMeta) {
          logMeta.textContent = "";
        }
        showStatus(logsStatus, "Introduce un token válido para consultar los logs.", "error");
        logContent.textContent = "Introduce un token válido para ver los logs.";
      } else {
        if (logSelect) {
          logSelect.innerHTML = "";
          logSelect.disabled = true;
        }
        if (logMeta) {
          logMeta.textContent = "";
        }
        showStatus(logsStatus, "No se pudieron cargar los logs.", "error");
        logContent.textContent = "Sin datos disponibles.";
      }
      return false;
    } finally {
      release?.();
    }
  };

  const renderLogs = (data) => {
    const files = Array.isArray(data.files) ? data.files : [];
    const notice =
      data && typeof data.notice === "string" && data.notice.trim().length
        ? data.notice.trim()
        : "";
    logSelect.innerHTML = "";

    if (notice) {
      showStatus(logsStatus, notice, "error");
    } else {
      hideStatus(logsStatus);
    }

    if (files.length === 0) {
      const option = document.createElement("option");
      option.textContent = "Sin archivos de log";
      option.disabled = true;
      option.selected = true;
      logSelect.appendChild(option);
      logSelect.disabled = true;
      logContent.textContent =
        notice || "No se encontraron archivos .log en el directorio configurado.";
      logMeta.textContent = data.log_dir ? `Directorio: ${data.log_dir}` : "";
      return;
    }

    logSelect.disabled = false;
    files.forEach((file) => {
      const option = document.createElement("option");
      option.value = file.name;
      const formattedDate = file.modified
        ? new Date(file.modified).toLocaleString()
        : "sin fecha";
      option.textContent = `${file.name} · ${formattedDate}`;
      logSelect.appendChild(option);
    });

    const selectedName = data.selected?.name || logSelect.options[0]?.value;
    if (selectedName) {
      logSelect.value = selectedName;
    }

    logContent.textContent = resolveLogContentText(data.selected);

    const size = data.selected?.size;
    const modified = data.selected?.modified
      ? new Date(data.selected.modified).toLocaleString()
      : "";
    logMeta.textContent = formatLogMetadata({
      logDir: data.log_dir,
      modified,
      size,
    });
  };

  const handleSuccessfulLogin = async ({
    showSuccessMessage = true,
    storageStatus = null,
  } = {}) => {
    setInitialDataLoading(true);
    hideStatus(configStatus);
    hideStatus(scheduleStatus);
    hideStatus(logsStatus);
    if (loginForm) {
      loginForm.reset();
    }
    setAuthState(true);
    let configLoaded = false;
    let scheduleLoaded = false;
    let logsLoaded = false;
    try {
      [configLoaded, scheduleLoaded, logsLoaded] = await Promise.all([
        fetchConfig({ showLoadingStatus: true }),
        fetchSchedule({ showLoadingStatus: true }),
        fetchLogs(null, { showLoadingStatus: true }),
      ]);
    } finally {
      setInitialDataLoading(false);
    }
    const storageOutcome = processStorageStatus(storageStatus, { silent: true });
    const storageMessage = storageOutcome.handled
      ? (storageOutcome.message || "").trim()
      : "";
    const missingSections = [];
    if (!configLoaded) {
      missingSections.push("la configuración");
    }
    if (!scheduleLoaded) {
      missingSections.push("la programación");
    }
    if (!logsLoaded) {
      missingSections.push("los logs");
    }
    if (missingSections.length) {
      const formatMissingSummary = (sections) => {
        if (sections.length === 1) {
          return sections[0];
        }
        const head = sections.slice(0, -1).join(", ");
        const tail = sections[sections.length - 1];
        return `${head} y ${tail}`;
      };
      const missingSummary = formatMissingSummary(missingSections);
      const baseMessage = `Token validado, pero no se pudo cargar ${missingSummary}. Revisa el servicio e inténtalo de nuevo.`;
      const combinedMessage = storageMessage ? `${baseMessage} ${storageMessage}` : baseMessage;
      showLoginMessage(combinedMessage, "error");
    } else if (storageOutcome.handled) {
      showLoginMessage(storageMessage, storageOutcome.tone || "error");
    } else if (showSuccessMessage) {
      showLoginMessage("Token validado. Puedes usar la interfaz con normalidad.", "success");
    } else {
      showLoginMessage("", "info");
    }
  };

  const showLoginPrompt = (
    tone = "info",
    message = "Introduce el token bearer para continuar. Marca «Recordar token» solo si el equipo es de confianza.",
  ) => {
    setAuthState(false);
    showLoginMessage(message, tone);
    tokenInput?.focus();
  };

  loginForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const value = tokenInput?.value?.trim() ?? "";
    if (!value) {
      showLoginMessage("Debes introducir un token para continuar.", "error");
      tokenInput?.focus();
      return;
    }
    showLoginMessage("Verificando token…", "info");
    try {
      const shouldPersist = rememberCheckbox?.checked ?? false;
      const verification = await verifyToken(value, { persist: shouldPersist });
      await handleSuccessfulLogin({ storageStatus: verification?.storageStatus });
    } catch (error) {
      console.error(error);
      if (error?.message === "UNAUTHORIZED" || error?.status === 401) {
        const { message, reason } = resolveUnauthorizedDetails(
          error,
          "El token proporcionado no está autorizado. Vuelve a intentarlo.",
        );
        const finalMessage =
          reason === "missing-credentials"
            ? buildMissingCredentialsMessage(message)
            : message;
        showLoginMessage(finalMessage, "error");
      } else if (error?.message === "NETWORK_ERROR") {
        showLoginMessage(
          "No se pudo verificar el token. Revisa la conexión e inténtalo de nuevo.",
          "error",
        );
      } else if (error?.message === "TOKEN_REQUIRED") {
        showLoginMessage("Debes introducir un token para continuar.", "error");
      } else {
        showLoginMessage("No se pudo verificar el token. Inténtalo de nuevo.", "error");
      }
    }
  });

  const clearSession = (
    message = "Introduce el token bearer para continuar.",
    tone = "info",
  ) => {
    const clearStatus = auth.clearToken();
    const storageOutcome = processStorageStatus(clearStatus, { silent: true });
    loginForm?.reset();
    if (storageOutcome.handled) {
      showLoginPrompt("error", storageOutcome.message);
      return;
    }
    showLoginPrompt(tone, message);
  };

  clearTokenButton?.addEventListener("click", () => {
    clearSession("Se olvidó el token guardado. Introduce uno nuevo.");
  });

  logoutButton?.addEventListener("click", () => {
    clearSession("Sesión cerrada. Introduce un token válido para continuar.");
  });

  updateScheduleModeUI(scheduleModeSelect?.value ?? "cron");

  scheduleModeSelect?.addEventListener("change", (event) => {
    updateScheduleModeUI(event.target?.value ?? "cron");
    clearFieldErrors(scheduleFieldsContainer);
    hideStatus(scheduleStatus);
  });

  scheduleForm?.addEventListener("submit", submitSchedule);
  scheduleResetButton?.addEventListener("click", resetSchedule);

  form.addEventListener("submit", submitConfig);
  resetButton.addEventListener("click", resetConfig);
  logSelect.addEventListener("change", (event) => {
    const { value } = event.target;
    if (!value || logSelect.disabled) return;
    fetchLogs(value);
  });
  refreshLogs.addEventListener("click", () => {
    const selected = logSelect.disabled ? null : logSelect.value;
    fetchLogs(selected || null);
  });

  if (storedToken) {
    showLoginMessage("Verificando token guardado…", "info");
    verifyToken(storedToken, { persist: true })
      .then((verification) =>
        handleSuccessfulLogin({
          showSuccessMessage: false,
          storageStatus: verification?.storageStatus,
        }),
      )
      .catch((error) => {
        console.error(error);
        const isUnauthorized = error?.message === "UNAUTHORIZED" || error?.status === 401;
        if (isUnauthorized) {
          const { message, reason } = resolveUnauthorizedDetails(
            error,
            "El token guardado no es válido. Introduce uno nuevo.",
          );
          if (reason === "missing-credentials") {
            const finalMessage = buildMissingCredentialsMessage(message);
            showLoginPrompt("error", finalMessage);
            return;
          }

          const clearStatus = auth.clearToken();
          const storageOutcome = processStorageStatus(clearStatus, { silent: true });
          const finalMessage = storageOutcome.handled
            ? `${message} ${storageOutcome.message}`
            : message;
          showLoginPrompt("error", finalMessage);
        } else if (error?.message === "NETWORK_ERROR") {
          showLoginPrompt(
            "error",
            "No se pudo verificar el token guardado por un problema de red. Revisa la conexión e inténtalo de nuevo; el token seguirá guardado.",
          );
        } else {
          showLoginPrompt(
            "error",
            "No se pudo verificar el token guardado. Inténtalo de nuevo o introduce uno nuevo.",
          );
        }
      });
  } else {
    if (initialStorageOutcome.handled) {
      showLoginPrompt("error", initialStorageOutcome.message);
    } else {
      showLoginPrompt();
    }
  }
};

if (typeof document !== "undefined") {
  initializeApp();
}
