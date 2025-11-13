import { parentPort } from "node:worker_threads";

class FakeClassList {
  constructor() {
    this.classes = new Set();
  }
  add(...names) {
    names.forEach((name) => this.classes.add(name));
  }
  remove(...names) {
    names.forEach((name) => this.classes.delete(name));
  }
  toggle(name, force) {
    if (force === true) {
      this.classes.add(name);
      return true;
    }
    if (force === false) {
      this.classes.delete(name);
      return false;
    }
    if (this.classes.has(name)) {
      this.classes.delete(name);
      return false;
    }
    this.classes.add(name);
    return true;
  }
  contains(name) {
    return this.classes.has(name);
  }
}

class FakeEvent {
  constructor(type, { bubbles = false, cancelable = false } = {}) {
    this.type = type;
    this.bubbles = bubbles;
    this.cancelable = cancelable;
    this.defaultPrevented = false;
    this.target = null;
  }
  preventDefault() {
    if (this.cancelable) {
      this.defaultPrevented = true;
    }
  }
}

class FakeElement {
  constructor(id = null, tagName = "div") {
    this.id = id;
    this.tagName = tagName.toUpperCase();
    this.dataset = {};
    this.children = [];
    this.classList = new FakeClassList();
    this.attributes = new Map();
    this.listeners = new Map();
    this.disabled = false;
    this.hidden = false;
    this.textContent = "";
    this.value = "";
    this.checked = false;
    this.innerHTML = "";
    this.parentElement = null;
  }
  appendChild(child) {
    child.parentElement = this;
    this.children.push(child);
    return child;
  }
  removeChild(child) {
    const index = this.children.indexOf(child);
    if (index >= 0) {
      this.children.splice(index, 1);
      child.parentElement = null;
    }
    return child;
  }
  addEventListener(type, handler) {
    if (!this.listeners.has(type)) {
      this.listeners.set(type, []);
    }
    this.listeners.get(type).push(handler);
  }
  dispatchEvent(event) {
    event.target = this;
    const handlers = this.listeners.get(event.type) || [];
    for (const handler of handlers) {
      handler.call(this, event);
    }
    return !event.defaultPrevented;
  }
  querySelector() {
    return null;
  }
  querySelectorAll() {
    return [];
  }
  focus() {}
  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }
  removeAttribute(name) {
    this.attributes.delete(name);
  }
  reset() {}
}

class FakeFormElement extends FakeElement {
  constructor(id) {
    super(id, "form");
  }
  reset() {
    if (this.id === "token-form") {
      const tokenInput = elementsById.get("token-input");
      if (tokenInput) {
        tokenInput.value = "";
      }
      const remember = elementsById.get("remember-token");
      if (remember) {
        remember.checked = false;
      }
    }
  }
}

class ScheduleFieldsElement extends FakeElement {
  constructor() {
    super("schedule-fields");
    this.expressionField = new FakeElement(null, "div");
    this.expressionField.dataset.name = "expression";
    this.datetimeField = new FakeElement(null, "div");
    this.datetimeField.dataset.name = "datetime";
  }
  querySelector(selector) {
    if (selector === '[data-name="expression"]') {
      return this.expressionField;
    }
    if (selector === '[data-name="datetime"]') {
      return this.datetimeField;
    }
    return null;
  }
}

class FakeSelectElement extends FakeElement {
  constructor(id) {
    super(id, "select");
    this.options = [];
  }
  appendChild(option) {
    this.options.push(option);
    return super.appendChild(option);
  }
  get value() {
    return this._value ?? "";
  }
  set value(next) {
    this._value = next;
  }
}

class FakeOptionElement extends FakeElement {
  constructor(value = "") {
    super(null, "option");
    this.value = value;
    this.disabled = false;
    this.selected = false;
  }
}

class MemoryStorage {
  constructor() {
    this.store = new Map();
  }
  getItem(key) {
    return this.store.has(key) ? this.store.get(key) : null;
  }
  setItem(key, value) {
    this.store.set(key, String(value));
  }
  removeItem(key) {
    this.store.delete(key);
  }
  clear() {
    this.store.clear();
  }
}

const elementsById = new Map();

const body = new FakeElement("body", "body");
body.classList = new FakeClassList();

const loginForm = registerElement(new FakeFormElement("token-form"));
const tokenInput = registerElement(new FakeElement("token-input", "input"));
const loginStatus = registerElement(new FakeElement("login-status", "div"));
const clearToken = registerElement(new FakeElement("clear-token", "button"));
const rememberCheckbox = registerElement(new FakeElement("remember-token", "input"));
const logoutButton = registerElement(new FakeElement("logout-button", "button"));
const configForm = registerElement(new FakeFormElement("config-form"));
const configFields = registerElement(new FakeElement("config-fields", "div"));
const resetConfigButton = registerElement(new FakeElement("reset-config", "button"));
const configStatus = registerElement(new FakeElement("config-status", "div"));
const scheduleForm = registerElement(new FakeFormElement("schedule-form"));
const scheduleFields = registerElement(new ScheduleFieldsElement());
const scheduleMode = registerElement(new FakeSelectElement("schedule-mode"));
scheduleMode.value = "cron";
const scheduleExpression = registerElement(new FakeElement("schedule-expression", "input"));
const scheduleDatetime = registerElement(new FakeElement("schedule-datetime", "input"));
const scheduleStatus = registerElement(new FakeElement("schedule-status", "div"));
const scheduleReset = registerElement(new FakeElement("reset-schedule", "button"));
const logSelect = registerElement(new FakeSelectElement("log-select"));
const logContent = registerElement(new FakeElement("log-content", "pre"));
const logMeta = registerElement(new FakeElement("log-meta", "div"));
const logsStatus = registerElement(new FakeElement("logs-status", "div"));
const refreshLogs = registerElement(new FakeElement("refresh-logs", "button"));

function registerElement(element) {
  if (element.id) {
    elementsById.set(element.id, element);
  }
  return element;
}

const documentStub = {
  body,
  getElementById(id) {
    return elementsById.get(id) ?? null;
  },
  querySelector(selector) {
    if (selector === "base[href]") {
      return null;
    }
    return null;
  },
  createElement(tag) {
    if (tag === "option") {
      return new FakeOptionElement();
    }
    return new FakeElement(null, tag);
  },
};

const windowStub = {
  document: documentStub,
  localStorage: new MemoryStorage(),
  sessionStorage: new MemoryStorage(),
  location: {
    origin: "https://example.test",
    protocol: "https:",
    host: "example.test",
    pathname: "/ui/",
    href: "https://example.test/ui/",
  },
  URL,
  Request,
  Headers,
  Response,
  setTimeout,
  clearTimeout,
};

globalThis.window = windowStub;
globalThis.document = documentStub;
globalThis.localStorage = windowStub.localStorage;
globalThis.sessionStorage = windowStub.sessionStorage;
if (!globalThis.navigator) {
  windowStub.navigator = { userAgent: "fake" };
  globalThis.navigator = windowStub.navigator;
} else {
  windowStub.navigator = globalThis.navigator;
}
globalThis.URL = URL;
globalThis.Request = Request;
globalThis.Headers = Headers;
globalThis.Response = Response;
globalThis.setTimeout = setTimeout;
globalThis.clearTimeout = clearTimeout;
globalThis.Event = FakeEvent;
globalThis.CustomEvent = FakeEvent;

const fetchQueue = [];

globalThis.fetch = async (input, init = {}) => {
  const next = fetchQueue.shift();
  if (!next) {
    throw new Error(`Unexpected fetch for ${typeof input === "object" ? input.url ?? "object" : input}`);
  }
  return next(input, init);
};

const okResponse = (body) =>
  Promise.resolve(
    new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );

const unauthorizedResponse = () =>
  Promise.resolve(
    new Response(JSON.stringify({ detail: "Unauthorized" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    }),
  );

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

const tokenValue = "demo-token";

await import(new URL("../src/app.js", import.meta.url));

rememberCheckbox.checked = true;
tokenInput.value = tokenValue;

enqueueResponses([
  () => okResponse({}),
  () => unauthorizedResponse(),
  () => okResponse({ mode: "cron", expression: "", datetime: "" }),
  () => okResponse({ files: [], selected: null, log_dir: "/logs" }),
]);

loginForm.dispatchEvent(new FakeEvent("submit", { bubbles: true, cancelable: true }));
await flush();
await flush();

const checkboxAfterUnauthorized = rememberCheckbox.checked;
const tokenInputAfterUnauthorized = tokenInput.value;
const storedAfterUnauthorized = windowStub.localStorage.getItem("pullpilot.bearerToken");

enqueueResponses([
  () => okResponse({}),
  () =>
    okResponse({
      schema: { variables: [] },
      values: {},
      multiline: {},
      meta: { multiline_fields: [] },
    }),
  () => okResponse({ mode: "cron", expression: "", datetime: "" }),
  () => okResponse({ files: [], selected: null, log_dir: "/logs" }),
]);

loginForm.dispatchEvent(new FakeEvent("submit", { bubbles: true, cancelable: true }));
await flush();
await flush();
await flush();

const storedAfterRelogin = windowStub.localStorage.getItem("pullpilot.bearerToken");

parentPort.postMessage({
  checkboxAfterUnauthorized,
  tokenInputAfterUnauthorized,
  storedAfterUnauthorized,
  storedAfterRelogin,
  tokenValue,
});

function enqueueResponses(responses) {
  fetchQueue.push(
    ...responses.map((factory) => (input, init) => {
      const result = factory(input, init);
      return result instanceof Promise ? result : Promise.resolve(result);
    }),
  );
}
