const { setTimeout, clearTimeout } = globalThis;

export const createAppTestHarness = () => {
  const elementsById = new Map();

  class FakeClassList {
    constructor(owner) {
      this.owner = owner;
      this.classes = new Set();
    }
    _updateOwner() {
      if (this.owner) {
        this.owner._className = Array.from(this.classes).join(" ");
      }
    }
    add(...names) {
      names.filter(Boolean).forEach((name) => this.classes.add(name));
      this._updateOwner();
    }
    remove(...names) {
      names.filter(Boolean).forEach((name) => this.classes.delete(name));
      this._updateOwner();
    }
    toggle(name, force) {
      if (!name) {
        return this.classes.size > 0;
      }
      if (force === true) {
        this.classes.add(name);
        this._updateOwner();
        return true;
      }
      if (force === false) {
        this.classes.delete(name);
        this._updateOwner();
        return false;
      }
      if (this.classes.has(name)) {
        this.classes.delete(name);
        this._updateOwner();
        return false;
      }
      this.classes.add(name);
      this._updateOwner();
      return true;
    }
    contains(name) {
      return this.classes.has(name);
    }
    setFrom(names) {
      this.classes = new Set(names.filter(Boolean));
      this._updateOwner();
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
      this.classList = new FakeClassList(this);
      this._className = "";
      this.attributes = new Map();
      this.listeners = new Map();
      this.disabled = false;
      this.hidden = false;
      this._textContent = "";
      this.value = "";
      this.checked = false;
      this.innerHTML = "";
      this.parentElement = null;
    }
    get className() {
      return this._className;
    }
    set className(value) {
      const names =
        typeof value === "string"
          ? value
              .split(/\s+/)
              .map((name) => name.trim())
              .filter(Boolean)
          : [];
      this.classList.setFrom(names);
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
    get textContent() {
      if (!this.children.length) {
        return this._textContent ?? "";
      }
      const childText = this.children
        .map((child) => child.textContent ?? "")
        .join("");
      return `${this._textContent ?? ""}${childText}`;
    }
    set textContent(value) {
      this._textContent = value == null ? "" : String(value);
      if (this.children.length) {
        this.children.forEach((child) => {
          child.parentElement = null;
        });
        this.children = [];
      }
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
    matchesSelector(selector) {
      if (!selector) {
        return false;
      }
      const tagMatch = selector.match(/^[a-zA-Z][a-zA-Z0-9-]*/);
      if (tagMatch && this.tagName !== tagMatch[0].toUpperCase()) {
        return false;
      }
      const idMatch = selector.match(/#([a-zA-Z0-9_-]+)/);
      if (idMatch && this.id !== idMatch[1]) {
        return false;
      }
      const classMatches = selector.match(/\.([a-zA-Z0-9_-]+)/g) || [];
      const hasClass = (name) => {
        if (!name) return false;
        if (this.classList.contains(name)) return true;
        if (typeof this._className === "string" && this._className.length) {
          return this._className.split(/\s+/).includes(name);
        }
        return false;
      };
      for (const classToken of classMatches) {
        const className = classToken.slice(1);
        if (!hasClass(className)) {
          return false;
        }
      }
      const attributeRegex = /\[data-([a-zA-Z0-9_-]+)(?:=(?:"([^"]*)"|'([^']*)'|([^\]]+)))?\]/g;
      let attributeMatch;
      while ((attributeMatch = attributeRegex.exec(selector))) {
        const rawName = attributeMatch[1];
        const camelName = rawName.replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
        const expected = attributeMatch[2] ?? attributeMatch[3] ?? attributeMatch[4] ?? null;
        const actual = this.dataset?.[camelName] ?? null;
        if (expected === null) {
          if (actual == null) {
            return false;
          }
        } else if (actual !== expected) {
          return false;
        }
      }
      return true;
    }
    querySelector(selector) {
      const all = this.querySelectorAll(selector);
      return all.length ? all[0] : null;
    }
    querySelectorAll(selector) {
      if (!selector) {
        return [];
      }
      const selectors = selector
        .split(",")
        .map((segment) => segment.trim())
        .filter(Boolean);
      if (!selectors.length) {
        return [];
      }
      const results = [];
      const seen = new Set();
      const visit = (element) => {
        element.children.forEach((child) => {
          for (const simpleSelector of selectors) {
            if (child.matchesSelector(simpleSelector)) {
              if (!seen.has(child)) {
                seen.add(child);
                results.push(child);
              }
              break;
            }
          }
          visit(child);
        });
      };
      visit(this);
      return results;
    }
    focus() {}
    setAttribute(name, value) {
      this.attributes.set(name, String(value));
    }
    removeAttribute(name) {
      this.attributes.delete(name);
    }
    getAttribute(name) {
      return this.attributes.has(name) ? this.attributes.get(name) : null;
    }
    hasAttribute(name) {
      return this.attributes.has(name);
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

  const registerElement = (element) => {
    if (element.id) {
      elementsById.set(element.id, element);
    }
    return element;
  };

  const body = new FakeElement("body", "body");
  body.classList = new FakeClassList();
  const main = registerElement(new FakeElement(null, "main"));

  const loginForm = registerElement(new FakeFormElement("token-form"));
  const tokenInput = registerElement(new FakeElement("token-input", "input"));
  const loginStatus = registerElement(new FakeElement("login-status", "div"));
  const clearTokenButton = registerElement(new FakeElement("clear-token", "button"));
  const rememberCheckbox = registerElement(new FakeElement("remember-token", "input"));
  const logoutButton = registerElement(new FakeElement("logout-button", "button"));
  const configForm = registerElement(new FakeFormElement("config-form"));
  const configFields = registerElement(new FakeElement("config-fields", "div"));
  const resetConfigButton = registerElement(new FakeElement("reset-config", "button"));
  const retryConfigButton = registerElement(new FakeElement("retry-config", "button"));
  retryConfigButton.hidden = true;
  const testConfigButton = registerElement(new FakeElement("test-config", "button"));
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
  const initialLoadingBanner = registerElement(
    new FakeElement("initial-loading-banner", "div"),
  );

  main.querySelectorAll = () => [];

  const documentStub = {
    body,
    getElementById(id) {
      return elementsById.get(id) ?? null;
    },
    querySelector(selector) {
      if (selector === "main") {
        return main;
      }
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
      throw new Error(
        `Unexpected fetch for ${typeof input === "object" ? input.url ?? "object" : input}`,
      );
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

  const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

  const enqueueResponses = (responses) => {
    fetchQueue.push(
      ...responses.map((factory) => (input, init) => {
        const result = factory(input, init);
        return result instanceof Promise ? result : Promise.resolve(result);
      }),
    );
  };

  return {
    elementsById,
    body,
    main,
    loginForm,
    tokenInput,
    loginStatus,
    clearTokenButton,
    rememberCheckbox,
    logoutButton,
    configForm,
    configFields,
    resetConfigButton,
    retryConfigButton,
    testConfigButton,
    configStatus,
    scheduleForm,
    scheduleFields,
    scheduleMode,
    scheduleExpression,
    scheduleDatetime,
    scheduleStatus,
    scheduleReset,
    logSelect,
    logContent,
    logMeta,
    logsStatus,
    refreshLogs,
    initialLoadingBanner,
    window: windowStub,
    document: documentStub,
    localStorage: windowStub.localStorage,
    sessionStorage: windowStub.sessionStorage,
    fetchQueue,
    enqueueResponses,
    okResponse,
    flush,
    FakeEvent,
  };
};

export default createAppTestHarness;
