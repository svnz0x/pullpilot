const registerElement = (doc, element, id = null) => {
  if (id) {
    element.id = id;
    doc.registerElement(element);
  }
  return element;
};

const createButton = (doc, { id, text = "", type = "button", className = "" } = {}) => {
  const button = doc.createElement("button");
  button.type = type;
  button.textContent = text;
  button.className = className;
  registerElement(doc, button, id);
  return button;
};

const buildLoginSection = (doc, body) => {
  const loginSection = doc.createElement("section");
  registerElement(doc, loginSection, "login-screen");

  const loginForm = doc.createElement("form");
  registerElement(doc, loginForm, "token-form");

  const tokenLabel = doc.createElement("label");
  tokenLabel.setAttribute("for", "token-input");
  const tokenInput = doc.createElement("input");
  tokenInput.type = "password";
  tokenInput.placeholder = "Introduce tu token";
  tokenInput.autocomplete = "off";
  tokenInput.spellcheck = false;
  registerElement(doc, tokenInput, "token-input");
  tokenLabel.appendChild(tokenInput);

  const rememberLabel = doc.createElement("label");
  rememberLabel.className = "remember-token";
  rememberLabel.setAttribute("for", "remember-token");
  const rememberCheckbox = doc.createElement("input");
  rememberCheckbox.type = "checkbox";
  registerElement(doc, rememberCheckbox, "remember-token");
  rememberLabel.appendChild(rememberCheckbox);

  const loginActions = doc.createElement("div");
  loginActions.className = "login-actions";
  const submitButton = createButton(doc, { text: "Iniciar sesión", type: "submit", className: "primary" });
  const clearButton = createButton(doc, { id: "clear-token", text: "Olvidar token", className: "secondary" });
  loginActions.appendChild(submitButton);
  loginActions.appendChild(clearButton);

  const loginStatus = doc.createElement("span");
  registerElement(doc, loginStatus, "login-status");

  loginForm.appendChild(tokenLabel);
  loginForm.appendChild(rememberLabel);
  loginForm.appendChild(loginActions);
  loginForm.appendChild(loginStatus);

  loginSection.appendChild(loginForm);
  body.appendChild(loginSection);
};

const buildConfigSection = (doc, main) => {
  const section = doc.createElement("section");
  registerElement(doc, section, "config-section");

  const form = doc.createElement("form");
  registerElement(doc, form, "config-form");
  const fields = doc.createElement("div");
  fields.className = "config-grid";
  registerElement(doc, fields, "config-fields");
  form.appendChild(fields);

  const actions = doc.createElement("div");
  actions.className = "form-actions";
  const saveButton = createButton(doc, { id: "save-config", text: "Guardar cambios", className: "primary", type: "submit" });
  const resetButton = createButton(doc, { id: "reset-config", text: "Descartar cambios", className: "secondary" });
  const retryButton = createButton(doc, { id: "retry-config", text: "Reintentar carga", className: "secondary" });
  retryButton.hidden = true;
  const testButton = createButton(doc, { id: "test-config", text: "Probar ejecución", className: "secondary" });
  actions.appendChild(saveButton);
  actions.appendChild(resetButton);
  actions.appendChild(retryButton);
  actions.appendChild(testButton);
  form.appendChild(actions);

  const status = doc.createElement("div");
  registerElement(doc, status, "config-status");
  status.hidden = true;

  section.appendChild(form);
  section.appendChild(status);
  main.appendChild(section);
};

const buildScheduleSection = (doc, main) => {
  const section = doc.createElement("section");
  registerElement(doc, section, "schedule-section");

  const form = doc.createElement("form");
  registerElement(doc, form, "schedule-form");
  const fields = doc.createElement("div");
  fields.className = "config-grid";
  registerElement(doc, fields, "schedule-fields");

  const modeField = doc.createElement("div");
  modeField.className = "config-field";
  modeField.dataset.name = "mode";
  const modeSelect = doc.createElement("select");
  registerElement(doc, modeSelect, "schedule-mode");
  modeSelect.className = "value-input";
  const cronOption = doc.createElement("option");
  cronOption.value = "cron";
  cronOption.textContent = "Repetir según cron";
  const onceOption = doc.createElement("option");
  onceOption.value = "once";
  onceOption.textContent = "Ejecutar una sola vez";
  modeSelect.appendChild(cronOption);
  modeSelect.appendChild(onceOption);
  modeSelect.value = "cron";
  modeField.appendChild(modeSelect);

  const expressionField = doc.createElement("div");
  expressionField.className = "config-field";
  expressionField.dataset.name = "expression";
  const expressionInput = doc.createElement("input");
  expressionInput.type = "text";
  expressionInput.className = "value-input";
  registerElement(doc, expressionInput, "schedule-expression");
  expressionField.appendChild(expressionInput);

  const datetimeField = doc.createElement("div");
  datetimeField.className = "config-field";
  datetimeField.dataset.name = "datetime";
  const datetimeInput = doc.createElement("input");
  datetimeInput.type = "text";
  datetimeInput.className = "value-input";
  registerElement(doc, datetimeInput, "schedule-datetime");
  datetimeField.appendChild(datetimeInput);
  datetimeField.hidden = true;

  fields.appendChild(modeField);
  fields.appendChild(expressionField);
  fields.appendChild(datetimeField);

  const actions = doc.createElement("div");
  actions.className = "form-actions";
  const saveButton = createButton(doc, { id: "save-schedule", text: "Guardar programación", className: "primary", type: "submit" });
  const resetButton = createButton(doc, { id: "reset-schedule", text: "Descartar cambios", className: "secondary" });
  actions.appendChild(saveButton);
  actions.appendChild(resetButton);

  form.appendChild(fields);
  form.appendChild(actions);

  const status = doc.createElement("div");
  registerElement(doc, status, "schedule-status");
  status.hidden = true;

  section.appendChild(form);
  section.appendChild(status);
  main.appendChild(section);
};

const buildLogsSection = (doc, main) => {
  const section = doc.createElement("section");
  registerElement(doc, section, "logs-section");

  const header = doc.createElement("div");
  header.className = "logs-header";
  const logSelect = doc.createElement("select");
  registerElement(doc, logSelect, "log-select");
  const refreshButton = createButton(doc, { id: "refresh-logs", text: "Actualizar", className: "secondary" });
  const logMeta = doc.createElement("span");
  registerElement(doc, logMeta, "log-meta");
  header.appendChild(logSelect);
  header.appendChild(refreshButton);
  header.appendChild(logMeta);

  const logsStatus = doc.createElement("div");
  registerElement(doc, logsStatus, "logs-status");
  logsStatus.hidden = true;
  const logContent = doc.createElement("pre");
  logContent.textContent = "Cargando logs…";
  registerElement(doc, logContent, "log-content");

  section.appendChild(header);
  section.appendChild(logsStatus);
  section.appendChild(logContent);
  main.appendChild(section);
};

export const buildAppShell = (doc) => {
  const body = doc.body;
  body.className = "requires-auth";

  const header = doc.createElement("header");
  const logoutButton = createButton(doc, {
    id: "logout-button",
    text: "Olvidar token actual",
    className: "secondary logout-button",
  });
  header.appendChild(logoutButton);
  body.appendChild(header);

  buildLoginSection(doc, body);

  const main = doc.createElement("main");
  body.appendChild(main);

  const initialLoadingBanner = doc.createElement("div");
  registerElement(doc, initialLoadingBanner, "initial-loading-banner");
  initialLoadingBanner.className = "initial-loading-banner";
  initialLoadingBanner.hidden = true;
  main.appendChild(initialLoadingBanner);

  buildConfigSection(doc, main);
  buildScheduleSection(doc, main);
  buildLogsSection(doc, main);
};
