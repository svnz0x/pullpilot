const { setTimeout: globalSetTimeout, clearTimeout: globalClearTimeout } = globalThis;

class FakeClassList {
  constructor(owner) {
    this.owner = owner;
    this.classes = new Set();
  }
  _syncOwner() {
    if (this.owner) {
      this.owner._className = Array.from(this.classes).join(" ");
    }
  }
  add(...names) {
    names.filter(Boolean).forEach((name) => this.classes.add(name));
    this._syncOwner();
  }
  remove(...names) {
    names.filter(Boolean).forEach((name) => this.classes.delete(name));
    this._syncOwner();
  }
  toggle(name, force) {
    if (!name) {
      return this.classes.size > 0;
    }
    if (force === true) {
      this.classes.add(name);
      this._syncOwner();
      return true;
    }
    if (force === false) {
      this.classes.delete(name);
      this._syncOwner();
      return false;
    }
    if (this.classes.has(name)) {
      this.classes.delete(name);
      this._syncOwner();
      return false;
    }
    this.classes.add(name);
    this._syncOwner();
    return true;
  }
  contains(name) {
    return this.classes.has(name);
  }
  setFrom(names) {
    this.classes = new Set(names.filter(Boolean));
    this._syncOwner();
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
  constructor(id = null, tagName = "div", ownerDocument = null) {
    this.ownerDocument = ownerDocument;
    this._id = null;
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
    this.type = "";
    this.id = id;
  }
  get id() {
    return this._id;
  }
  set id(value) {
    this._id = value;
    if (this.ownerDocument) {
      if (value) {
        this.ownerDocument.elementsById.set(value, this);
      } else {
        this.ownerDocument.elementsById.delete(value);
      }
    }
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
    if (!child) return child;
    child.parentElement = this;
    if (child.ownerDocument !== this.ownerDocument) {
      child.ownerDocument = this.ownerDocument;
    }
    this.children.push(child);
    if (child.id && this.ownerDocument) {
      this.ownerDocument.elementsById.set(child.id, child);
    }
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
    const childText = this.children.map((child) => child.textContent ?? "").join("");
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
  blur() {}
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
  constructor(id, ownerDocument) {
    super(id, "form", ownerDocument);
  }
  reset() {
    if (this.id === "token-form" && this.ownerDocument) {
      const tokenInput = this.ownerDocument.getElementById("token-input");
      if (tokenInput) {
        tokenInput.value = "";
      }
      const remember = this.ownerDocument.getElementById("remember-token");
      if (remember) {
        remember.checked = false;
      }
    }
  }
}

class FakeSelectElement extends FakeElement {
  constructor(id, ownerDocument) {
    super(id, "select", ownerDocument);
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
  constructor(value = "", ownerDocument) {
    super(null, "option", ownerDocument);
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

class FakeDocument {
  constructor(window) {
    this.defaultView = window;
    this.elementsById = new Map();
    this.documentElement = new FakeElement("html", "html", this);
    this.body = new FakeElement("body", "body", this);
    this.documentElement.appendChild(this.body);
    this.registerElement(this.documentElement);
    this.registerElement(this.body);
  }
  createElement(tag) {
    if (tag === "option") {
      return new FakeOptionElement("", this);
    }
    if (tag === "select") {
      return new FakeSelectElement(null, this);
    }
    if (tag === "form") {
      return new FakeFormElement(null, this);
    }
    return new FakeElement(null, tag, this);
  }
  getElementById(id) {
    return this.elementsById.get(id) ?? null;
  }
  querySelector(selector) {
    return this.documentElement.querySelector(selector);
  }
  querySelectorAll(selector) {
    return this.documentElement.querySelectorAll(selector);
  }
  registerElement(element) {
    if (element && element.id) {
      this.elementsById.set(element.id, element);
    }
    return element;
  }
  contains(node) {
    let current = node;
    while (current) {
      if (current === this.documentElement) {
        return true;
      }
      current = current.parentElement;
    }
    return false;
  }
  open() {
    this.body.children = [];
    this.body.textContent = "";
  }
  write() {}
  close() {}
}

export class Window {
  constructor({ url = "https://example.test/ui/" } = {}) {
    this.document = new FakeDocument(this);
    this.navigator = { userAgent: "fake" };
    const targetUrl = new URL(url);
    this.location = {
      origin: `${targetUrl.protocol}//${targetUrl.host}`,
      protocol: targetUrl.protocol,
      host: targetUrl.host,
      pathname: targetUrl.pathname,
      href: targetUrl.href,
    };
    this.localStorage = new MemoryStorage();
    this.sessionStorage = new MemoryStorage();
    this.URL = URL;
    this.Request = Request;
    this.Response = Response;
    this.Headers = Headers;
    this.setTimeout = globalSetTimeout;
    this.clearTimeout = globalClearTimeout;
    this.Event = FakeEvent;
    this.CustomEvent = FakeEvent;
    this.Node = FakeElement;
    this.HTMLElement = FakeElement;
    const documentRef = this.document;
    this.DOMParser = class {
      parseFromString() {
        return { documentElement: documentRef.documentElement };
      }
    };
    this.getComputedStyle = () => ({ getPropertyValue: () => "", setProperty: () => {} });
    this.requestAnimationFrame = (callback) => this.setTimeout(() => callback(Date.now()), 0);
    this.cancelAnimationFrame = (id) => this.clearTimeout(id);
  }
  close() {}
}

export default { Window };
