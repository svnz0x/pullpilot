(() => {
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
  const logSelect = document.getElementById("log-select");
  const logContent = document.getElementById("log-content");
  const logMeta = document.getElementById("log-meta");
  const logsStatus = document.getElementById("logs-status");
  const refreshLogs = document.getElementById("refresh-logs");

  const TOKEN_STORAGE_KEY = "pullpilot.bearerToken";
  let lastConfigSnapshot = null;
  let memoryToken = null;
  let storedToken = null;

  const buildApiUrl = (() => {
    let cachedBase = null;

    const hasProtocol = (value) => /^[a-zA-Z][a-zA-Z\d+.-]*:/.test(value);

    const resolveBase = () => {
      if (cachedBase) {
        return cachedBase;
      }

      const baseElement = document.querySelector("base[href]");
      if (baseElement) {
        const href = baseElement.getAttribute("href");
        if (href) {
          try {
            cachedBase = new URL(href, window.location.href);
            return cachedBase;
          } catch (error) {
            console.warn("Base href inválido; se ignorará.", error);
          }
        }
      }

      const { origin, pathname } = window.location;
      const marker = "/ui/";
      let basePath = "/";

      if (pathname.endsWith("/ui")) {
        basePath = `${pathname}/`;
      } else if (pathname.includes(marker)) {
        basePath = pathname.slice(0, pathname.indexOf(marker) + marker.length);
      } else if (pathname.endsWith("/")) {
        basePath = pathname;
      } else {
        const lastSlashIndex = pathname.lastIndexOf("/");
        basePath = lastSlashIndex >= 0 ? pathname.slice(0, lastSlashIndex + 1) : "/";
      }

      try {
        cachedBase = new URL(basePath, origin);
      } catch (error) {
        console.warn("No se pudo resolver la base a partir de window.location.", error);
        cachedBase = new URL("/", origin);
      }
      return cachedBase;
    };

    return (path = "") => {
      if (path instanceof URL) {
        return path.toString();
      }

      const normalized = typeof path === "string" ? path.trim() : "";
      if (!normalized) {
        return resolveBase().toString();
      }

      if (hasProtocol(normalized)) {
        return normalized;
      }

      const relative = normalized.startsWith("/")
        ? normalized.slice(1)
        : normalized;
      return new URL(relative, resolveBase()).toString();
    };
  })();

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

    return { handled: false, status };
  };

  const readStoredTokenStatus = () => {
    try {
      const token = window.localStorage.getItem(TOKEN_STORAGE_KEY) || null;
      return { ok: true, operation: "read", token };
    } catch (error) {
      return { ok: false, operation: "read", error };
    }
  };

  const storedTokenStatus = readStoredTokenStatus();
  storedToken = storedTokenStatus.ok ? storedTokenStatus.token : null;
  const initialStorageOutcome = processStorageStatus(storedTokenStatus, {
    silent: true,
  });

  const resetPortalState = () => {
    if (fieldsContainer) {
      fieldsContainer.innerHTML = "";
    }
    lastConfigSnapshot = null;
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
      resetPortalState();
    }
  };

  const auth = {
    getToken: () => memoryToken,
    setToken: (token, { persist = false } = {}) => {
      const trimmed = typeof token === "string" ? token.trim() : "";
      memoryToken = trimmed || null;

      if (!memoryToken) {
        try {
          window.localStorage.removeItem(TOKEN_STORAGE_KEY);
          return { ok: true, operation: "remove", persisted: false };
        } catch (error) {
          return { ok: false, operation: "remove", error };
        }
      }

      if (persist) {
        try {
          window.localStorage.setItem(TOKEN_STORAGE_KEY, memoryToken);
          return { ok: true, operation: "write", persisted: true };
        } catch (error) {
          return { ok: false, operation: "write", error };
        }
      }

      try {
        window.localStorage.removeItem(TOKEN_STORAGE_KEY);
        return { ok: true, operation: "remove", persisted: false };
      } catch (error) {
        return { ok: false, operation: "remove", error };
      }
    },
    clearToken: () => {
      memoryToken = null;
      try {
        window.localStorage.removeItem(TOKEN_STORAGE_KEY);
        return { ok: true, operation: "clear" };
      } catch (error) {
        return { ok: false, operation: "clear", error };
      }
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

  const resolveUnauthorizedDetails = (error, fallbackMessage) => {
    const payload = error?.payload;
    const fallback = typeof fallbackMessage === "string" ? fallbackMessage : "";
    const ignoredMessages = new Set(["missing credentials", "unauthorized"]);
    const defaultResult = { message: fallback, reason: "unknown" };

    const gatherMessages = (...sources) => {
      const results = [];
      const visitedObjects =
        typeof WeakSet === "function" ? new WeakSet() : new Set();

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

  const resolveUnauthorizedMessage = (error, fallbackMessage) =>
    resolveUnauthorizedDetails(error, fallbackMessage).message;

  const buildMissingCredentialsMessage = (message) => {
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

    const clearStatus = auth.clearToken();
    const storageOutcome = processStorageStatus(clearStatus, { silent: true });
    loginForm?.reset();
    const finalMessage = storageOutcome.handled
      ? `${message} ${storageOutcome.message}`
      : message;
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

  const clearFieldErrors = () => {
    if (!fieldsContainer) return;
    fieldsContainer.querySelectorAll(".config-field.is-error").forEach((field) => {
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

  const applyFieldErrorHighlights = (details) => {
    if (!fieldsContainer) return [];
    const entries = Array.isArray(details) ? details : details != null ? [details] : [];
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
          const field = fieldsContainer.querySelector(selector);
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

  const buildErrorStatusPayload = (data) => {
    const summary =
      data && typeof data.error === "string" && data.error.trim().length
        ? data.error.trim()
        : "No se pudo guardar la configuración.";
    const details = applyFieldErrorHighlights(data?.details);
    return { summary, details };
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

  const fetchConfig = async () => {
    hideStatus(configStatus);
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

  const fetchLogs = async (selectedName = null) => {
    hideStatus(logsStatus);
    const logsUrl = new URL(buildApiUrl("logs"));
    if (selectedName) {
      logsUrl.searchParams.set("name", selectedName);
    }
    const url = logsUrl.toString();
    try {
      const response = await authorizedFetch(url);
      if (!response.ok) {
        throw new Error(`Error HTTP ${response.status}`);
      }
      const data = await response.json();
      renderLogs(data);
      return true;
    } catch (error) {
      console.error(error);
      if (error?.message === "UNAUTHORIZED") {
        showStatus(logsStatus, "Introduce un token válido para consultar los logs.", "error");
        logContent.textContent = "Introduce un token válido para ver los logs.";
      } else {
        showStatus(logsStatus, "No se pudieron cargar los logs.", "error");
        logContent.textContent = "Sin datos disponibles.";
      }
      return false;
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

    if (data.selected?.content) {
      logContent.textContent = data.selected.content;
    } else if (data.selected) {
      logContent.textContent = "Archivo sin contenido o no legible.";
    } else {
      logContent.textContent = "No hay contenido disponible para el archivo seleccionado.";
    }

    const size = data.selected?.size;
    const modified = data.selected?.modified ? new Date(data.selected.modified).toLocaleString() : "";
    logMeta.textContent = `${data.log_dir ? `Directorio: ${data.log_dir}` : ""}${
      modified ? ` · Última modificación: ${modified}` : ""
    }${size ? ` · Tamaño: ${size} bytes` : ""}`;
  };

  const handleSuccessfulLogin = async ({
    showSuccessMessage = true,
    storageStatus = null,
  } = {}) => {
    setAuthState(true);
    hideStatus(configStatus);
    hideStatus(logsStatus);
    if (loginForm) {
      loginForm.reset();
    }
    const configLoaded = await fetchConfig();
    await fetchLogs();
    const storageOutcome = processStorageStatus(storageStatus, { silent: true });
    const storageMessage = storageOutcome.handled ? storageOutcome.message : "";
    if (!configLoaded) {
      const baseMessage =
        "Token validado, pero no se pudo cargar la configuración. Revisa el servicio e inténtalo de nuevo.";
      const combinedMessage = storageMessage
        ? `${baseMessage} ${storageMessage}`
        : baseMessage;
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
        const message = resolveUnauthorizedMessage(
          error,
          "El token proporcionado no está autorizado. Vuelve a intentarlo.",
        );
        showLoginMessage(message, "error");
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
})();
